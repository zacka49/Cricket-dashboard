from __future__ import annotations

import hashlib
import json
import random
from datetime import date, datetime, time, timedelta, timezone

from .config import SETTINGS
from .database import Database, utc_now


TEAMS = [
    "Somerset",
    "Surrey",
    "Lancashire",
    "Yorkshire",
    "Birmingham Bears",
    "Essex",
    "Kent",
    "Hampshire",
    "England Women",
    "India Women",
    "Australia Women",
    "South Africa Women",
]

VENUES = [
    "Taunton",
    "The Oval",
    "Old Trafford",
    "Headingley",
    "Edgbaston",
    "Chelmsford",
    "Canterbury",
    "Ageas Bowl",
]


def _stable_random(*parts: str) -> random.Random:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return random.Random(int(digest[:12], 16))


def seed_demo_data(db: Database) -> None:
    db.init_schema()
    account = db.query_one("SELECT id FROM paper_account WHERE id = 1")
    if not account:
        db.execute(
            "INSERT INTO paper_account(id, starting_bankroll, created_at) VALUES (1, ?, ?)",
            (SETTINGS.starting_bankroll, utc_now()),
        )

    existing = db.query_one("SELECT COUNT(*) AS count FROM fixtures")
    if existing and existing["count"] > 0:
        return

    today = date.today()
    fixtures = [
        (today, time(13, 30), "Vitality Blast", "T20", "Somerset", "Surrey", "Taunton"),
        (today, time(18, 30), "Vitality Blast", "T20", "Lancashire", "Yorkshire", "Old Trafford"),
        (today + timedelta(days=1), time(14, 0), "Women's T20 World Cup", "T20", "England Women", "India Women", "Edgbaston"),
        (today + timedelta(days=1), time(19, 0), "Vitality Blast", "T20", "Hampshire", "Essex", "Ageas Bowl"),
        (today + timedelta(days=2), time(18, 30), "Women's T20 World Cup", "T20", "Australia Women", "South Africa Women", "The Oval"),
    ]

    for match_date, start, competition, fmt, team_a, team_b, venue in fixtures:
        weather = _demo_weather(venue, match_date.isoformat())
        db.execute(
            """
            INSERT OR IGNORE INTO fixtures(
                match_date, start_time, competition, format, team_a, team_b, venue,
                status, weather_json, source, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'scheduled', ?, 'demo', ?)
            """,
            (
                match_date.isoformat(),
                start.strftime("%H:%M"),
                competition,
                fmt,
                team_a,
                team_b,
                venue,
                json.dumps(weather, sort_keys=True),
                utc_now(),
            ),
        )

    ensure_demo_odds(db)
    db.log_event("system", "Seeded demo fixtures and paper account.")


def ensure_demo_odds(db: Database) -> None:
    fixtures = db.query("SELECT * FROM fixtures WHERE source = 'demo' AND status IN ('scheduled', 'live') ORDER BY match_date, start_time")
    for fixture in fixtures:
        latest = db.query_one(
            """
            SELECT id FROM odds_snapshots
            WHERE fixture_id = ? AND market = 'match_winner'
            LIMIT 1
            """,
            (fixture["id"],),
        )
        if latest:
            continue
        rng = _stable_random(str(fixture["id"]), fixture["team_a"], fixture["team_b"], "open")
        base_a = 1.65 + rng.random() * 1.25
        implied_a = 1 / base_a
        overround = 1.045
        implied_b = max(0.08, overround - implied_a)
        odds_b = 1 / implied_b
        captured_at = utc_now()
        for selection, odds in ((fixture["team_a"], base_a), (fixture["team_b"], odds_b)):
            db.execute(
                """
                INSERT INTO odds_snapshots(fixture_id, market, selection, odds, source, captured_at)
                VALUES (?, 'match_winner', ?, ?, 'demo-market', ?)
                """,
                (fixture["id"], selection, round(odds, 3), captured_at),
            )


def _demo_weather(venue: str, match_date: str) -> dict[str, float | str]:
    rng = _stable_random(venue, match_date, "weather")
    return {
        "source": "demo",
        "temperature_c": round(14 + rng.random() * 12, 1),
        "rain_probability": round(rng.random() * 0.55, 2),
        "wind_kph": round(6 + rng.random() * 24, 1),
        "humidity": round(48 + rng.random() * 40, 1),
    }


def simulate_market_move(db: Database) -> None:
    fixtures = db.query("SELECT * FROM fixtures WHERE source = 'demo' AND status IN ('scheduled', 'live')")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for fixture in fixtures:
        rows = db.query(
            """
            SELECT selection, odds
            FROM odds_snapshots
            WHERE fixture_id = ? AND market = 'match_winner'
            AND captured_at = (
                SELECT MAX(captured_at) FROM odds_snapshots
                WHERE fixture_id = ? AND market = 'match_winner'
            )
            """,
            (fixture["id"], fixture["id"]),
        )
        if len(rows) < 2:
            continue
        rng = _stable_random(str(fixture["id"]), now, "move")
        shock = rng.uniform(-0.06, 0.06)
        for idx, row in enumerate(rows):
            direction = shock if idx == 0 else -shock
            new_odds = max(1.08, float(row["odds"]) * (1 + direction))
            db.execute(
                """
                INSERT INTO odds_snapshots(fixture_id, market, selection, odds, source, captured_at)
                VALUES (?, 'match_winner', ?, ?, 'demo-market', ?)
                """,
                (fixture["id"], row["selection"], round(new_odds, 3), now),
            )

    db.log_event("market", "Simulated fresh market odds movement for open fixtures.")
