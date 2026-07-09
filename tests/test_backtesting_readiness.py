from pathlib import Path

from cricket_edge.backtesting import run_strategy_backtest
from cricket_edge.database import Database, utc_now
from cricket_edge.readiness import portfolio_readiness_report


def test_strategy_backtest_uses_historical_market_baselines(tmp_path: Path) -> None:
    db = Database(tmp_path / "backtest.sqlite3")
    db.init_schema()
    _insert_match(db, "m1", "2024-01-01", "Alpha", "Beta", "Alpha")
    _insert_match(db, "m2", "2024-01-02", "Gamma", "Delta", "Delta")
    _insert_prediction(db, "candidate_v1", "m1", "2024-01-01", "Alpha", "Beta", "Alpha", 0.62, 1.0)
    _insert_prediction(db, "candidate_v1", "m2", "2024-01-02", "Gamma", "Delta", "Delta", 0.51, 0.0)
    _insert_market(db, "m1", "2024-01-01T09:00:00+00:00", "Alpha", 2.20, 0.45)
    _insert_market(db, "m2", "2024-01-02T09:00:00+00:00", "Gamma", 1.95, 0.50)

    result = run_strategy_backtest(db, model_name="candidate_v1", min_edge=0.03, stake=10.0)

    assert result["bets"] == 1
    assert result["wins"] == 1
    assert result["staked"] == 10.0
    assert result["pnl"] == 12.0
    assert result["roi"] == 1.2
    assert result["by_competition"][0]["competition"] == "Test League"


def test_portfolio_readiness_report_tracks_passes_and_gaps(tmp_path: Path) -> None:
    db = Database(tmp_path / "readiness.sqlite3")
    db.init_schema()

    report = portfolio_readiness_report(db)

    assert report["summary"]["mode"] == "paper_only"
    assert report["summary"]["complete"] < report["summary"]["total"]
    assert any(item["key"] == "real_money_disabled" and item["status"] == "pass" for item in report["items"])
    assert any(item["key"] == "historical_backtesting" and item["status"] == "gap" for item in report["items"])


def _insert_match(db: Database, match_id: str, match_date: str, team_a: str, team_b: str, winner: str) -> None:
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


def _insert_prediction(
    db: Database,
    model_name: str,
    match_id: str,
    match_date: str,
    team_a: str,
    team_b: str,
    winner: str,
    pred_a: float,
    result_a: float,
) -> None:
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


def _insert_market(
    db: Database,
    match_id: str,
    captured_at: str,
    selection: str,
    odds: float,
    probability: float,
) -> None:
    db.execute(
        """
        INSERT INTO market_baselines(
            model_name, scope, fixture_id, match_id, market, selection, probability,
            decimal_odds, overround, captured_at, result, brier, log_loss, correct, source
        )
        VALUES ('market_implied_historical_v1', 'historical_match', NULL, ?, 'match_winner',
                ?, ?, ?, 1.05, ?, NULL, NULL, NULL, NULL, 'manual_csv')
        """,
        (match_id, selection, probability, odds, captured_at),
    )
