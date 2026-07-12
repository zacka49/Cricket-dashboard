import json
from pathlib import Path

from cricket_edge.pipeline import (
    BetEvaluator,
    BriefingWriter,
    DataHealthCheck,
    PositionMonitor,
    RiskGate,
)
from cricket_edge.database import Database, utc_now


def _insert_fixture(
    db: Database, team_a: str, team_b: str, match_date: str = "2026-01-01", source: str = "bet365"
) -> int:
    return db.execute(
        """
        INSERT INTO fixtures(
            match_date, start_time, competition, format, team_a, team_b, venue,
            status, source, created_at
        )
        VALUES (?, '09:00', 'Test League', 'T20', ?, ?, 'Test Ground', 'scheduled', ?, ?)
        """,
        (match_date, team_a, team_b, source, utc_now()),
    )


def _insert_prediction(
    db: Database,
    fixture_id: int,
    selection: str,
    probability: float = 0.65,
    fair_odds: float = 1.54,
    market_odds: float = 2.0,
    edge: float = 0.05,
    confidence: float = 0.65,
    market_source: str = "bet365",
    market_is_fresh: bool = True,
) -> int:
    features = {
        "market_source": market_source,
        "market_captured_at": utc_now(),
        "market_status": "fresh" if market_is_fresh else "stale",
        "market_is_fresh": market_is_fresh,
        "market_stale_after_minutes": 30,
        "weather_penalty": 0.0,
    }
    return db.execute(
        """
        INSERT INTO predictions(
            fixture_id, model_name, generated_at, market, selection,
            probability, fair_odds, market_odds, edge, confidence, features_json
        )
        VALUES (?, 'test_model', ?, 'match_winner', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fixture_id,
            utc_now(),
            selection,
            probability,
            fair_odds,
            market_odds,
            edge,
            confidence,
            json.dumps(features),
        ),
    )


def _insert_odds_snapshot(db: Database, fixture_id: int, selection: str, odds: float, source: str = "bet365") -> None:
    db.execute(
        """
        INSERT INTO odds_snapshots(fixture_id, market, selection, odds, source, captured_at)
        VALUES (?, 'match_winner', ?, ?, ?, ?)
        """,
        (fixture_id, selection, odds, source, utc_now()),
    )


def _place_open_bet(db: Database, fixture_id: int, selection: str, odds: float, stake: float = 10.0) -> int:
    return db.execute(
        """
        INSERT INTO paper_bets(
            fixture_id, decision_id, market, selection, stake, odds, status, placed_at, notes
        )
        VALUES (?, NULL, 'match_winner', ?, ?, ?, 'open', ?, '')
        """,
        (fixture_id, selection, stake, odds, utc_now()),
    )


def _insert_decision_log(db: Database, source: str, decision: str) -> None:
    db.execute(
        """
        INSERT INTO decision_log(
            fixture_id, source, generated_at, decision, stake, confidence, reason, payload_json
        )
        VALUES (NULL, ?, ?, ?, 0, 0, 'seeded for test', '{}')
        """,
        (source, utc_now(), decision),
    )


# --- DataHealthCheck ---------------------------------------------------------


def test_data_health_check_reports_healthy_with_data(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta")
    _insert_odds_snapshot(db, fixture_id, "Alpha", 2.0)
    _insert_prediction(db, fixture_id, "Alpha")

    result = DataHealthCheck(db).run()

    assert result["decision"] == "healthy"
    assert result["issues"] == []
    row = db.query_one("SELECT * FROM decision_log WHERE source = 'data_health_check' ORDER BY id DESC LIMIT 1")
    assert row["decision"] == "healthy"


def test_data_health_check_reports_needs_attention_when_empty(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()

    result = DataHealthCheck(db).run()

    assert result["decision"] == "needs_attention"
    assert "No fixtures loaded." in result["issues"]
    assert "No odds snapshots loaded." in result["issues"]
    assert "No predictions generated." in result["issues"]


# --- BetEvaluator: evaluate()/execute() split -------------------------------


def test_evaluate_proposes_without_placing_a_bet(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta")
    _insert_prediction(db, fixture_id, "Alpha")

    decisions = BetEvaluator(db).evaluate()

    assert len(decisions) == 1
    assert decisions[0]["decision"] == "paper_bet"
    assert decisions[0]["stake"] > 0
    assert "prediction" in decisions[0]
    assert db.query("SELECT * FROM paper_bets") == []
    recorded = db.query("SELECT * FROM decision_log WHERE source = 'bet_evaluator'")
    assert len(recorded) == 1


def test_evaluate_skips_candidates_without_real_odds(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta", source="demo-market")
    _insert_prediction(db, fixture_id, "Alpha", market_source="demo-market", market_is_fresh=False)

    decisions = BetEvaluator(db).evaluate()

    assert decisions[0]["decision"] == "skip"
    assert "no fresh real bookmaker odds" in decisions[0]["risk"]["risk_reasons"]


def test_execute_places_bet_only_when_oversight_approved(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta")
    _insert_prediction(db, fixture_id, "Alpha")
    evaluator = BetEvaluator(db)
    decisions = evaluator.evaluate()
    decisions[0]["oversight"] = {"status": "approved"}

    placed = evaluator.execute(decisions)

    assert len(placed) == 1
    bets = db.query("SELECT * FROM paper_bets")
    assert len(bets) == 1
    assert bets[0]["selection"] == "Alpha"


def test_execute_does_not_place_bet_when_vetoed(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta")
    _insert_prediction(db, fixture_id, "Alpha")
    evaluator = BetEvaluator(db)
    decisions = evaluator.evaluate()
    decisions[0]["oversight"] = {"status": "vetoed", "reason": "test veto"}

    placed = evaluator.execute(decisions)

    assert placed == []
    assert db.query("SELECT * FROM paper_bets") == []


def test_run_wrapper_places_bet_end_to_end_when_nothing_vetoes_it(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta")
    _insert_prediction(db, fixture_id, "Alpha")

    reviewed = BetEvaluator(db).run()

    assert reviewed[0]["oversight"]["status"] == "approved"
    assert len(db.query("SELECT * FROM paper_bets")) == 1


# --- RiskGate -----------------------------------------------------------------


def test_risk_gate_vetoes_all_bets_when_data_health_needs_attention(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta")
    _insert_decision_log(db, "data_health_check", "needs_attention")
    proposal = {"fixture_id": fixture_id, "decision": "paper_bet", "stake": 8.0, "confidence": 0.7, "decision_id": 999}

    reviewed = RiskGate(db).review([proposal])

    assert reviewed[0]["oversight"]["status"] == "vetoed"
    veto_rows = db.query("SELECT * FROM decision_log WHERE source = 'risk_gate'")
    assert len(veto_rows) == 1
    assert veto_rows[0]["decision"] == "veto"
    payload = json.loads(veto_rows[0]["payload_json"])
    assert payload["source_decision_id"] == 999


def test_risk_gate_vetoes_overflow_beyond_portfolio_cap(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta")
    proposals = [
        {"fixture_id": fixture_id, "decision": "paper_bet", "stake": 8.0, "confidence": 0.7, "decision_id": 1},
        {"fixture_id": fixture_id, "decision": "paper_bet", "stake": 8.0, "confidence": 0.7, "decision_id": 2},
    ]

    reviewed = RiskGate(db, portfolio_cap_fraction=0.01).review(proposals)

    assert reviewed[0]["oversight"]["status"] == "approved"
    assert reviewed[1]["oversight"]["status"] == "vetoed"
    veto_rows = db.query("SELECT * FROM decision_log WHERE source = 'risk_gate'")
    assert len(veto_rows) == 1


def test_risk_gate_approves_proposals_under_the_cap(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta")
    proposal = {"fixture_id": fixture_id, "decision": "paper_bet", "stake": 5.0, "confidence": 0.7, "decision_id": 1}

    reviewed = RiskGate(db).review([proposal])

    assert reviewed[0]["oversight"]["status"] == "approved"
    assert db.query("SELECT * FROM decision_log WHERE source = 'risk_gate'") == []


def test_risk_gate_marks_non_bet_decisions_not_applicable(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta")
    proposal = {"fixture_id": fixture_id, "decision": "skip", "stake": 0.0, "confidence": 0.4, "decision_id": 1}

    reviewed = RiskGate(db).review([proposal])

    assert reviewed[0]["oversight"]["status"] == "not_applicable"


# --- PositionMonitor ----------------------------------------------------------


def test_position_monitor_cashes_out_on_material_shorten(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta")
    bet_id = _place_open_bet(db, fixture_id, "Alpha", odds=2.0)
    _insert_odds_snapshot(db, fixture_id, "Alpha", 1.6)

    actions = PositionMonitor(db).run()

    assert actions[0]["action"] == "cash_out"
    bet = db.query_one("SELECT * FROM paper_bets WHERE id = ?", (bet_id,))
    assert bet["status"] == "cashed_out"


def test_position_monitor_cashes_out_on_material_drift(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta")
    bet_id = _place_open_bet(db, fixture_id, "Alpha", odds=2.0)
    _insert_odds_snapshot(db, fixture_id, "Alpha", 2.5)

    actions = PositionMonitor(db).run()

    assert actions[0]["action"] == "cash_out"
    bet = db.query_one("SELECT * FROM paper_bets WHERE id = ?", (bet_id,))
    assert bet["status"] == "cashed_out"


def test_position_monitor_holds_on_small_move(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta")
    bet_id = _place_open_bet(db, fixture_id, "Alpha", odds=2.0)
    _insert_odds_snapshot(db, fixture_id, "Alpha", 2.05)

    actions = PositionMonitor(db).run()

    assert actions[0]["action"] == "hold"
    bet = db.query_one("SELECT * FROM paper_bets WHERE id = ?", (bet_id,))
    assert bet["status"] == "open"


# --- BriefingWriter ------------------------------------------------------------


def test_daily_briefing_mentions_top_edges_and_records_a_decision(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta")
    _insert_prediction(db, fixture_id, "Alpha", edge=0.09)

    payload = BriefingWriter(db).daily_briefing()

    assert any("Paper bankroll" in line for line in payload["briefing"])
    assert any("Alpha" in line and "Beta" in line for line in payload["briefing"])
    row = db.query_one("SELECT * FROM decision_log WHERE source = 'briefing_writer' ORDER BY id DESC LIMIT 1")
    assert row["decision"] == "briefing"
