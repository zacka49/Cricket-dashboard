import json
from pathlib import Path

from cricket_edge.database import Database
from cricket_edge.elo import EloConfig
from cricket_edge.live_model import build_live_match_features


def _empty_snapshot() -> dict:
    return {"elo_ratings": {}, "team_stats": {}, "model_name": "test_model"}


def test_logs_diagnostic_for_a_team_with_no_alias_and_no_history(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture = {"team_a": "Nowhereland", "team_b": "Somewhereland", "match_date": "2026-01-01", "competition": "Test League"}

    build_live_match_features(fixture, _empty_snapshot(), db)

    events = db.query("SELECT * FROM events WHERE type = 'diagnostics' ORDER BY id")
    assert len(events) == 2
    payload_a = json.loads(events[0]["payload_json"])
    assert payload_a["raw_name"] == "Nowhereland"
    assert payload_a["alias_applied"] is False


def test_logs_diagnostic_marking_alias_applied_when_normalization_still_finds_no_history(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture = {"team_a": "USA", "team_b": "Somewhereland", "match_date": "2026-01-01", "competition": "Test League"}

    build_live_match_features(fixture, _empty_snapshot(), db)

    events = db.query("SELECT * FROM events WHERE type = 'diagnostics' ORDER BY id")
    payload_for_usa = next(json.loads(row["payload_json"]) for row in events if json.loads(row["payload_json"])["raw_name"] == "USA")
    assert payload_for_usa["normalized_name"] == "United States of America"
    assert payload_for_usa["alias_applied"] is True


def test_no_diagnostic_logged_when_team_has_historical_matches(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    snapshot = {
        "elo_ratings": {"Alpha": EloConfig.start_rating, "Beta": EloConfig.start_rating},
        "team_stats": {"Alpha": {"matches": 10, "wins": 5, "runs_for": 0, "runs_against": 0, "wickets_for": 0}},
        "model_name": "test_model",
    }
    fixture = {"team_a": "Alpha", "team_b": "Beta", "match_date": "2026-01-01", "competition": "Test League"}

    build_live_match_features(fixture, snapshot, db)

    events = db.query("SELECT * FROM events WHERE type = 'diagnostics'")
    raw_names = {json.loads(row["payload_json"])["raw_name"] for row in events}
    assert "Alpha" not in raw_names
    assert "Beta" in raw_names


def test_no_diagnostic_logged_when_db_not_provided(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture = {"team_a": "Nowhereland", "team_b": "Somewhereland", "match_date": "2026-01-01", "competition": "Test League"}

    build_live_match_features(fixture, _empty_snapshot())

    assert db.query("SELECT * FROM events") == []
