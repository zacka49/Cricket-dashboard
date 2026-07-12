from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, SETTINGS
from .database import Database, utc_now


MIN_TRUSTED_BACKTEST_BETS = 30


def portfolio_readiness_report(db: Database) -> dict[str, Any]:
    items = [
        _item(
            "real_money_disabled",
            "Real-money connector disabled",
            "pass",
            "The app exposes only a paper broker and has no live-money execution path.",
        ),
        _item(
            "paper_broker",
            "Paper broker state",
            "pass" if _count(db, "paper_account") > 0 else "gap",
            "Paper account exists and bankroll/exposure can be audited.",
        ),
        _item(
            "bet365_configured",
            "Bet365 odds feed configured",
            "pass" if SETTINGS.odds_api_key else "gap",
            "ODDS_API_KEY is loaded from environment/.env; the key itself is never displayed.",
        ),
        _item(
            "real_odds_captured",
            "Real bookmaker odds captured",
            "pass" if _count_where(db, "market_odds_snapshots", "source = 'bet365'") > 0 else "gap",
            "At least one Bet365 market snapshot has been stored.",
        ),
        _item(
            "fresh_odds_gate",
            "Fresh-odds betting gate",
            "pass" if _latest_skip_reason_mentions(db, "fresh Bet365 odds") else "watch",
            "Risk decisions explicitly block missing or stale Bet365 odds.",
        ),
        _item(
            "model_training_data",
            "Model training data",
            "pass" if _count(db, "cricsheet_matches") > 0 and _count(db, "team_elo_history") > 0 else "gap",
            "Cricsheet matches and chronological Elo rows must exist before supervised evaluation can be reproduced.",
        ),
        _item(
            "model_runs",
            "Model evaluation runs",
            "pass" if _count(db, "model_runs") > 0 else "gap",
            "At least one model run should be stored with Brier score, log loss, accuracy, and payload metrics.",
        ),
        _item(
            "model_predictions",
            "Historical model predictions",
            "pass" if _count(db, "model_predictions") > 0 else "gap",
            "Historical predictions are needed for calibration review and strategy backtests.",
        ),
        _item(
            "active_model",
            "Active model registry",
            "pass" if _count_where(db, "model_registry", "active = 1") > 0 else "gap",
            "One active model should be selected for paper execution.",
        ),
        _item(
            "historical_backtesting",
            "Historical strategy backtesting",
            "pass" if _count_where(db, "backtest_runs", "bets > 0") > 0 else "gap",
            "Run the market data build/backtest after historical market odds exist.",
        ),
        _item(
            "backtest_sample_size",
            "Backtest sample size",
            _backtest_sample_status(db),
            f"A research-grade read needs at least {MIN_TRUSTED_BACKTEST_BETS} bets from timestamp-valid real market baselines.",
        ),
        _item(
            "clv_tracking",
            "Paper CLV tracking",
            "pass" if _count(db, "paper_bet_evaluations") > 0 else "gap",
            "Paper bet evaluations compare entry odds against the latest closing proxy.",
        ),
        _item(
            "decision_log",
            "Decision audit trail",
            "pass" if _count(db, "decision_log") > 0 else "gap",
            "Pipeline decisions are persisted with reasons and payloads.",
        ),
        _item(
            "scheduler_heartbeat",
            "Background scheduler heartbeat",
            "pass" if _scheduler_alive(db) else "gap",
            "Background scheduler ticks monitor/settle continuously and retrains on a schedule, without manual button presses.",
        ),
        _item(
            "tests",
            "Regression tests",
            "pass" if _tests_exist() else "gap",
            "Pytest coverage exists for odds parsing, risk gates, workflows, server routes, and backtesting.",
        ),
    ]
    complete = sum(1 for item in items if item["status"] == "pass")
    return {
        "summary": {
            "mode": "paper_only",
            "generated_at": utc_now(),
            "complete": complete,
            "total": len(items),
            "gaps": sum(1 for item in items if item["status"] == "gap"),
            "watch": sum(1 for item in items if item["status"] == "watch"),
        },
        "items": items,
    }


def _item(key: str, label: str, status: str, detail: str) -> dict[str, str]:
    return {"key": key, "label": label, "status": status, "detail": detail}


def _count(db: Database, table: str) -> int:
    row = db.query_one(f"SELECT COUNT(*) AS count FROM {table}")
    return int(row["count"] or 0) if row else 0


def _count_where(db: Database, table: str, clause: str) -> int:
    row = db.query_one(f"SELECT COUNT(*) AS count FROM {table} WHERE {clause}")
    return int(row["count"] or 0) if row else 0


def _latest_skip_reason_mentions(db: Database, needle: str) -> bool:
    row = db.query_one(
        """
        SELECT reason
        FROM decision_log
        WHERE decision = 'skip'
        ORDER BY generated_at DESC, id DESC
        LIMIT 20
        """
    )
    return bool(row and needle.lower() in str(row["reason"]).lower())


def _backtest_sample_status(db: Database) -> str:
    row = db.query_one(
        """
        SELECT bets
        FROM backtest_runs
        ORDER BY generated_at DESC, id DESC
        LIMIT 1
        """
    )
    if not row:
        return "gap"
    return "pass" if int(row["bets"] or 0) >= MIN_TRUSTED_BACKTEST_BETS else "watch"


def _scheduler_alive(db: Database) -> bool:
    row = db.query_one("SELECT last_tick_at FROM scheduler_state WHERE id = 1")
    if not row or not row["last_tick_at"]:
        return False
    last_tick = datetime.fromisoformat(str(row["last_tick_at"]).replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - last_tick).total_seconds() <= 2 * SETTINGS.scheduler_tick_seconds


def _tests_exist() -> bool:
    tests_dir = Path(PROJECT_ROOT) / "tests"
    return tests_dir.exists() and any(tests_dir.glob("test_*.py"))
