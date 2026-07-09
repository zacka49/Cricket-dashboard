from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cricket_edge.database import Database, utc_now
from cricket_edge.market import fetch_bet365_cricket_odds, latest_week4_report


class FakeOddsSource:
    def __init__(self, db: Database) -> None:
        self.db = db

    def fetch_odds_api_io_sports(self) -> dict:
        return {"data": [{"name": "Cricket", "slug": "cricket"}]}

    def fetch_odds_api_io_events(self, sport: str, status: str | None = None, limit: int | None = None) -> dict:
        if status == "live":
            return {"data": []}
        return {
            "data": [
                {
                    "id": 123,
                    "home": "Somerset",
                    "away": "Surrey",
                    "date": "2026-06-12T12:00:00Z",
                    "status": "pending",
                    "league": {"name": "T20 Blast", "slug": "t20-blast"},
                    "sport": {"name": "Cricket", "slug": "cricket"},
                }
            ]
        }

    def fetch_odds_api_io_event_odds(self, event_id: str | int, bookmakers: str) -> dict:
        return {
            "data": {
                "id": event_id,
                "home": "Somerset",
                "away": "Surrey",
                "date": "2026-06-12T12:00:00Z",
                "status": "pending",
                "bookmakers": {
                    "Bet365": [
                        {
                            "name": "ML",
                            "updatedAt": "2026-06-12T10:00:00Z",
                            "odds": [{"home": "2.10", "away": "1.80"}],
                        }
                    ]
                },
            }
        }


class FailingOddsSource(FakeOddsSource):
    def fetch_odds_api_io_sports(self) -> dict:
        raise RuntimeError("provider down")

    def fetch_odds_api_io_events(self, sport: str, status: str | None = None, limit: int | None = None) -> dict:
        raise RuntimeError("provider down")


class EventOddsFailingSource(FakeOddsSource):
    def fetch_odds_api_io_event_odds(self, event_id: str | int, bookmakers: str) -> dict:
        raise RuntimeError("odds endpoint down")


class MalformedDateSource(FakeOddsSource):
    def fetch_odds_api_io_events(self, sport: str, status: str | None = None, limit: int | None = None) -> dict:
        if status == "live":
            return {"data": []}
        payload = super().fetch_odds_api_io_events(sport, status, limit)
        payload["data"][0]["date"] = "not-a-date"
        return payload


class EmptyPrimaryWithTheOddsApiFallbackSource(FakeOddsSource):
    def fetch_odds_api_io_events(self, sport: str, status: str | None = None, limit: int | None = None) -> dict:
        return {"data": []}

    def fetch_the_odds_api_odds(
        self,
        sport_key: str,
        regions: str,
        markets: str,
        bookmakers: str | None = None,
    ) -> dict:
        return {
            "data": [
                {
                    "id": "toa-1",
                    "sport_key": sport_key,
                    "sport_title": "T20 Blast",
                    "commence_time": "2026-06-14T18:30:00Z",
                    "home_team": "Somerset",
                    "away_team": "Surrey",
                    "bookmakers": [
                        {
                            "key": "paddypower",
                            "title": "Paddy Power",
                            "last_update": utc_now(),
                            "markets": [
                                {
                                    "key": "h2h",
                                    "last_update": utc_now(),
                                    "outcomes": [
                                        {"name": "Somerset", "price": 2.2},
                                        {"name": "Surrey", "price": 1.75},
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }


def test_fetch_bet365_cricket_odds_inserts_provider_rows(tmp_path: Path) -> None:
    settings = SimpleNamespace(
        odds_api_key="test-key",
        odds_api_max_events=5,
        odds_api_io_sport="cricket",
        odds_api_bookmakers="Bet365",
        odds_stale_minutes=30,
    )
    db = Database(tmp_path / "market.sqlite3")

    with patch("cricket_edge.market.SETTINGS", settings), patch("cricket_edge.market.FreeDataSources", FakeOddsSource):
        result = fetch_bet365_cricket_odds(db)

    rows = db.query("SELECT * FROM odds_snapshots WHERE source = 'bet365' ORDER BY selection")
    market_rows = db.query("SELECT * FROM market_odds_snapshots WHERE source = 'bet365' ORDER BY selection")

    assert result["ok"] is True
    assert result["events_checked"] == 1
    assert result["odds_rows_inserted"] == 2
    assert [row["selection"] for row in rows] == ["Somerset", "Surrey"]
    assert [round(row["normalized_probability"], 4) for row in market_rows] == [0.4615, 0.5385]


def test_fetch_bet365_cricket_odds_skips_duplicate_provider_snapshots(tmp_path: Path) -> None:
    settings = SimpleNamespace(
        odds_api_key="test-key",
        odds_api_max_events=5,
        odds_api_io_sport="cricket",
        odds_api_bookmakers="Bet365",
        odds_stale_minutes=30,
    )
    db = Database(tmp_path / "market.sqlite3")

    with patch("cricket_edge.market.SETTINGS", settings), patch("cricket_edge.market.FreeDataSources", FakeOddsSource):
        first = fetch_bet365_cricket_odds(db)
        second = fetch_bet365_cricket_odds(db)

    rows = db.query("SELECT * FROM market_odds_snapshots WHERE source = 'bet365'")

    assert first["odds_rows_inserted"] == 2
    assert second["odds_rows_inserted"] == 0
    assert len(rows) == 2


def test_fetch_bet365_cricket_odds_returns_structured_provider_errors(tmp_path: Path) -> None:
    settings = SimpleNamespace(
        odds_api_key="test-key",
        odds_api_max_events=5,
        odds_api_io_sport="cricket",
        odds_api_bookmakers="Bet365",
        odds_stale_minutes=30,
    )
    db = Database(tmp_path / "market.sqlite3")

    with patch("cricket_edge.market.SETTINGS", settings), patch("cricket_edge.market.FreeDataSources", FailingOddsSource):
        result = fetch_bet365_cricket_odds(db)

    assert result["ok"] is False
    assert result["events_checked"] == 0
    assert result["odds_rows_inserted"] == 0
    assert {error["stage"] for error in result["errors"]} == {"upcoming", "live_events"}


def test_fetch_bet365_cricket_odds_marks_all_event_odds_failures_not_ok(tmp_path: Path) -> None:
    settings = SimpleNamespace(
        odds_api_key="test-key",
        odds_api_max_events=5,
        odds_api_io_sport="cricket",
        odds_api_bookmakers="Bet365",
        odds_stale_minutes=30,
    )
    db = Database(tmp_path / "market.sqlite3")

    with patch("cricket_edge.market.SETTINGS", settings), patch("cricket_edge.market.FreeDataSources", EventOddsFailingSource):
        result = fetch_bet365_cricket_odds(db)

    assert result["ok"] is False
    assert result["events_checked"] == 1
    assert result["odds_rows_inserted"] == 0
    assert result["errors"][0]["stage"] == "event_odds"


def test_fetch_bet365_cricket_odds_skips_malformed_event_dates(tmp_path: Path) -> None:
    settings = SimpleNamespace(
        odds_api_key="test-key",
        odds_api_max_events=5,
        odds_api_io_sport="cricket",
        odds_api_bookmakers="Bet365",
        odds_stale_minutes=30,
    )
    db = Database(tmp_path / "market.sqlite3")

    with patch("cricket_edge.market.SETTINGS", settings), patch("cricket_edge.market.FreeDataSources", MalformedDateSource):
        result = fetch_bet365_cricket_odds(db)

    assert result["ok"] is False
    assert result["odds_rows_inserted"] == 0
    assert result["errors"][0]["stage"] == "event_odds"
    assert "Invalid event date" in result["errors"][0]["error"]


def test_fetch_live_cricket_odds_falls_back_to_the_odds_api(tmp_path: Path) -> None:
    settings = SimpleNamespace(
        odds_api_key="primary-key",
        odds_api_max_events=5,
        odds_api_io_sport="cricket",
        odds_api_bookmakers="Bet365",
        odds_stale_minutes=30,
        the_odds_api_key="fallback-key",
        the_odds_api_regions="uk,eu",
        the_odds_api_markets="h2h",
        the_odds_api_bookmakers="",
        the_odds_api_sport_keys="cricket_t20_blast",
        the_odds_api_max_sports=3,
    )
    db = Database(tmp_path / "market.sqlite3")

    with patch("cricket_edge.market.SETTINGS", settings), patch(
        "cricket_edge.market.FreeDataSources",
        EmptyPrimaryWithTheOddsApiFallbackSource,
    ):
        result = fetch_bet365_cricket_odds(db)

    rows = db.query("SELECT * FROM odds_snapshots WHERE source = 'the_odds_api' ORDER BY selection")
    market_rows = db.query("SELECT * FROM market_odds_snapshots WHERE source = 'the_odds_api' ORDER BY selection")

    assert result["ok"] is True
    assert result["fallback_used"] is True
    assert result["odds_rows_inserted"] == 2
    assert result["fallback"]["provider"] == "The Odds API"
    assert [row["selection"] for row in rows] == ["Somerset", "Surrey"]
    assert [row["bookmaker"] for row in market_rows] == ["Paddy Power", "Paddy Power"]
    assert [round(row["normalized_probability"], 4) for row in market_rows] == [0.443, 0.557]


def test_latest_week4_report_tolerates_corrupt_model_run_payload(tmp_path: Path) -> None:
    db = Database(tmp_path / "market.sqlite3")
    db.init_schema()
    db.execute(
        """
        INSERT INTO model_runs(model_name, generated_at, n_matches, brier, log_loss, accuracy, payload_json)
        VALUES ('market_implied_synthetic_v1', '2026-06-12T00:00:00+00:00', 1, 0.1, 0.2, 0.6, '{bad json')
        """
    )

    report = latest_week4_report(db)

    assert report["synthetic_market"]["payload"] == {"error": "invalid_json"}
