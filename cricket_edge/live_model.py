from __future__ import annotations

import json
import math
from datetime import date
from typing import Any

from .database import Database
from .elo import EloConfig, current_team_elo_ratings
from .logistic_model import BASE_FEATURE_NAMES, PRETOSS_MODEL_NAME, current_team_stats


# Same team under a different label at the odds provider vs. Cricsheet. Verified by
# direct lookup against this project's own Cricsheet import, not guessed.
TEAM_NAME_ALIASES = {
    "Hong Kong, China": "Hong Kong",
    "Utd Arab Emirates": "United Arab Emirates",
    "USA": "United States of America",
}

MIN_MATCHES_FOR_FULL_CONFIDENCE = 20


def normalize_team_name(name: str) -> str:
    return TEAM_NAME_ALIASES.get(name, name)


def load_live_model_snapshot(db: Database, model_name: str = PRETOSS_MODEL_NAME) -> dict[str, Any] | None:
    """Latest trained coefficients/calibrator for a logistic model, plus current
    Elo ratings and cumulative team stats needed to build live features.

    Returns None if the model hasn't been trained yet (fresh checkout, Week 1-3
    scripts never run) so callers can fall back rather than crash.
    """
    latest = db.query_one(
        """
        SELECT payload_json
        FROM model_runs
        WHERE model_name = ?
        ORDER BY generated_at DESC, id DESC
        LIMIT 1
        """,
        (model_name,),
    )
    if not latest:
        return None
    payload = json.loads(latest["payload_json"])
    coefficients = payload.get("coefficients")
    if not coefficients:
        return None
    return {
        "model_name": model_name,
        "coefficients": {row["feature"]: row for row in coefficients},
        "calibrator": payload.get("calibrator", {"a": 1.0, "b": 0.0}),
        "elo_ratings": current_team_elo_ratings(db),
        "team_stats": current_team_stats(db),
    }


def build_live_match_features(fixture: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    team_a = normalize_team_name(fixture["team_a"])
    team_b = normalize_team_name(fixture["team_b"])
    elo_ratings = snapshot["elo_ratings"]
    team_stats = snapshot["team_stats"]

    elo_a = elo_ratings.get(team_a, EloConfig.start_rating)
    elo_b = elo_ratings.get(team_b, EloConfig.start_rating)
    stats_a = team_stats.get(team_a)
    stats_b = team_stats.get(team_b)
    matches_a = int(stats_a["matches"]) if stats_a else 0
    matches_b = int(stats_b["matches"]) if stats_b else 0

    match_date = str(fixture.get("match_date") or date.today().isoformat())
    competition = str(fixture.get("competition") or "")
    haystack = f"{competition} {fixture.get('team_a', '')} {fixture.get('team_b', '')}".lower()

    features = {
        "elo_diff": (elo_a - elo_b) / 400.0,
        "experience_diff": (math.log1p(matches_a) - math.log1p(matches_b)) / 5.0,
        "win_rate_diff": _win_rate(stats_a) - _win_rate(stats_b),
        "avg_runs_for_diff": (_avg(stats_a, "runs_for", "matches", 155.0) - _avg(stats_b, "runs_for", "matches", 155.0)) / 55.0,
        "avg_runs_against_diff": (_avg(stats_a, "runs_against", "matches", 155.0) - _avg(stats_b, "runs_against", "matches", 155.0)) / 55.0,
        "avg_wickets_taken_diff": (_avg(stats_a, "wickets_for", "matches", 6.0) - _avg(stats_b, "wickets_for", "matches", 6.0)) / 4.0,
        # Neither Bet365 (via odds-api.io) nor The Odds API returns a real venue for
        # cricket fixtures, only the competition name, so this stays neutral rather
        # than guessed.
        "venue_experience_diff": 0.0,
        "rest_days_diff": (_rest_days(stats_a, match_date) - _rest_days(stats_b, match_date)) / 60.0,
        "female_match": 1.0 if "women" in haystack else 0.0,
        "world_cup_match": 1.0 if "world cup" in haystack else 0.0,
    }
    return {
        "features": features,
        "team_a_normalized": team_a,
        "team_b_normalized": team_b,
        "team_a_elo": round(elo_a, 1),
        "team_b_elo": round(elo_b, 1),
        "team_a_historical_matches": matches_a,
        "team_b_historical_matches": matches_b,
        "team_a_matched": stats_a is not None,
        "team_b_matched": stats_b is not None,
        "feature_source": "trained_pretoss_logistic",
    }


def predict_probability(snapshot: dict[str, Any], features: dict[str, float]) -> float:
    coefficients = snapshot["coefficients"]
    logit = float(coefficients["intercept"]["weight"])
    for name in BASE_FEATURE_NAMES:
        row = coefficients.get(name)
        if not row:
            continue
        mean = float(row.get("train_mean", 0.0))
        std = float(row.get("train_std", 1.0)) or 1.0
        scaled = (float(features[name]) - mean) / std
        logit += float(row["weight"]) * scaled
    logit = max(-35.0, min(35.0, logit))
    calibrator = snapshot["calibrator"]
    calibrated = float(calibrator.get("a", 1.0)) * logit + float(calibrator.get("b", 0.0))
    calibrated = max(-35.0, min(35.0, calibrated))
    return 1.0 / (1.0 + math.exp(-calibrated))


def data_confidence_factor(feature_context: dict[str, Any]) -> float:
    """Scales confidence down when either team has thin/no Cricsheet history.

    A team the model has never seen (0 historical matches) should not produce the
    same confidence as a well-covered international side purely because the
    sigmoid output looks decisive -- the risk gate relies on this to skip bets on
    teams outside the model's real coverage.
    """
    known = min(feature_context["team_a_historical_matches"], feature_context["team_b_historical_matches"])
    if known >= MIN_MATCHES_FOR_FULL_CONFIDENCE:
        return 1.0
    return max(0.0, known / MIN_MATCHES_FOR_FULL_CONFIDENCE)


def _win_rate(stats: dict[str, Any] | None) -> float:
    if not stats or not stats["matches"]:
        return 0.5
    return float(stats["wins"]) / float(stats["matches"])


def _avg(stats: dict[str, Any] | None, numerator: str, denominator: str, default: float) -> float:
    if not stats or not stats[denominator]:
        return default
    return float(stats[numerator]) / float(stats[denominator])


def _rest_days(stats: dict[str, Any] | None, match_date: str) -> float:
    if not stats or not stats.get("last_date"):
        return 30.0
    try:
        current = date.fromisoformat(match_date)
        previous = date.fromisoformat(str(stats["last_date"]))
    except ValueError:
        return 30.0
    return float(max(0, min(180, (current - previous).days)))
