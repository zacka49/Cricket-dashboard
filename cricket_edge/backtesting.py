from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .database import Database, utc_now


@dataclass(frozen=True)
class StrategyBacktestConfig:
    min_edge: float = 0.03
    stake: float = 10.0
    split: str = "test"


def run_latest_strategy_backtest(db: Database) -> dict[str, Any]:
    model_name = _active_or_latest_model(db)
    if not model_name:
        return _empty_result("No trained model predictions are available.")
    return run_strategy_backtest(db, model_name=model_name)


def run_strategy_backtest(
    db: Database,
    model_name: str,
    min_edge: float = 0.03,
    stake: float = 10.0,
    split: str = "test",
) -> dict[str, Any]:
    db.init_schema()
    config = StrategyBacktestConfig(min_edge=min_edge, stake=stake, split=split)
    candidates = _historical_candidates(db, model_name, split)
    bets: list[dict[str, Any]] = []
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for row in candidates:
        edge = float(row["pred_a"]) - float(row["market_probability"])
        if edge < config.min_edge:
            continue
        win = float(row["result_a"]) == 1.0
        pnl = config.stake * (float(row["decimal_odds"]) - 1.0) if win else -config.stake
        cumulative += pnl
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
        bets.append(
            {
                "match_id": row["match_id"],
                "match_date": row["match_date"],
                "competition": row["competition"],
                "selection": row["team_a"],
                "opponent": row["team_b"],
                "model_probability": round(float(row["pred_a"]), 6),
                "market_probability": round(float(row["market_probability"]), 6),
                "edge": round(edge, 6),
                "decimal_odds": round(float(row["decimal_odds"]), 4),
                "stake": round(config.stake, 2),
                "pnl": round(pnl, 2),
                "result": "win" if win else "loss",
                "source": row["market_source"],
                "captured_at": row["captured_at"],
            }
        )

    wins = sum(1 for bet in bets if bet["result"] == "win")
    staked = round(config.stake * len(bets), 2)
    pnl = round(sum(float(bet["pnl"]) for bet in bets), 2)
    roi = round(pnl / staked, 6) if staked else 0.0
    payload = {
        "model_name": model_name,
        "generated_at": utc_now(),
        "config": config.__dict__,
        "n_candidates": len(candidates),
        "bets": len(bets),
        "wins": wins,
        "win_rate": round(wins / len(bets), 6) if bets else 0.0,
        "staked": staked,
        "pnl": pnl,
        "roi": roi,
        "yield": roi,
        "max_drawdown": round(max_drawdown, 2),
        "by_competition": _group_bets(bets, "competition"),
        "by_edge_bucket": _group_bets(bets, "edge_bucket"),
        "recent_bets": bets[-20:],
        "notes": [
            "Uses only model_predictions joined to historical market_baselines.",
            "A candidate is eligible only when the market baseline timestamp is on or before match date.",
            "This is paper research only; no real-money execution is represented.",
        ],
    }
    db.execute(
        """
        INSERT INTO backtest_runs(
            model_name, generated_at, n_candidates, bets, wins, staked, pnl,
            roi, yield, max_drawdown, payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            model_name,
            payload["generated_at"],
            payload["n_candidates"],
            payload["bets"],
            payload["wins"],
            payload["staked"],
            payload["pnl"],
            payload["roi"],
            payload["yield"],
            payload["max_drawdown"],
            json.dumps(payload, sort_keys=True),
        ),
    )
    db.log_event("backtest", f"Ran strategy backtest for {model_name}.", payload)
    return payload


def latest_backtest_report(db: Database) -> dict[str, Any]:
    row = db.query_one(
        """
        SELECT *
        FROM backtest_runs
        ORDER BY generated_at DESC, id DESC
        LIMIT 1
        """
    )
    if not row:
        return _empty_result("No strategy backtest has been run yet.")
    return {"latest_run": dict(row), "payload": _safe_json_loads(row["payload_json"])}


def _historical_candidates(db: Database, model_name: str, split: str) -> list[dict[str, Any]]:
    rows = db.query(
        """
        SELECT
            p.model_name, p.match_id, p.split, p.match_date, p.competition,
            p.team_a, p.team_b, p.winner, p.pred_a, p.result_a,
            m.probability AS market_probability, m.decimal_odds,
            m.source AS market_source, m.captured_at
        FROM model_predictions p
        JOIN market_baselines m
          ON m.match_id = p.match_id
         AND m.market = 'match_winner'
         AND m.selection = p.team_a
        WHERE p.model_name = ?
          AND p.split = ?
          AND date(m.captured_at) <= date(p.match_date)
          AND m.decimal_odds > 1.01
          AND m.source NOT IN ('app_fixture_odds')
        ORDER BY p.match_date, p.match_id, m.captured_at
        """,
        (model_name, split),
    )
    latest_by_match: dict[str, dict[str, Any]] = {}
    for row in rows:
        latest_by_match[str(row["match_id"])] = row
    return list(latest_by_match.values())


def _group_bets(bets: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for bet in bets:
        group_key = _edge_bucket(float(bet["edge"])) if key == "edge_bucket" else str(bet[key])
        grouped[group_key].append(bet)
    output = []
    for group_key, items in grouped.items():
        staked = sum(float(item["stake"]) for item in items)
        pnl = sum(float(item["pnl"]) for item in items)
        wins = sum(1 for item in items if item["result"] == "win")
        output.append(
            {
                key: group_key,
                "bets": len(items),
                "wins": wins,
                "staked": round(staked, 2),
                "pnl": round(pnl, 2),
                "roi": round(pnl / staked, 6) if staked else 0.0,
            }
        )
    return sorted(output, key=lambda item: str(item[key]))


def _edge_bucket(edge: float) -> str:
    if edge < 0.05:
        return "3-5%"
    if edge < 0.10:
        return "5-10%"
    if edge < 0.15:
        return "10-15%"
    return "15%+"


def _active_or_latest_model(db: Database) -> str:
    active = db.query_one("SELECT model_name FROM model_registry WHERE active = 1 LIMIT 1")
    if active:
        return str(active["model_name"])
    latest = db.query_one(
        """
        SELECT model_name
        FROM model_predictions
        GROUP BY model_name
        ORDER BY MAX(match_date) DESC
        LIMIT 1
        """
    )
    return str(latest["model_name"]) if latest else ""


def _empty_result(message: str) -> dict[str, Any]:
    return {
        "latest_run": {},
        "payload": {
            "bets": 0,
            "wins": 0,
            "staked": 0.0,
            "pnl": 0.0,
            "roi": 0.0,
            "yield": 0.0,
            "max_drawdown": 0.0,
            "message": message,
        },
    }


def _safe_json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "invalid_json"}
    return loaded if isinstance(loaded, dict) else {"value": loaded}
