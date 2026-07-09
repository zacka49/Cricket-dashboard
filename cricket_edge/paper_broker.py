from __future__ import annotations

from datetime import date
from typing import Any

from .database import Database, utc_now
from .match_linkage import link_fixture_to_cricsheet, resolve_winner_for_fixture


class PaperBroker:
    def __init__(self, db: Database) -> None:
        self.db = db

    def account_summary(self) -> dict[str, float]:
        account = self.db.query_one("SELECT starting_bankroll FROM paper_account WHERE id = 1")
        starting = float(account["starting_bankroll"]) if account else 1000.0
        settled = self.db.query_one("SELECT COALESCE(SUM(pnl), 0) AS pnl FROM paper_bets WHERE status IN ('settled', 'cashed_out')")
        open_exposure = self.db.query_one("SELECT COALESCE(SUM(stake), 0) AS exposure FROM paper_bets WHERE status = 'open'")
        open_count = self.db.query_one("SELECT COUNT(*) AS count FROM paper_bets WHERE status = 'open'")
        total_pnl = float(settled["pnl"] or 0)
        exposure = float(open_exposure["exposure"] or 0)
        bankroll = starting + total_pnl
        return {
            "starting_bankroll": round(starting, 2),
            "bankroll": round(bankroll, 2),
            "available": round(bankroll - exposure, 2),
            "open_exposure": round(exposure, 2),
            "settled_pnl": round(total_pnl, 2),
            "open_bets": int(open_count["count"] or 0),
        }

    def already_has_open_bet(self, fixture_id: int, market: str, selection: str) -> bool:
        row = self.db.query_one(
            """
            SELECT id FROM paper_bets
            WHERE fixture_id = ? AND market = ? AND selection = ? AND status = 'open'
            LIMIT 1
            """,
            (fixture_id, market, selection),
        )
        return bool(row)

    def fixture_market_has_open_bet(self, fixture_id: int, market: str) -> bool:
        row = self.db.query_one(
            """
            SELECT id FROM paper_bets
            WHERE fixture_id = ? AND market = ? AND status = 'open'
            LIMIT 1
            """,
            (fixture_id, market),
        )
        return bool(row)

    def place_bet(self, decision: dict[str, Any], prediction: dict[str, Any]) -> int | None:
        stake = float(decision.get("stake", 0))
        if stake <= 0:
            return None
        fixture_id = int(prediction["fixture_id"])
        market = prediction["market"]
        selection = prediction["selection"]
        if self.already_has_open_bet(fixture_id, market, selection):
            return None
        bet_id = self.db.execute(
            """
            INSERT INTO paper_bets(
                fixture_id, decision_id, market, selection, stake, odds,
                status, placed_at, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (
                fixture_id,
                decision.get("decision_id"),
                market,
                selection,
                round(stake, 2),
                float(prediction["market_odds"]),
                utc_now(),
                decision.get("reason", ""),
            ),
        )
        self.db.log_event("broker", f"Placed paper bet on {selection} at {prediction['market_odds']}.", {"bet_id": bet_id})
        return bet_id

    def cash_out_bet(self, bet_id: int, reason: str) -> None:
        bet = self.db.query_one("SELECT * FROM paper_bets WHERE id = ? AND status = 'open'", (bet_id,))
        if not bet:
            return
        latest_odds = self._latest_odds(int(bet["fixture_id"]), bet["market"], bet["selection"]) or float(bet["odds"])
        pnl = float(bet["stake"]) * ((float(bet["odds"]) / latest_odds) - 1)
        self.db.execute(
            """
            UPDATE paper_bets
            SET status = 'cashed_out', closed_at = ?, pnl = ?, cashout_value = ?, notes = ?
            WHERE id = ?
            """,
            (utc_now(), round(pnl, 2), round(pnl, 2), reason, bet_id),
        )
        self.db.log_event("broker", f"Cashed out paper bet #{bet_id}.", {"pnl": round(pnl, 2), "reason": reason})

    def settle_due_bets(self) -> dict[str, int]:
        """Settles paper bets against real Cricsheet results only.

        A bet never gets a fabricated winner: if Cricsheet hasn't caught up with
        the real match yet, it stays 'open'. A linked match with no winner (tie,
        no-result, abandoned) settles as void (pnl = 0), which is distinct from
        "not resolved yet".
        """
        open_bets = self.db.query(
            """
            SELECT b.*, f.team_a, f.team_b, f.match_date
            FROM paper_bets b
            JOIN fixtures f ON f.id = b.fixture_id
            WHERE b.status = 'open'
            """
        )
        settled = voided = still_awaiting_result = 0
        for bet in open_bets:
            if date.fromisoformat(bet["match_date"]) > date.today():
                continue
            match = link_fixture_to_cricsheet(
                self.db, int(bet["fixture_id"]), bet["team_a"], bet["team_b"], bet["match_date"]
            )
            if not match:
                still_awaiting_result += 1
                continue
            winner = resolve_winner_for_fixture(bet["team_a"], bet["team_b"], match)
            if winner is None:
                pnl = 0.0
                notes = f"Voided: linked Cricsheet match {match['match_id']} had no winner (tie/no result)."
                voided += 1
            else:
                pnl = float(bet["stake"]) * (float(bet["odds"]) - 1) if bet["selection"] == winner else -float(bet["stake"])
                notes = f"Settled from Cricsheet match {match['match_id']}. Real winner: {winner}"
                settled += 1
            self.db.execute(
                """
                UPDATE paper_bets
                SET status = 'settled', closed_at = ?, pnl = ?, notes = ?
                WHERE id = ?
                """,
                (utc_now(), round(pnl, 2), notes, bet["id"]),
            )
            self.db.execute(
                """
                UPDATE fixtures SET status = 'complete', result_winner = ?
                WHERE id = ? AND status != 'complete'
                """,
                (winner, bet["fixture_id"]),
            )
            self.db.log_event(
                "settlement",
                f"Settled paper bet #{bet['id']} from Cricsheet match {match['match_id']} (winner: {winner}).",
                {"pnl": round(pnl, 2), "match_id": match["match_id"], "voided": winner is None},
            )
        return {"settled": settled, "voided": voided, "still_open_awaiting_result": still_awaiting_result}

    def _latest_odds(self, fixture_id: int, market: str, selection: str) -> float | None:
        row = self.db.query_one(
            """
            SELECT odds FROM odds_snapshots
            WHERE fixture_id = ? AND market = ? AND selection = ?
            ORDER BY captured_at DESC, id DESC
            LIMIT 1
            """,
            (fixture_id, market, selection),
        )
        return float(row["odds"]) if row else None
