from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .database import utc_now
from .orchestrator import CricketEdgeOrchestrator


@dataclass(frozen=True)
class PaperSchedulerConfig:
    monitor_cycles: int = 6
    interval_seconds: int = 300
    settle_after: bool = False


def run_paper_cycle_once(orchestrator: CricketEdgeOrchestrator | None = None) -> dict[str, Any]:
    app = orchestrator or CricketEdgeOrchestrator()
    started_at = utc_now()
    morning = app.morning_run()
    monitor = app.monitor_tick()
    account = app.state()["account"]
    return {
        "mode": "paper_only",
        "started_at": started_at,
        "finished_at": utc_now(),
        "morning": _compact_result(morning),
        "monitor": _compact_result(monitor),
        "account": account,
    }


def run_paper_scheduler(
    config: PaperSchedulerConfig | None = None,
    orchestrator: CricketEdgeOrchestrator | None = None,
) -> dict[str, Any]:
    config = config or PaperSchedulerConfig()
    app = orchestrator or CricketEdgeOrchestrator()
    started_at = utc_now()
    morning = app.morning_run()
    monitors = []
    for cycle in range(max(0, config.monitor_cycles)):
        if cycle > 0 and config.interval_seconds > 0:
            time.sleep(config.interval_seconds)
        result = app.monitor_tick()
        monitors.append({"cycle": cycle + 1, "result": _compact_result(result)})
    settlement = app.settle() if config.settle_after else None
    account = app.state()["account"]
    return {
        "mode": "paper_only",
        "started_at": started_at,
        "finished_at": utc_now(),
        "config": config.__dict__,
        "morning": _compact_result(morning),
        "monitors": monitors,
        "settlement": settlement,
        "account": account,
    }


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in ("predictions", "decisions", "account", "odds_refresh", "data_status"):
        if key in result:
            compact[key] = result[key]
    if "market_actions" in result:
        compact["market_actions"] = len(result["market_actions"])
    return compact
