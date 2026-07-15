import json
from pathlib import Path

from cricket_edge.database import Database, utc_now
from cricket_edge.logistic_model import PRETOSS_MODEL_NAME
from cricket_edge.pipeline import BetEvaluator
from cricket_edge.prediction import PredictionEngine
from cricket_edge.risk import evaluate_candidate
from cricket_edge.seed import seed_demo_data


def _insert_real_fixture(db: Database) -> dict:
    fixture_id = db.execute(
        '''
        INSERT INTO fixtures(
            match_date, start_time, competition, format, team_a, team_b, venue,
            status, source, created_at
        )
        VALUES ('2026-07-14', '09:00', 'Test League', 'T20', 'Alpha', 'Beta',
                'Test Ground', 'scheduled', 'bet365', ?)
        ''',
        (utc_now(),),
    )
    for selection, odds in (('Alpha', 2.25), ('Beta', 1.80)):
        db.execute(
            '''
            INSERT INTO odds_snapshots(fixture_id, market, selection, odds, source, captured_at)
            VALUES (?, 'match_winner', ?, ?, 'bet365', ?)
            ''',
            (fixture_id, selection, odds, utc_now()),
        )
    return db.query_one('SELECT * FROM fixtures WHERE id = ?', (fixture_id,))


def test_real_fixture_without_active_model_is_explicitly_blocked(tmp_path: Path) -> None:
    db = Database(tmp_path / 'gate.sqlite3')
    db.init_schema()
    fixture = _insert_real_fixture(db)

    predictions = PredictionEngine(db).run_for_fixture(fixture)
    decisions = BetEvaluator(db).run()

    assert {row['model_name'] for row in predictions} == {'blocked_no_active_model_v1'}
    assert all(json.loads(row['features_json'])['model_artifact_status'] == 'missing_or_inactive' for row in predictions)
    assert all(decision['decision'] == 'skip' for decision in decisions)
    assert all('no_valid_active_model' in decision['risk']['risk_reasons'] for decision in decisions)
    assert db.query('SELECT * FROM paper_bets') == []


def test_active_governed_pretoss_model_uses_live_prediction_path(tmp_path: Path) -> None:
    db = Database(tmp_path / 'gate.sqlite3')
    db.init_schema()
    fixture = _insert_real_fixture(db)
    payload = {
        'coefficients': [{'feature': 'intercept', 'weight': 0.0}],
        'calibrator': {'a': 1.0, 'b': 0.0},
    }
    db.execute(
        '''
        INSERT INTO model_runs(model_name, generated_at, n_matches, brier, log_loss, accuracy, payload_json)
        VALUES (?, ?, 100, 0.2, 0.5, 0.6, ?)
        ''',
        (PRETOSS_MODEL_NAME, utc_now(), json.dumps(payload)),
    )
    db.execute(
        '''
        INSERT INTO model_registry(
            model_name, model_family, timing, status, generated_at, active, calibrated,
            feature_names_json, metrics_json, notes
        )
        VALUES (?, 'logistic_regression', 'pre_toss', 'active', ?, 1, 1, '[]', '{}', '')
        ''',
        (PRETOSS_MODEL_NAME, utc_now()),
    )

    predictions = PredictionEngine(db).run_for_fixture(fixture)

    assert {row['model_name'] for row in predictions} == {PRETOSS_MODEL_NAME}
    assert all(json.loads(row['features_json'])['model_artifact_status'] == 'active' for row in predictions)
    assert all(json.loads(row['features_json'])['feature_source'] == 'trained_pretoss_logistic' for row in predictions)


def test_real_fixture_outside_t20_scope_is_explicitly_blocked(tmp_path: Path) -> None:
    db = Database(tmp_path / 'gate.sqlite3')
    db.init_schema()
    fixture = _insert_real_fixture(db)
    db.execute("UPDATE fixtures SET format = 'ODI', competition = 'One Day Internationals' WHERE id = ?", (fixture['id'],))
    fixture = db.query_one('SELECT * FROM fixtures WHERE id = ?', (fixture['id'],))

    predictions = PredictionEngine(db).run_for_fixture(fixture)
    decisions = BetEvaluator(db).run()

    assert {row['model_name'] for row in predictions} == {'blocked_unsupported_format_v1'}
    assert all(json.loads(row['features_json'])['model_block_reason'] == 'unsupported_model_scope' for row in predictions)
    assert all(decision['decision'] == 'skip' for decision in decisions)
    assert all('model supports T20 fixtures only' in decision['risk']['risk_reasons'] for decision in decisions)
    assert db.query('SELECT * FROM paper_bets') == []


def test_demo_odds_do_not_make_predictions_bettable(tmp_path: Path) -> None:
    db = Database(tmp_path / "gate.sqlite3")
    seed_demo_data(db)
    fixture = db.query_one("SELECT * FROM fixtures WHERE source = 'demo' ORDER BY id LIMIT 1")

    predictions = PredictionEngine(db).run_for_fixture(fixture)
    risk = evaluate_candidate(predictions[0], bankroll=1000.0, open_exposure=0.0)

    assert predictions[0]["market_odds"] == 0
    assert "no fresh real bookmaker odds" in risk["risk_reasons"]
    assert risk["decision"] == "skip"


def test_fresh_bet365_odds_are_used_by_prediction_engine(tmp_path: Path) -> None:
    db = Database(tmp_path / "gate.sqlite3")
    seed_demo_data(db)
    fixture = db.query_one("SELECT * FROM fixtures WHERE source = 'demo' ORDER BY id LIMIT 1")
    db.execute(
        """
        INSERT INTO odds_snapshots(fixture_id, market, selection, odds, source, captured_at)
        VALUES (?, 'match_winner', ?, 2.25, 'bet365', ?)
        """,
        (fixture["id"], fixture["team_a"], utc_now()),
    )

    predictions = PredictionEngine(db).run_for_fixture(fixture)
    selected = next(row for row in predictions if row["selection"] == fixture["team_a"])

    assert selected["market_odds"] == 2.25
    assert "fresh_bet365_odds" in selected["features_json"]


def test_fresh_the_odds_api_odds_are_used_by_prediction_engine(tmp_path: Path) -> None:
    db = Database(tmp_path / "gate.sqlite3")
    seed_demo_data(db)
    fixture = db.query_one("SELECT * FROM fixtures WHERE source = 'demo' ORDER BY id LIMIT 1")
    db.execute(
        """
        INSERT INTO odds_snapshots(fixture_id, market, selection, odds, source, captured_at)
        VALUES (?, 'match_winner', ?, 2.25, 'the_odds_api', ?)
        """,
        (fixture["id"], fixture["team_a"], utc_now()),
    )

    predictions = PredictionEngine(db).run_for_fixture(fixture)
    selected = next(row for row in predictions if row["selection"] == fixture["team_a"])
    risk = evaluate_candidate(selected, bankroll=1000.0, open_exposure=0.0)

    assert selected["market_odds"] == 2.25
    assert "fresh_the_odds_api_odds" in selected["features_json"]
    assert "no fresh real bookmaker odds" not in risk["risk_reasons"]
    assert risk['decision'] == 'skip'
