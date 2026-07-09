from __future__ import annotations

import threading
import time
from datetime import date, datetime, timezone
from typing import Any

from .config import SETTINGS
from .database import utc_now
from .orchestrator import CricketEdgeOrchestrator


class AutonomousEngine:
    """Runs the daily cycle, continuous monitoring/settlement, and scheduled
    model retraining without any manual button presses."""

    def __init__(self, orchestrator: CricketEdgeOrchestrator | None = None) -> None:
        self.app = orchestrator or CricketEdgeOrchestrator()
        self.db = self.app.db
        self._ensure_state_row()

    def _ensure_state_row(self) -> None:
        self.db.execute("INSERT OR IGNORE INTO autonomous_state(id, updated_at) VALUES (1, ?)", (utc_now(),))

    def run_forever(self) -> None:
        while True:
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 - one bad tick must not kill the loop
                self.db.log_event("autonomous_engine", f"Tick failed: {exc}", {"error": str(exc)})
            time.sleep(SETTINGS.autonomous_tick_seconds)

    def tick(self) -> dict[str, Any]:
        state = self.db.query_one("SELECT * FROM autonomous_state WHERE id = 1")
        today = date.today().isoformat()

        if state["last_morning_run_date"] != today:
            self.app.morning_run()
            self.db.execute("UPDATE autonomous_state SET last_morning_run_date = ? WHERE id = 1", (today,))

        self.app.monitor_tick()
        self.app.settle()

        if self._retrain_due(state):
            # Isolated from the rest of the tick: a retrain failure (e.g. not
            # enough training data yet on a fresh system) must not prevent the
            # heartbeat below from updating -- "alive" means the engine is
            # ticking, not that every step succeeded.
            try:
                self.app.train_week3_models()
                self.db.execute(
                    "UPDATE autonomous_state SET last_retrain_at = ?, last_retrain_match_count = ? WHERE id = 1",
                    (utc_now(), self._match_count()),
                )
            except Exception as exc:  # noqa: BLE001
                self.db.log_event("autonomous_engine", f"Retrain failed: {exc}", {"error": str(exc)})

        self.db.execute("UPDATE autonomous_state SET last_tick_at = ?, updated_at = ? WHERE id = 1", (utc_now(), utc_now()))
        self.db.log_event("autonomous_engine", "Tick completed.", {})
        return {"ticked_at": utc_now()}

    def _retrain_due(self, state: dict[str, Any]) -> bool:
        if not state["last_retrain_at"]:
            return True
        hours_since = (datetime.now(timezone.utc) - _parse_utc(state["last_retrain_at"])).total_seconds() / 3600
        if hours_since >= SETTINGS.autonomous_retrain_interval_hours:
            return True
        new_matches = self._match_count() - int(state["last_retrain_match_count"] or 0)
        return new_matches >= SETTINGS.autonomous_retrain_new_match_threshold

    def _match_count(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) AS count FROM cricsheet_matches")
        return int(row["count"] or 0)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def start_background_engine() -> AutonomousEngine | None:
    if not SETTINGS.autonomous_enabled:
        return None
    engine = AutonomousEngine()
    thread = threading.Thread(target=engine.run_forever, daemon=True, name="autonomous-engine")
    thread.start()
    return engine
