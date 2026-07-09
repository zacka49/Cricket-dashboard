from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .autonomous_engine import start_background_engine
from .config import SETTINGS
from .orchestrator import CricketEdgeOrchestrator


WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_DIR / "static"
TEMPLATE_DIR = WEB_DIR / "templates"


class AppState:
    orchestrator = CricketEdgeOrchestrator()


class CricketEdgeHandler(BaseHTTPRequestHandler):
    server_version = "CricketEdge/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" or self.path.startswith("/?"):
            self._send_file(TEMPLATE_DIR / "index.html", "text/html; charset=utf-8")
            return
        if self.path == "/api/state":
            self._send_json(AppState.orchestrator.state())
            return
        if self.path.startswith("/static/"):
            relative = self.path.replace("/static/", "", 1).split("?", 1)[0]
            target = (STATIC_DIR / relative).resolve()
            if not str(target).startswith(str(STATIC_DIR.resolve())):
                self._send_json({"error": "invalid path"}, status=400)
                return
            self._send_file(target)
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        routes = {
            "/api/morning-run": AppState.orchestrator.morning_run,
            "/api/monitor-tick": AppState.orchestrator.monitor_tick,
            "/api/settle": AppState.orchestrator.settle,
            "/api/reset-demo": AppState.orchestrator.reset_demo,
            "/api/train-elo": AppState.orchestrator.train_elo,
            "/api/train-logistic": AppState.orchestrator.train_logistic,
            "/api/train-week3": AppState.orchestrator.train_week3_models,
            "/api/run-week4": AppState.orchestrator.run_week4_market,
            "/api/fetch-bet365-odds": AppState.orchestrator.fetch_bet365_odds,
            "/api/fetch-live-odds": AppState.orchestrator.fetch_bet365_odds,
            "/api/pull-live-data": AppState.orchestrator.pull_live_data,
        }
        action = routes.get(self.path)
        if not action:
            self._send_json({"error": "not found"}, status=404)
            return
        try:
            result = action()
            self._send_json(_action_response(result))
        except Exception as exc:  # pragma: no cover - keeps the local server responsive
            self._send_json({"ok": False, "error": str(exc)}, status=500)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[server] {self.address_string()} - {fmt % args}")

    def _send_file(self, path: Path, content_type: str | None = None) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"error": "file not found"}, status=404)
            return
        body = path.read_bytes()
        guessed = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", guessed)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(host: str = SETTINGS.host, port: int = SETTINGS.port) -> None:
    server = ThreadingHTTPServer((host, port), CricketEdgeHandler)
    print(f"Cricket Edge running at http://{host}:{port}")
    print("Paper mode only. No real-money betting connector is implemented.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Cricket Edge.")
    finally:
        server.server_close()


def _action_response(result: Any) -> dict[str, Any]:
    ok = True
    if isinstance(result, dict) and "ok" in result:
        ok = bool(result["ok"])
    return {"ok": ok, "result": result, "reload_state": True}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Cricket Edge dashboard.")
    parser.add_argument("--host", default=SETTINGS.host)
    parser.add_argument("--port", type=int, default=SETTINGS.port)
    args = parser.parse_args()
    start_background_engine()
    run(args.host, args.port)


if __name__ == "__main__":
    main()
