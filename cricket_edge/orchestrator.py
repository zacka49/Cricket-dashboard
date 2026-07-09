from __future__ import annotations

from typing import Any

from .agents import (
    BetDecisionAgent,
    DataStewardAgent,
    MarketWatchAgent,
    PortfolioOversightAgent,
    ReportWriterAgent,
)
from .advanced_models import latest_week3_report, train_week3_models
from .backtesting import latest_backtest_report, run_latest_strategy_backtest
from .charts import build_all_charts
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
        odds_refresh = self.fetch_bet365_odds()
        data_status = DataStewardAgent(self.db).run()
        predictions = PredictionEngine(self.db).run_for_open_fixtures()
        bet_agent = BetDecisionAgent(self.db)
        proposals = bet_agent.evaluate()
        reviewed = PortfolioOversightAgent(self.db).review(proposals)
        placed = bet_agent.execute(reviewed)
        briefing = ReportWriterAgent(self.db).daily_briefing()
        return {
            "odds_refresh": odds_refresh,
            "data_status": data_status,
            "predictions": len(predictions),
            "decisions": len(reviewed),
            "bets_placed": len(placed),
            "briefing": briefing,
            "account": PaperBroker(self.db).account_summary(),
        }

    def monitor_tick(self) -> dict[str, Any]:
        odds_refresh = self.fetch_bet365_odds()
        simulate_market_move(self.db)
        predictions = PredictionEngine(self.db).run_for_open_fixtures()
        actions = MarketWatchAgent(self.db).run()
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
        return train_week3_models(self.db)

    def run_week4_market(self) -> dict[str, Any]:
        result = run_week4_market_build(self.db)
        result["strategy_backtest"] = run_latest_strategy_backtest(self.db)
        return result

    def fetch_bet365_odds(self) -> dict[str, Any]:
        return fetch_bet365_cricket_odds(self.db)

    def pull_live_data(self) -> dict[str, Any]:
        return pull_all_live_data(self.db)

    def state(self) -> dict[str, Any]:
        return build_state(self.db)

    def reset_demo(self) -> dict[str, Any]:
        self.db.execute("DELETE FROM paper_bets")
        self.db.execute("DELETE FROM agent_decisions")
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
        FROM agent_decisions d
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
    }
    state["charts"] = build_all_charts(db, state)
    return state
