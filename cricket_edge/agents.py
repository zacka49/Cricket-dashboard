from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import SETTINGS
from .database import Database, utc_now
from .llm import LocalLLMClient
from .paper_broker import PaperBroker
from .risk import evaluate_candidate


class DataStewardAgent:
    name = "data_steward"
    role_title = "Chief Data Officer"

    def __init__(self, db: Database) -> None:
        self.db = db

    def run(self) -> dict[str, Any]:
        fixtures = self.db.query_one("SELECT COUNT(*) AS count FROM fixtures")
        odds = self.db.query_one("SELECT COUNT(*) AS count FROM odds_snapshots")
        predictions = self.db.query_one("SELECT COUNT(*) AS count FROM predictions")
        issues: list[str] = []
        if not fixtures or fixtures["count"] == 0:
            issues.append("No fixtures loaded.")
        if not odds or odds["count"] == 0:
            issues.append("No odds snapshots loaded.")
        if predictions and predictions["count"] == 0:
            issues.append("No predictions generated.")

        decision = "healthy" if not issues else "needs_attention"
        reason = "Data pipeline is ready." if not issues else " ".join(issues)
        payload = {
            "fixtures": int(fixtures["count"] if fixtures else 0),
            "odds_snapshots": int(odds["count"] if odds else 0),
            "predictions": int(predictions["count"] if predictions else 0),
            "issues": issues,
        }
        self._record(None, decision, 0, 0.9 if not issues else 0.4, reason, payload)
        return payload | {"decision": decision, "reason": reason}

    def _record(
        self,
        fixture_id: int | None,
        decision: str,
        stake: float,
        confidence: float,
        reason: str,
        payload: dict[str, Any],
    ) -> int:
        return self.db.execute(
            """
            INSERT INTO agent_decisions(
                fixture_id, agent_name, generated_at, decision, stake, confidence, reason, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (fixture_id, self.name, utc_now(), decision, stake, confidence, reason, json.dumps(payload, sort_keys=True)),
        )


class BetDecisionAgent:
    name = "bet_decision_agent"
    role_title = "Trading Desk"

    def __init__(self, db: Database, llm: LocalLLMClient | None = None) -> None:
        self.db = db
        self.llm = llm or LocalLLMClient()
        self.broker = PaperBroker(db)

    def evaluate(self) -> list[dict[str, Any]]:
        """Proposes decisions for open predictions without placing any bets.

        Side-effect-free w.r.t. paper_bets: callers must route the result
        through an oversight step (see PortfolioOversightAgent) and then
        execute() before any bet actually gets placed.
        """
        predictions = self.db.query(
            """
            SELECT p.*, f.match_date, f.start_time, f.competition, f.team_a, f.team_b, f.venue
            FROM predictions p
            JOIN fixtures f ON f.id = p.fixture_id
            WHERE f.status IN ('scheduled', 'live')
            ORDER BY p.edge DESC, p.confidence DESC
            """
        )
        account = self.broker.account_summary()
        decisions: list[dict[str, Any]] = []
        open_exposure = float(account["open_exposure"])
        for prediction in predictions:
            if self.broker.fixture_market_has_open_bet(int(prediction["fixture_id"]), prediction["market"]):
                continue
            risk = evaluate_candidate(prediction, float(account["bankroll"]), open_exposure)
            llm_reason = self._llm_reason(prediction, risk)
            reason = llm_reason or _fallback_reason(prediction, risk)
            decision = {
                "fixture_id": prediction["fixture_id"],
                "decision": risk["decision"],
                "stake": risk["stake"],
                "confidence": prediction["confidence"],
                "reason": reason,
                "risk": risk,
                "prediction": prediction,
            }
            decision_id = self._record(prediction, decision)
            decision["decision_id"] = decision_id
            if decision["decision"] == "paper_bet":
                open_exposure += float(decision["stake"])
            decisions.append(decision)
        self.db.log_event("agent", f"Bet Decision Agent evaluated {len(decisions)} candidates.")
        return decisions

    def execute(self, decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Places bets for decisions an oversight step has approved.

        A decision with no oversight verdict, or a 'vetoed' one, is never
        placed -- oversight approval is required, not just a proposed
        'paper_bet' decision.
        """
        placed: list[dict[str, Any]] = []
        for decision in decisions:
            if decision["decision"] != "paper_bet":
                continue
            if decision.get("oversight", {}).get("status") != "approved":
                continue
            bet_id = self.broker.place_bet(decision, decision["prediction"])
            decision["bet_id"] = bet_id
            if bet_id:
                placed.append(decision)
        self.db.log_event("agent", f"Bet Decision Agent placed {len(placed)} paper bets.")
        return placed

    def run(self) -> list[dict[str, Any]]:
        """Convenience wrapper: evaluate -> oversight review -> execute."""
        proposals = self.evaluate()
        reviewed = PortfolioOversightAgent(self.db).review(proposals)
        self.execute(reviewed)
        return reviewed

    def _llm_reason(self, prediction: dict[str, Any], risk: dict[str, Any]) -> str:
        context = {
            "match": f"{prediction['team_a']} vs {prediction['team_b']}",
            "competition": prediction["competition"],
            "venue": prediction["venue"],
            "selection": prediction["selection"],
            "model_probability": prediction["probability"],
            "fair_odds": prediction["fair_odds"],
            "market_odds": prediction["market_odds"],
            "edge": prediction["edge"],
            "confidence": prediction["confidence"],
            "risk_decision": risk,
        }
        result = self.llm.generate_json(
            "You are a conservative paper-betting analyst. Do not invent stats. Explain decisions from the JSON context only.",
            json.dumps(context, sort_keys=True),
        )
        if not result.ok or not result.data:
            return ""
        return str(result.data.get("reason", "")).strip()[:500]

    def _record(self, prediction: dict[str, Any], decision: dict[str, Any]) -> int:
        return self.db.execute(
            """
            INSERT INTO agent_decisions(
                fixture_id, agent_name, generated_at, decision, stake, confidence, reason, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prediction["fixture_id"],
                self.name,
                utc_now(),
                decision["decision"],
                decision["stake"],
                float(decision["confidence"]),
                decision["reason"],
                json.dumps({"prediction": dict(prediction), "risk": decision["risk"]}, sort_keys=True, default=str),
            ),
        )


class PortfolioOversightAgent:
    """Sits between BetDecisionAgent.evaluate() and .execute(), able to veto
    an individual proposed bet -- the coordination point where one agent's
    output can be overridden by another, with its own audit trail row."""

    name = "portfolio_oversight_agent"
    role_title = "Chief Risk Officer"

    def __init__(self, db: Database, portfolio_cap_fraction: float | None = None) -> None:
        self.db = db
        self.portfolio_cap_fraction = portfolio_cap_fraction

    def review(self, proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        needs_attention = self._data_steward_needs_attention()
        cap_fraction = (
            self.portfolio_cap_fraction
            if self.portfolio_cap_fraction is not None
            else SETTINGS.max_portfolio_run_exposure_fraction
        )
        bankroll = PaperBroker(self.db).account_summary()["bankroll"]
        cap = bankroll * cap_fraction
        running_total = 0.0
        for proposal in proposals:
            if proposal["decision"] != "paper_bet":
                proposal["oversight"] = {"status": "not_applicable"}
                continue
            if needs_attention:
                self._veto(
                    proposal,
                    "Data Steward flagged needs_attention; oversight blocks new paper bets this run.",
                )
                continue
            running_total += float(proposal["stake"])
            if running_total > cap:
                self._veto(
                    proposal,
                    f"Portfolio-level run cap of GBP {cap:.2f} exceeded by this run's proposed bets; bet vetoed.",
                )
                continue
            proposal["oversight"] = {"status": "approved"}
        return proposals

    def _data_steward_needs_attention(self) -> bool:
        row = self.db.query_one(
            """
            SELECT decision FROM agent_decisions
            WHERE agent_name = ?
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            (DataStewardAgent.name,),
        )
        return bool(row and row["decision"] == "needs_attention")

    def _veto(self, proposal: dict[str, Any], reason: str) -> None:
        decision_id = self.db.execute(
            """
            INSERT INTO agent_decisions(
                fixture_id, agent_name, generated_at, decision, stake, confidence, reason, payload_json
            )
            VALUES (?, ?, ?, 'veto', 0, ?, ?, ?)
            """,
            (
                proposal["fixture_id"],
                self.name,
                utc_now(),
                float(proposal["confidence"]),
                reason,
                json.dumps(
                    {"source_decision_id": proposal.get("decision_id"), "proposed_stake": proposal["stake"]},
                    sort_keys=True,
                ),
            ),
        )
        proposal["oversight"] = {"status": "vetoed", "reason": reason, "oversight_decision_id": decision_id}


class MarketWatchAgent:
    name = "market_watch_agent"
    role_title = "Trading Desk — Position Monitoring"

    def __init__(self, db: Database) -> None:
        self.db = db
        self.broker = PaperBroker(db)

    def run(self) -> list[dict[str, Any]]:
        open_bets = self.db.query(
            """
            SELECT b.*, f.team_a, f.team_b, f.competition
            FROM paper_bets b
            JOIN fixtures f ON f.id = b.fixture_id
            WHERE b.status = 'open'
            ORDER BY b.placed_at
            """
        )
        actions: list[dict[str, Any]] = []
        for bet in open_bets:
            latest = self.db.query_one(
                """
                SELECT odds FROM odds_snapshots
                WHERE fixture_id = ? AND market = ? AND selection = ?
                ORDER BY captured_at DESC, id DESC
                LIMIT 1
                """,
                (bet["fixture_id"], bet["market"], bet["selection"]),
            )
            if not latest:
                continue
            entry = float(bet["odds"])
            current = float(latest["odds"])
            move = (current - entry) / entry
            action = "hold"
            reason = "Market move is within the normal hold band."
            if move <= -0.16:
                action = "cash_out"
                reason = "Price has shortened materially; simulated hedge locks in paper profit."
                self.broker.cash_out_bet(int(bet["id"]), reason)
            elif move >= 0.22:
                action = "cash_out"
                reason = "Price has drifted materially; simulated stop-loss reduces paper exposure."
                self.broker.cash_out_bet(int(bet["id"]), reason)
            payload = {"bet_id": bet["id"], "entry_odds": entry, "current_odds": current, "move": round(move, 4)}
            decision_id = self._record(int(bet["fixture_id"]), action, reason, payload)
            actions.append(payload | {"action": action, "reason": reason, "decision_id": decision_id})
        self.db.log_event("agent", f"Market Watch Agent checked {len(open_bets)} open bets.")
        return actions

    def _record(self, fixture_id: int, decision: str, reason: str, payload: dict[str, Any]) -> int:
        return self.db.execute(
            """
            INSERT INTO agent_decisions(
                fixture_id, agent_name, generated_at, decision, stake, confidence, reason, payload_json
            )
            VALUES (?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (fixture_id, self.name, utc_now(), decision, 0.75, reason, json.dumps(payload, sort_keys=True)),
        )


class ReportWriterAgent:
    name = "report_writer_agent"
    role_title = "Chief Operating Officer"

    def __init__(self, db: Database) -> None:
        self.db = db

    def daily_briefing(self) -> dict[str, Any]:
        account = PaperBroker(self.db).account_summary()
        top_edges = self.db.query(
            """
            SELECT p.*, f.team_a, f.team_b, f.competition, f.venue, f.start_time
            FROM predictions p
            JOIN fixtures f ON f.id = p.fixture_id
            WHERE f.status IN ('scheduled', 'live')
            ORDER BY p.edge DESC
            LIMIT 5
            """
        )
        open_bets = self.db.query("SELECT COUNT(*) AS count FROM paper_bets WHERE status = 'open'")[0]["count"]
        lines = [
            f"Paper bankroll: GBP {account['bankroll']:.2f}; open exposure: GBP {account['open_exposure']:.2f}.",
            f"Open paper bets: {open_bets}. Top model edges are ranked below; hard risk rules still decide execution.",
        ]
        for row in top_edges[:3]:
            lines.append(
                f"{row['selection']} in {row['team_a']} vs {row['team_b']}: edge {float(row['edge']):.1%}, "
                f"fair {float(row['fair_odds']):.2f}, market {float(row['market_odds']):.2f}."
            )
        payload = {"briefing": lines, "generated_at": datetime.now(timezone.utc).isoformat()}
        self.db.execute(
            """
            INSERT INTO agent_decisions(
                fixture_id, agent_name, generated_at, decision, stake, confidence, reason, payload_json
            )
            VALUES (NULL, ?, ?, 'briefing', 0, 0.8, ?, ?)
            """,
            (self.name, utc_now(), "Generated daily paper-trading briefing.", json.dumps(payload, sort_keys=True)),
        )
        return payload


def _fallback_reason(prediction: dict[str, Any], risk: dict[str, Any]) -> str:
    if risk["decision"] == "paper_bet":
        return (
            f"Paper bet allowed: model edge {float(prediction['edge']):.1%}, "
            f"confidence {float(prediction['confidence']):.1%}, market {float(prediction['market_odds']):.2f} "
            f"vs fair {float(prediction['fair_odds']):.2f}."
        )
    return "Skipped by hard rules: " + "; ".join(risk["risk_reasons"])
