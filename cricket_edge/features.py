from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def stable_score(name: str, low: float = 0.0, high: float = 1.0) -> float:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    value = int(digest[:12], 16) / float(0xFFFFFFFFFFFF)
    return low + value * (high - low)


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def parse_weather(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def build_match_features(fixture: dict[str, Any]) -> dict[str, float | str]:
    team_a = fixture["team_a"]
    team_b = fixture["team_b"]
    venue = fixture["venue"]
    weather = parse_weather(fixture.get("weather_json"))

    team_a_elo = stable_score(f"elo:{team_a}", 1420, 1660)
    team_b_elo = stable_score(f"elo:{team_b}", 1420, 1660)
    team_a_batting = stable_score(f"batting:{team_a}", -0.35, 0.35)
    team_b_batting = stable_score(f"batting:{team_b}", -0.35, 0.35)
    team_a_bowling = stable_score(f"bowling:{team_a}", -0.35, 0.35)
    team_b_bowling = stable_score(f"bowling:{team_b}", -0.35, 0.35)
    venue_home = stable_score(f"venue-home:{venue}:{team_a}", -0.12, 0.12)
    par_score = stable_score(f"venue-par:{venue}", 145, 184)
    rain_probability = float(weather.get("rain_probability", 0.18))
    wind_kph = float(weather.get("wind_kph", 12.0))
    weather_penalty = min(0.12, rain_probability * 0.09 + max(0, wind_kph - 20) * 0.002)

    strength_delta = (
        (team_a_elo - team_b_elo) / 380
        + team_a_batting
        - team_b_bowling * 0.65
        - team_b_batting * 0.85
        + team_a_bowling * 0.45
        + venue_home
    )

    return {
        "team_a_elo": round(team_a_elo, 1),
        "team_b_elo": round(team_b_elo, 1),
        "team_a_batting": round(team_a_batting, 3),
        "team_b_batting": round(team_b_batting, 3),
        "team_a_bowling": round(team_a_bowling, 3),
        "team_b_bowling": round(team_b_bowling, 3),
        "venue_home": round(venue_home, 3),
        "venue_par_score": round(par_score, 1),
        "rain_probability": round(rain_probability, 3),
        "wind_kph": round(wind_kph, 1),
        "weather_penalty": round(weather_penalty, 3),
        "strength_delta": round(strength_delta, 4),
        "feature_source": "deterministic_demo_features",
    }
