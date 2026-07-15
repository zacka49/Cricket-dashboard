import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from cricket_edge.database import Database, utc_now
from cricket_edge.orchestrator import CricketEdgeOrchestrator


class WorkflowTest(unittest.TestCase):
    def test_morning_run_generates_predictions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / "test.sqlite3")
            app = CricketEdgeOrchestrator(db)
            with patch(
                "cricket_edge.orchestrator.fetch_bet365_cricket_odds",
                return_value={"ok": True, "events_checked": 0, "odds_rows_inserted": 0, "errors": []},
            ):
                result = app.morning_run()
            state = app.state()

            self.assertGreater(result["predictions"], 0)
            self.assertGreater(len(state["fixtures"]), 0)
            self.assertGreater(len(state["predictions"]), 0)
            self.assertIn("bankroll", state["account"])

    def test_routine_refresh_reuses_fresh_real_odds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = CricketEdgeOrchestrator(Database(Path(temp_dir) / "test.sqlite3"))
            fresh_status = {"bet365_status": {"is_fresh": True, "latest_capture": utc_now()}}
            with patch("cricket_edge.orchestrator.latest_week4_report", return_value=fresh_status), patch.object(
                app, "fetch_bet365_odds"
            ) as fetch:
                result = app.refresh_live_odds_if_needed()

            self.assertTrue(result["skipped"])
            self.assertEqual(result["reason"], "fresh_real_odds_available")
            fetch.assert_not_called()

    def test_routine_refresh_respects_provider_rate_limit_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = CricketEdgeOrchestrator(Database(Path(temp_dir) / "test.sqlite3"))
            app.db.log_event(
                "market",
                "Fetched Bet365 cricket odds for 25 events; inserted 0 odds rows.",
                {"errors": [{"error": "HTTP 429: rate limit resets in 15 minutes"}]},
            )
            with patch.object(app, "fetch_bet365_odds") as fetch:
                result = app.refresh_live_odds_if_needed()

            self.assertTrue(result["skipped"])
            self.assertEqual(result["reason"], "provider_rate_limited")
            self.assertIn("retry_at", result)
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
