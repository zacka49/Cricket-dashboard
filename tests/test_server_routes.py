import json
import tempfile
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from cricket_edge.database import Database
from cricket_edge.orchestrator import CricketEdgeOrchestrator, build_state
from cricket_edge.server import AppState, CricketEdgeHandler


def test_post_actions_return_compact_reload_response() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db = Database(Path(temp_dir) / "server.sqlite3")
        previous = AppState.orchestrator
        AppState.orchestrator = CricketEdgeOrchestrator(db)
        server = ThreadingHTTPServer(("127.0.0.1", 0), CricketEdgeHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch(
                "cricket_edge.orchestrator.fetch_bet365_cricket_odds",
                return_value={"ok": True, "events_checked": 0, "odds_rows_inserted": 0, "errors": []},
            ):
                conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
                conn.request("POST", "/api/morning-run", body="{}", headers={"Content-Type": "application/json"})
                response = conn.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
                conn.close()
        finally:
            server.shutdown()
            server.server_close()
            AppState.orchestrator = previous

    assert response.status == 200
    assert payload["ok"] is True
    assert payload["reload_state"] is True
    assert "state" not in payload
    assert payload["result"]["predictions"] > 0


def test_state_charts_stay_well_formed_on_an_empty_database(tmp_path: Path) -> None:
    # Not a substitute for actually looking at the dashboard in a browser (no
    # browser automation is available here), but a cheap guard against the chart
    # builders crashing on a fresh, unseeded database rather than just an empty one.
    db = Database(tmp_path / "empty.sqlite3")
    db.init_schema()

    state = build_state(db)

    expected_keys = {
        "model_comparison",
        "calibration",
        "feature_importance",
        "elo_ratings",
        "equity_curve",
        "backtest_pnl",
        "edge_bucket",
    }
    assert expected_keys <= state["charts"].keys()
    for chart in state["charts"].values():
        assert isinstance(chart, dict)
