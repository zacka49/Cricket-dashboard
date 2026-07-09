import json
import tempfile
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from cricket_edge.database import Database
from cricket_edge.orchestrator import CricketEdgeOrchestrator
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
