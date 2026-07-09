from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .config import SETTINGS


APPROVED_REAL_ODDS_SOURCES = {"bet365", "the_odds_api"}


@dataclass(frozen=True)
class RiskPolicy:
    min_edge: float = SETTINGS.min_edge
    min_confidence: float = SETTINGS.min_confidence
    max_stake_fraction: float = SETTINGS.max_stake_fraction
    max_daily_exposure_fraction: float = SETTINGS.max_daily_exposure_fraction


def fractional_kelly(probability: float, odds: float, bankroll: float, fraction: float = 0.25) -> float:
    b = odds - 1
    if b <= 0:
        return 0.0
    kelly = ((probability * b) - (1 - probability)) / b
    return max(0.0, bankroll * kelly * fraction)


def evaluate_candidate(
    prediction: dict[str, Any],
    bankroll: float,
    open_exposure: float,
    policy: RiskPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or RiskPolicy()
    probability = float(prediction["probability"])
    market_odds = float(prediction["market_odds"])
    edge = float(prediction["edge"])
    confidence = float(prediction["confidence"])
    features = _prediction_features(prediction)

    reasons: list[str] = []
    if features.get("market_source") not in APPROVED_REAL_ODDS_SOURCES:
        reasons.append("no fresh real bookmaker odds")
    elif not bool(features.get("market_is_fresh")):
        reasons.append(str(features.get("market_status") or "stale real bookmaker odds"))
    if edge < policy.min_edge:
        reasons.append(f"edge {edge:.1%} below minimum {policy.min_edge:.1%}")
    if confidence < policy.min_confidence:
        reasons.append(f"confidence {confidence:.1%} below minimum {policy.min_confidence:.1%}")
    if market_odds <= 1.01:
        reasons.append("invalid market odds")

    max_stake = bankroll * policy.max_stake_fraction
    max_exposure = bankroll * policy.max_daily_exposure_fraction
    if open_exposure >= max_exposure:
        reasons.append("daily exposure limit already reached")

    raw_stake = fractional_kelly(probability, market_odds, bankroll, 0.25)
    stake = min(raw_stake, max_stake, max(0.0, max_exposure - open_exposure))
    if stake < 1.0:
        reasons.append("calculated stake below paper minimum")

    decision = "paper_bet" if not reasons else "skip"
    return {
        "decision": decision,
        "stake": round(stake, 2) if decision == "paper_bet" else 0.0,
        "risk_reasons": reasons,
        "policy": {
            "min_edge": policy.min_edge,
            "min_confidence": policy.min_confidence,
            "max_stake_fraction": policy.max_stake_fraction,
            "max_daily_exposure_fraction": policy.max_daily_exposure_fraction,
        },
    }


def _prediction_features(prediction: dict[str, Any]) -> dict[str, Any]:
    raw = prediction.get("features_json") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
