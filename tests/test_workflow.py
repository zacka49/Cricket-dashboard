import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from cricket_edge.database import Database
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


if __name__ == "__main__":
    unittest.main()
