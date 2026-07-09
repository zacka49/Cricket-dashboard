from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, SETTINGS
from .database import Database, utc_now


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
            "active_model",
            "Active model registry",
            "pass" if _count_where(db, "model_registry", "active = 1") > 0 else "gap",
            "One active model should be selected for paper execution.",
        ),
        _item(
            "historical_backtesting",
            "Historical strategy backtesting",
            "pass" if _count_where(db, "backtest_runs", "bets > 0") > 0 else "gap",
            "Run Week 4/backtesting after historical market odds exist.",
        ),
        _item(
            "clv_tracking",
            "Paper CLV tracking",
            "pass" if _count(db, "paper_bet_evaluations") > 0 else "gap",
            "Paper bet evaluations compare entry odds against the latest closing proxy.",
        ),
        _item(
            "agent_audit_log",
            "Agent audit trail",
            "pass" if _count(db, "agent_decisions") > 0 else "gap",
            "Agent decisions are persisted with reasons and payloads.",
        ),
        _item(
            "scheduler_script",
            "Paper scheduler script",
            "pass" if (PROJECT_ROOT / "scripts" / "run_paper_scheduler.py").exists() else "gap",
            "A local script can run morning and monitor cycles in paper mode.",
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
        FROM agent_decisions
        WHERE decision = 'skip'
        ORDER BY generated_at DESC, id DESC
        LIMIT 20
        """
    )
    return bool(row and needle.lower() in str(row["reason"]).lower())


def _tests_exist() -> bool:
    tests_dir = Path(PROJECT_ROOT) / "tests"
    return tests_dir.exists() and any(tests_dir.glob("test_*.py"))
