from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .pipeline import (
    BetEvaluator,
    BriefingWriter,
    DataHealthCheck,
    PositionMonitor,
    RiskGate,
)
from .advanced_models import latest_week3_report, train_and_evaluate_models
from .backtesting import latest_backtest_report, run_latest_strategy_backtest
from .charts import build_all_charts
from .config import SETTINGS
from .database import Database
from .elo import EloTrainer, latest_elo_report
from .live_data import pull_all_live_data
from .logistic_model import LogisticRegressionTrainer, latest_week2_report
from .market import fetch_bet365_cricket_odds, latest_week4_report, run_week4_market_build
from .paper_broker import PaperBroker
from .prediction import PredictionEngine
from .readiness import portfolio_readiness_report
from .seed import ensure_demo_odds, seed_demo_data, simulate_market_move


class CricketEdgeOrchestrator:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.db.init_schema()
        seed_demo_data(self.db)

    def morning_run(self) -> dict[str, Any]:
        seed_demo_data(self.db)
        ensure_demo_odds(self.db)
        voided_out_of_scope = PaperBroker(self.db).void_open_bets_outside_t20_scope()
        odds_refresh = self.refresh_live_odds_if_needed()
        data_status = DataHealthCheck(self.db).run()
        predictions = PredictionEngine(self.db).run_for_open_fixtures()
        bet_evaluator = BetEvaluator(self.db)
        proposals = bet_evaluator.evaluate()
        reviewed = RiskGate(self.db).review(proposals)
        placed = bet_evaluator.execute(reviewed)
        briefing = BriefingWriter(self.db).daily_briefing()
        return {
            "odds_refresh": odds_refresh,
            "data_status": data_status,
            "predictions": len(predictions),
            "decisions": len(reviewed),
            "bets_placed": len(placed),
            "bets_voided_out_of_scope": voided_out_of_scope,
            "briefing": briefing,
            "account": PaperBroker(self.db).account_summary(),
        }

    def monitor_tick(self) -> dict[str, Any]:
        odds_refresh = self.refresh_live_odds_if_needed()
        simulate_market_move(self.db)
        predictions = PredictionEngine(self.db).run_for_open_fixtures()
        actions = PositionMonitor(self.db).run()
        return {
            "odds_refresh": odds_refresh,
            "predictions": len(predictions),
            "market_actions": actions,
            "account": PaperBroker(self.db).account_summary(),
        }

    def settle(self) -> dict[str, Any]:
        broker = PaperBroker(self.db)
        settlement = broker.settle_due_bets()
        return {"account": broker.account_summary(), "settlement": settlement}

    def train_elo(self) -> dict[str, Any]:
        return EloTrainer(self.db).train()

    def train_logistic(self) -> dict[str, Any]:
        return LogisticRegressionTrainer(self.db).train()

    def train_week3_models(self) -> dict[str, Any]:
        return train_and_evaluate_models(self.db)

    def run_week4_market(self) -> dict[str, Any]:
        result = run_week4_market_build(self.db)
        result["strategy_backtest"] = run_latest_strategy_backtest(self.db)
        return result

    def fetch_bet365_odds(self) -> dict[str, Any]:
        return fetch_bet365_cricket_odds(self.db)

    def refresh_live_odds_if_needed(self) -> dict[str, Any]:
        """Avoid spending provider quota when approved odds are still usable.

        Explicit dashboard fetches continue to call ``fetch_bet365_odds``
        directly. This guard is for scheduled and routine workflow runs, where
        another refresh cannot improve a fresh snapshot and a 429 must not turn
        into repeated quota-consuming retries.
        """
        retry_at = self._rate_limit_retry_at()
        if retry_at:
            return {
                "ok": True,
                "skipped": True,
                "reason": "provider_rate_limited",
                "retry_at": retry_at,
            }
        status = (latest_week4_report(self.db).get("bet365_status") or {})
        if status.get("is_fresh"):
            return {
                "ok": True,
                "skipped": True,
                "reason": "fresh_real_odds_available",
                "latest_capture": status.get("latest_capture"),
            }
        return self.fetch_bet365_odds()

    def _rate_limit_retry_at(self) -> str | None:
        event = self.db.query_one(
            """
            SELECT timestamp, payload_json
            FROM events
            WHERE type = 'market' AND message LIKE 'Fetched % cricket odds%'
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """
        )
        if not event:
            return None
        try:
            payload = json.loads(event["payload_json"] or "{}")
        except json.JSONDecodeError:
            return None
        errors = payload.get("errors") or []
        messages = " ".join(str(item.get("error") or "") for item in errors if isinstance(item, dict))
        match = re.search(r"resets? in\s+(\d+)\s+minutes?", messages, flags=re.IGNORECASE)
        if not match:
            return None
        try:
            observed_at = datetime.fromisoformat(str(event["timestamp"]).replace("Z", "+00:00"))
        except ValueError:
            return None
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        retry_at = observed_at + timedelta(minutes=int(match.group(1)))
        if retry_at <= datetime.now(timezone.utc):
            return None
        return retry_at.isoformat()

    def pull_live_data(self) -> dict[str, Any]:
        return pull_all_live_data(self.db)

    def state(self) -> dict[str, Any]:
        return build_state(self.db)

    def reset_demo(self) -> dict[str, Any]:
        self.db.execute("DELETE FROM paper_bets")
        self.db.execute("DELETE FROM decision_log")
        self.db.execute("DELETE FROM predictions")
        self.db.execute("DELETE FROM odds_snapshots")
        self.db.execute("DELETE FROM fixtures")
        self.db.execute("DELETE FROM events")
        seed_demo_data(self.db)
        return {"reset": True, "fixtures": len(self.db.query("SELECT id FROM fixtures"))}


def build_state(db: Database) -> dict[str, Any]:
    fixtures = db.query(
        """
        SELECT * FROM fixtures
        ORDER BY match_date, start_time
        """
    )
    predictions = db.query(
        """
        SELECT p.*, f.team_a, f.team_b, f.competition, f.venue, f.start_time, f.match_date
        FROM predictions p
        JOIN fixtures f ON f.id = p.fixture_id
        ORDER BY p.edge DESC
        """
    )
    decisions = db.query(
        """
        SELECT d.*, f.team_a, f.team_b
        FROM decision_log d
        LEFT JOIN fixtures f ON f.id = d.fixture_id
        ORDER BY d.generated_at DESC, d.id DESC
        LIMIT 40
        """
    )
    bets = db.query(
        """
        SELECT b.*, f.team_a, f.team_b, f.match_date, f.start_time, f.competition
        FROM paper_bets b
        JOIN fixtures f ON f.id = b.fixture_id
        ORDER BY b.placed_at DESC
        """
    )
    events = db.query("SELECT * FROM events ORDER BY timestamp DESC, id DESC LIMIT 30")
    cricsheet_summary = db.query_one(
        """
        SELECT
            COUNT(*) AS matches,
            COUNT(DISTINCT team_a) + COUNT(DISTINCT team_b) AS rough_team_count,
            MIN(match_date) AS first_match,
            MAX(match_date) AS latest_match
        FROM cricsheet_matches
        """
    )
    competitions = db.query(
        """
        SELECT competition, COUNT(*) AS matches
        FROM cricsheet_matches
        GROUP BY competition
        ORDER BY matches DESC
        LIMIT 8
        """
    )
    odds = db.query(
        """
        SELECT o.*
        FROM odds_snapshots o
        JOIN (
            SELECT fixture_id, market, selection, MAX(captured_at) AS captured_at
            FROM odds_snapshots
            GROUP BY fixture_id, market, selection
        ) latest
        ON latest.fixture_id = o.fixture_id
        AND latest.market = o.market
        AND latest.selection = o.selection
        AND latest.captured_at = o.captured_at
        ORDER BY o.fixture_id, o.selection
        """
    )
    state = {
        "account": PaperBroker(db).account_summary(),
        "fixtures": fixtures,
        "predictions": predictions,
        "decisions": decisions,
        "paper_bets": bets,
        "events": events,
        "latest_odds": odds,
        "week1": {
            "cricsheet": cricsheet_summary or {},
            "competitions": competitions,
            "elo": latest_elo_report(db),
        },
        "week2": {
            "logistic": latest_week2_report(db),
        },
        "week3": latest_week3_report(db),
        "week4": latest_week4_report(db),
        "backtesting": latest_backtest_report(db),
        "readiness": portfolio_readiness_report(db),
        "scheduler": _scheduler_state(db),
    }
    state["charts"] = build_all_charts(db, state)
    return state


def _scheduler_state(db: Database) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM scheduler_state WHERE id = 1")
    if not row or not row["last_tick_at"]:
        return {"enabled": SETTINGS.scheduler_enabled, "alive": False}
    last_tick = datetime.fromisoformat(str(row["last_tick_at"]).replace("Z", "+00:00"))
    alive = (datetime.now(timezone.utc) - last_tick).total_seconds() <= 2 * SETTINGS.scheduler_tick_seconds
    return dict(row) | {"enabled": SETTINGS.scheduler_enabled, "alive": alive}
