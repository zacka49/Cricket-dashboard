from pathlib import Path

from cricket_edge.database import Database, utc_now
from cricket_edge.prediction import PredictionEngine
from cricket_edge.risk import evaluate_candidate
from cricket_edge.seed import seed_demo_data


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
    assert risk["decision"] == "paper_bet"
