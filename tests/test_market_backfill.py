from pathlib import Path

from cricket_edge.backtesting import run_strategy_backtest
from cricket_edge.database import Database, utc_now
from cricket_edge.market import backfill_historical_market_baselines


def _insert_fixture(db: Database, team_a: str, team_b: str, match_date: str, source: str = "bet365") -> int:
    return db.execute(
        """
        INSERT INTO fixtures(
            match_date, start_time, competition, format, team_a, team_b, venue,
            status, source, created_at
        )
        VALUES (?, '09:00', 'Test League', 'T20', ?, ?, 'Test Ground', 'scheduled', ?, ?)
        """,
        (match_date, team_a, team_b, source, utc_now()),
    )


def _insert_cricsheet_match(db: Database, match_id: str, match_date: str, team_a: str, team_b: str, winner: str) -> None:
    db.execute(
        """
        INSERT INTO cricsheet_matches(
            match_id, source_file, match_date, competition, gender, match_type,
            team_a, team_b, venue, city, winner, outcome,
            team_a_runs, team_a_wickets, team_a_balls,
            team_b_runs, team_b_wickets, team_b_balls, inserted_at
        )
        VALUES (?, 'test.json', ?, 'Test League', 'male', 'T20', ?, ?, 'Test Ground', 'Test City',
                ?, 'normal', 160, 6, 120, 150, 7, 120, ?)
        """,
        (match_id, match_date, team_a, team_b, winner, utc_now()),
    )


def _insert_odds(db: Database, fixture_id: int, selection: str, odds: float, captured_at: str, source: str = "bet365") -> None:
    db.execute(
        """
        INSERT INTO odds_snapshots(fixture_id, market, selection, odds, source, captured_at)
        VALUES (?, 'match_winner', ?, ?, ?, ?)
        """,
        (fixture_id, selection, odds, source, captured_at),
    )


def _insert_model_prediction(db: Database, model_name: str, match_id: str, match_date: str, team_a: str, team_b: str, winner: str, pred_a: float, result_a: float) -> None:
    db.execute(
        """
        INSERT INTO model_predictions(
            model_name, match_id, split, match_date, competition, team_a, team_b,
            winner, pred_a, result_a, brier, log_loss, correct, features_json
        )
        VALUES (?, ?, 'test', ?, 'Test League', ?, ?, ?, ?, ?, 0.1, 0.4, 1, '{}')
        """,
        (model_name, match_id, match_date, team_a, team_b, winner, pred_a, result_a),
    )


def test_backfill_only_inserts_when_odds_and_link_both_exist(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta", "2026-01-01")
    _insert_cricsheet_match(db, "m1", "2026-01-01", "Alpha", "Beta", "Alpha")
    _insert_odds(db, fixture_id, "Alpha", 2.20, "2026-01-01T09:00:00+00:00")
    _insert_odds(db, fixture_id, "Beta", 1.95, "2026-01-01T09:00:00+00:00")
    # A second fixture links to a real match but has no captured odds at all --
    # it should count as linked, contribute zero rows, and not error.
    _insert_fixture(db, "Gamma", "Delta", "2026-01-02")
    _insert_cricsheet_match(db, "m2", "2026-01-02", "Gamma", "Delta", "Delta")

    result = backfill_historical_market_baselines(db)

    assert result["linked"] == 2
    assert result["skipped_no_match"] == 0
    assert result["rows_inserted"] == 2
    rows = db.query("SELECT * FROM market_baselines WHERE scope = 'historical_match'")
    assert {row["selection"] for row in rows} == {"Alpha", "Beta"}
    alpha_row = next(row for row in rows if row["selection"] == "Alpha")
    assert alpha_row["result"] == 1.0


def test_backfill_is_idempotent(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta", "2026-01-01")
    _insert_cricsheet_match(db, "m1", "2026-01-01", "Alpha", "Beta", "Alpha")
    _insert_odds(db, fixture_id, "Alpha", 2.20, "2026-01-01T09:00:00+00:00")
    _insert_odds(db, fixture_id, "Beta", 1.95, "2026-01-01T09:00:00+00:00")

    backfill_historical_market_baselines(db)
    backfill_historical_market_baselines(db)

    rows = db.query("SELECT * FROM market_baselines WHERE scope = 'historical_match'")
    assert len(rows) == 2


def test_backfilled_rows_feed_a_real_strategy_backtest(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta", "2026-01-01")
    _insert_cricsheet_match(db, "m1", "2026-01-01", "Alpha", "Beta", "Alpha")
    _insert_odds(db, fixture_id, "Alpha", 2.20, "2026-01-01T09:00:00+00:00")
    _insert_odds(db, fixture_id, "Beta", 1.95, "2026-01-01T09:00:00+00:00")
    _insert_model_prediction(db, "candidate_v1", "m1", "2026-01-01", "Alpha", "Beta", "Alpha", 0.62, 1.0)

    backfill_historical_market_baselines(db)
    result = run_strategy_backtest(db, model_name="candidate_v1", min_edge=0.03, stake=10.0)

    assert result["bets"] >= 1
