from __future__ import annotations

import concurrent.futures
import csv
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from .config import SETTINGS
from .data_sources import FreeDataSources
from .database import Database, utc_now
from .live_model import normalize_team_name
from .match_linkage import link_fixture_to_cricsheet, resolve_winner_for_fixture
from .odds_api_io import extract_match_winner_outcomes as extract_odds_api_io_match_winner_outcomes
from .odds_api_io import parse_events, parse_sports
from .odds_math import implied_probability
from .the_odds_api import extract_match_winner_outcomes as extract_the_odds_api_match_winner_outcomes
from .the_odds_api import parse_odds_events
from .logistic_model import (
    binary_log_loss,
    calibration_bins,
    expected_calibration_error,
    split_metrics,
    upsert_model_registry,
)


CURRENT_MARKET_MODEL = "market_implied_current_v1"
SYNTHETIC_MARKET_MODEL = "market_implied_synthetic_v1"
HISTORICAL_MARKET_MODEL = "market_implied_historical_v1"
BET365_SOURCE = "bet365"
THE_ODDS_API_SOURCE = "the_odds_api"
REAL_ODDS_SOURCES = {BET365_SOURCE, THE_ODDS_API_SOURCE}


def run_week4_market_build(db: Database, csv_path: Path | None = None) -> dict[str, Any]:
    if csv_path:
        imported = import_market_csv(db, csv_path)
    else:
        imported = {"rows_imported": 0, "path": None}
    synced = sync_fixture_odds_to_market_snapshots(db)
    current = build_current_market_baselines(db)
    synthetic = build_synthetic_market_baseline(db)
    historical_backfill = backfill_historical_market_baselines(db)
    clv = update_paper_bet_evaluations(db)
    return {
        "csv_import": imported,
        "fixture_odds_synced": synced,
        "current_market_baselines": current,
        "synthetic_market_baseline": synthetic,
        "historical_market_backfill": historical_backfill,
        "paper_bet_clv": clv,
    }


def fetch_bet365_cricket_odds(db: Database) -> dict[str, Any]:
    primary = _fetch_odds_api_io_bet365_cricket_odds(db)
    fallback: dict[str, Any] | None = None
    fallback_used = False
    if _should_try_the_odds_api_fallback(db, primary):
        fallback = fetch_the_odds_api_cricket_odds(db)
        fallback_used = bool(fallback.get("ok")) and (
            int(fallback.get("odds_rows_inserted", 0) or 0) > 0 or _has_fresh_real_source(db, THE_ODDS_API_SOURCE)
        )
    if not fallback:
        return primary | {"primary": primary, "fallback": None, "fallback_used": False}

    errors = list(primary.get("errors", [])) + [
        {"stage": f"the_odds_api_{item.get('stage', 'fetch')}", "error": item.get("error", "")}
        for item in fallback.get("errors", [])
    ]
    return {
        "ok": bool(primary.get("ok")) or bool(fallback.get("ok")),
        "provider": "Live odds aggregator",
        "sport": "cricket",
        "bookmakers": primary.get("bookmakers", getattr(SETTINGS, "odds_api_bookmakers", "Bet365")),
        "events_checked": int(primary.get("events_checked", 0) or 0) + int(fallback.get("events_checked", 0) or 0),
        "odds_rows_inserted": int(primary.get("odds_rows_inserted", 0) or 0) + int(fallback.get("odds_rows_inserted", 0) or 0),
        "errors": errors,
        "primary": primary,
        "fallback": fallback,
        "fallback_used": fallback_used,
    }


def _fetch_odds_api_io_bet365_cricket_odds(db: Database) -> dict[str, Any]:
    db.init_schema()
    if not SETTINGS.odds_api_key:
        message = "ODDS_API_KEY is not set. Add it to .env to enable odds-api.io Bet365 odds."
        db.log_event("market", message)
        return {"ok": False, "needs_api_key": True, "message": message}

    source = FreeDataSources(db)
    max_events = max(1, SETTINGS.odds_api_max_events)
    sport = SETTINGS.odds_api_io_sport
    bookmakers = SETTINGS.odds_api_bookmakers or "Bet365"
    fetched_events = 0
    inserted_odds = 0
    errors: list[dict[str, str]] = []

    try:
        sports = source.fetch_odds_api_io_sports()["data"]
        parsed_sports = parse_sports(sports)
        available_slugs = {item.slug for item in parsed_sports}
        if sport not in available_slugs:
            cricket = next((item for item in parsed_sports if item.name.lower() == "cricket"), None)
            if cricket:
                sport = cricket.slug
        upcoming = source.fetch_odds_api_io_events(sport=sport, status="pending", limit=max_events)
        upcoming_events = [event.model_dump(mode="json") for event in parse_events(upcoming["data"])]
    except Exception as exc:
        upcoming_events = []
        errors.append({"stage": "upcoming", "error": str(exc)})

    try:
        live = source.fetch_odds_api_io_events(sport=sport, status="live", limit=max_events)
        live_events = [event.model_dump(mode="json") for event in parse_events(live["data"])]
    except Exception as exc:
        live_events = []
        errors.append({"stage": "live_events", "error": str(exc)})

    events_by_id: dict[str, dict[str, Any]] = {}
    for event in upcoming_events + live_events:
        event_id = str(event.get("id", ""))
        if event_id:
            events_by_id[event_id] = event

    selected_events = list(events_by_id.values())[:max_events]

    # Phase 1: sequential fixture upserts. Cheap DB writes, and must happen before
    # any network call so we know which events are even viable to fetch odds for.
    fixture_by_event_id: dict[str, int] = {}
    for event in selected_events:
        fetched_events += 1
        try:
            fixture_by_event_id[str(event.get("id", ""))] = _upsert_bet365_fixture(
                db, event, status_override=_odds_api_io_fixture_status(event)
            )
        except Exception as exc:
            errors.append({"stage": "event_odds", "event_id": str(event.get("id", "")), "error": str(exc)})

    # Phase 2: bounded-concurrency network calls only, no DB writes inside worker
    # threads. An overall time budget means a slow/rate-limited API can't hang the
    # whole run for minutes -- unfinished calls are recorded as timeouts instead.
    viable_events = [event for event in selected_events if str(event.get("id", "")) in fixture_by_event_id]
    odds_payload_by_event_id: dict[str, dict[str, Any]] = {}
    if viable_events:
        max_workers = max(1, getattr(SETTINGS, "odds_api_max_workers", 6))
        overall_timeout = getattr(SETTINGS, "odds_api_overall_timeout_seconds", 45)
        # Not using `with` here deliberately: ThreadPoolExecutor.__exit__ calls
        # shutdown(wait=True), which would block on any still-running thread and
        # defeat the whole point of the overall timeout below. shutdown(wait=False)
        # lets this function return promptly; any thread still running past the
        # budget is abandoned rather than waited on.
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        try:
            future_to_event = {
                pool.submit(source.fetch_odds_api_io_event_odds, event["id"], bookmakers=bookmakers): event
                for event in viable_events
            }
            done, not_done = concurrent.futures.wait(future_to_event, timeout=overall_timeout)
            for future in not_done:
                event = future_to_event[future]
                errors.append(
                    {
                        "stage": "event_odds_timeout",
                        "event_id": str(event.get("id", "")),
                        "error": f"exceeded overall {overall_timeout}s odds-fetch budget",
                    }
                )
            for future in done:
                event = future_to_event[future]
                event_id = str(event.get("id", ""))
                try:
                    odds_payload_by_event_id[event_id] = future.result()
                except Exception as exc:
                    errors.append({"stage": "event_odds", "event_id": event_id, "error": str(exc)})
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    # Phase 3: sequential parse + DB writes, single-threaded to avoid concurrent
    # sqlite writes.
    for event in viable_events:
        event_id = str(event.get("id", ""))
        payload = odds_payload_by_event_id.get(event_id)
        if payload is None:
            continue
        try:
            outcomes = [
                outcome.model_dump(mode="json")
                for outcome in extract_odds_api_io_match_winner_outcomes(
                    payload["data"],
                    allowed_bookmakers={"Bet365"},
                )
            ]
            inserted_odds += _insert_bet365_odds(
                db,
                fixture_by_event_id[event_id],
                event,
                outcomes,
                payload["data"],
                is_live=str(event.get("status", "")).lower() == "live",
            )
        except Exception as exc:
            errors.append({"stage": "event_odds", "event_id": event_id, "error": str(exc)})

    normalize_market_snapshot_probabilities(db)
    build_current_market_baselines(db)
    update_paper_bet_evaluations(db)
    fetch_payload = {
        "provider": "Bet365 via odds-api.io",
        "sport": sport,
        "bookmakers": bookmakers,
        "events_checked": fetched_events,
        "odds_rows_inserted": inserted_odds,
        "errors": errors[:10],
    }
    db.log_event(
        "market",
        f"Fetched Bet365 cricket odds for {fetched_events} events; inserted {inserted_odds} odds rows.",
        fetch_payload,
    )
    ok = not errors or inserted_odds > 0
    return {
        "ok": ok,
        "provider": "Bet365 via odds-api.io",
        "sport": sport,
        "bookmakers": bookmakers,
        "events_checked": fetched_events,
        "odds_rows_inserted": inserted_odds,
        "errors": errors,
    }


def fetch_the_odds_api_cricket_odds(db: Database) -> dict[str, Any]:
    db.init_schema()
    if not getattr(SETTINGS, "the_odds_api_key", ""):
        message = "THE_ODDS_API_KEY is not set. Add it to .env to enable The Odds API fallback."
        db.log_event("market", message)
        return {"ok": False, "needs_api_key": True, "message": message, "events_checked": 0, "odds_rows_inserted": 0, "errors": []}

    source = FreeDataSources(db)
    sport_keys = _the_odds_api_sport_keys()
    regions = getattr(SETTINGS, "the_odds_api_regions", "uk,eu,au")
    markets = getattr(SETTINGS, "the_odds_api_markets", "h2h")
    bookmakers = getattr(SETTINGS, "the_odds_api_bookmakers", "") or None
    fetched_events = 0
    inserted_odds = 0
    errors: list[dict[str, str]] = []
    bookmakers_seen: set[str] = set()

    for sport_key in sport_keys:
        try:
            payload = source.fetch_the_odds_api_odds(
                sport_key=sport_key,
                regions=regions,
                markets=markets,
                bookmakers=bookmakers,
            )
            events = [event.model_dump(mode="json") for event in parse_odds_events(payload["data"])]
        except Exception as exc:
            errors.append({"stage": "the_odds_api_odds", "sport_key": sport_key, "error": str(exc)})
            continue

        for event in events:
            fetched_events += 1
            try:
                fixture_id = _upsert_the_odds_api_fixture(db, event)
                outcomes = [
                    outcome.model_dump(mode="json")
                    for outcome in extract_the_odds_api_match_winner_outcomes(event)
                ]
                for outcome in outcomes:
                    bookmakers_seen.add(str(outcome.get("bookmaker") or ""))
                inserted_odds += _insert_the_odds_api_odds(db, fixture_id, event, outcomes)
            except Exception as exc:
                errors.append({"stage": "the_odds_api_event", "event_id": str(event.get("id", "")), "error": str(exc)})

    normalize_market_snapshot_probabilities(db)
    build_current_market_baselines(db)
    update_paper_bet_evaluations(db)
    fetch_payload = {
        "provider": "The Odds API",
        "sport": "cricket",
        "sport_keys": sport_keys,
        "regions": regions,
        "bookmakers": sorted(item for item in bookmakers_seen if item),
        "events_checked": fetched_events,
        "odds_rows_inserted": inserted_odds,
        "errors": errors[:10],
    }
    db.log_event(
        "market",
        f"Fetched The Odds API cricket odds for {fetched_events} events; inserted {inserted_odds} odds rows.",
        fetch_payload,
    )
    return {
        "ok": (not errors and fetched_events >= 0) or inserted_odds > 0,
        "provider": "The Odds API",
        "sport": "cricket",
        "sport_keys": sport_keys,
        "regions": regions,
        "bookmakers": sorted(item for item in bookmakers_seen if item),
        "events_checked": fetched_events,
        "odds_rows_inserted": inserted_odds,
        "errors": errors,
    }


def import_market_csv(db: Database, path: Path) -> dict[str, Any]:
    db.init_schema()
    rows_imported = 0
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            odds = float(row["decimal_odds"])
            implied = 1.0 / odds
            db.execute(
                """
                INSERT INTO market_odds_snapshots(
                    fixture_id, match_id, source, bookmaker, market, selection, decimal_odds,
                    implied_probability, normalized_probability, overround, captured_at,
                    is_closing_proxy, mapping_confidence, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)
                """,
                (
                    _nullable_int(row.get("fixture_id")),
                    row.get("match_id") or None,
                    row.get("source") or "manual_csv",
                    row.get("bookmaker") or "unknown",
                    row.get("market") or "match_winner",
                    row["selection"],
                    odds,
                    implied,
                    row.get("captured_at") or utc_now(),
                    int(row.get("is_closing_proxy") or 0),
                    float(row.get("mapping_confidence") or 1.0),
                    json.dumps(row, sort_keys=True),
                ),
            )
            rows_imported += 1
    db.log_event("market", f"Imported {rows_imported} market odds rows from CSV.", {"path": str(path)})
    normalize_market_snapshot_probabilities(db)
    return {"rows_imported": rows_imported, "path": str(path)}


def sync_fixture_odds_to_market_snapshots(db: Database) -> dict[str, Any]:
    db.execute("DELETE FROM market_odds_snapshots WHERE source = 'app_fixture_odds'")
    rows = db.query("SELECT * FROM odds_snapshots ORDER BY fixture_id, market, captured_at, selection")
    inserted = 0
    for row in rows:
        odds = float(row["odds"])
        db.execute(
            """
            INSERT INTO market_odds_snapshots(
                fixture_id, match_id, source, bookmaker, market, selection, decimal_odds,
                implied_probability, normalized_probability, overround, captured_at,
                is_closing_proxy, mapping_confidence, raw_json
            )
            VALUES (?, NULL, 'app_fixture_odds', ?, ?, ?, ?, ?, NULL, NULL, ?, 0, 1.0, ?)
            """,
            (
                row["fixture_id"],
                row["source"],
                row["market"],
                row["selection"],
                odds,
                1.0 / odds,
                row["captured_at"],
                json.dumps(row, sort_keys=True),
            ),
        )
        inserted += 1
    normalize_market_snapshot_probabilities(db)
    db.log_event("market", f"Synced {inserted} app fixture odds into market snapshots.")
    return {"rows_synced": inserted}


def normalize_market_snapshot_probabilities(db: Database) -> None:
    groups = db.query(
        """
        SELECT COALESCE(CAST(fixture_id AS TEXT), '') AS fixture_key,
               COALESCE(match_id, '') AS match_key,
               source, bookmaker, market, captured_at,
               SUM(implied_probability) AS overround
        FROM market_odds_snapshots
        GROUP BY fixture_key, match_key, source, bookmaker, market, captured_at
        """
    )
    for group in groups:
        overround = float(group["overround"] or 0)
        if overround <= 0:
            continue
        db.execute(
            """
            UPDATE market_odds_snapshots
            SET normalized_probability = implied_probability / ?, overround = ?
            WHERE COALESCE(CAST(fixture_id AS TEXT), '') = ?
              AND COALESCE(match_id, '') = ?
              AND source = ?
              AND bookmaker = ?
              AND market = ?
              AND captured_at = ?
            """,
            (
                overround,
                overround,
                group["fixture_key"],
                group["match_key"],
                group["source"],
                group["bookmaker"],
                group["market"],
                group["captured_at"],
            ),
        )


def build_current_market_baselines(db: Database) -> dict[str, Any]:
    db.execute("DELETE FROM market_baselines WHERE model_name = ?", (CURRENT_MARKET_MODEL,))
    rows = db.query(
        """
        SELECT m.*
        FROM market_odds_snapshots m
        JOIN (
            SELECT fixture_id, market, selection, MAX(captured_at) AS captured_at
            FROM market_odds_snapshots
            WHERE fixture_id IS NOT NULL
            GROUP BY fixture_id, market, selection
        ) latest
        ON latest.fixture_id = m.fixture_id
        AND latest.market = m.market
        AND latest.selection = m.selection
        AND latest.captured_at = m.captured_at
        WHERE m.fixture_id IS NOT NULL
        """
    )
    for row in rows:
        db.execute(
            """
            INSERT INTO market_baselines(
                model_name, scope, fixture_id, match_id, market, selection, probability,
                decimal_odds, overround, captured_at, result, brier, log_loss, correct, source
            )
            VALUES (?, 'current_fixture', ?, NULL, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?)
            """,
            (
                CURRENT_MARKET_MODEL,
                row["fixture_id"],
                row["market"],
                row["selection"],
                float(row["normalized_probability"] or row["implied_probability"]),
                float(row["decimal_odds"]),
                float(row["overround"] or 0),
                row["captured_at"],
                row["source"],
            ),
        )
    return {"rows": len(rows)}


def backfill_historical_market_baselines(db: Database) -> dict[str, Any]:
    """Populates real, match_id-keyed market_baselines rows so the historical
    strategy backtest has real data to work with.

    Independently scans real-sourced fixtures rather than relying on
    fixtures.status='complete' -- today that flag is only ever set by paper-bet
    settlement, so most real fixtures never get it even long after the match.
    Only inserts a row once a fixture is linked to a real Cricsheet match and has
    at least one captured real odds snapshot; never fabricates a baseline.
    """
    fixtures = db.query(
        """
        SELECT * FROM fixtures
        WHERE source IN ('bet365', 'the_odds_api') AND match_date <= date('now')
        """
    )
    linked = inserted = skipped_no_match = 0
    for fixture in fixtures:
        match = link_fixture_to_cricsheet(
            db, int(fixture["id"]), fixture["team_a"], fixture["team_b"], fixture["match_date"]
        )
        if not match:
            skipped_no_match += 1
            continue
        linked += 1

        odds_rows = db.query(
            """
            SELECT selection, odds, source, captured_at FROM odds_snapshots
            WHERE fixture_id = ? AND market = 'match_winner' AND source IN ('bet365', 'the_odds_api')
            ORDER BY captured_at ASC
            """,
            (fixture["id"],),
        )
        if not odds_rows:
            continue
        earliest_by_selection: dict[str, dict[str, Any]] = {}
        for row in odds_rows:
            earliest_by_selection.setdefault(row["selection"], row)

        implied = {selection: 1.0 / float(row["odds"]) for selection, row in earliest_by_selection.items()}
        overround = sum(implied.values()) if len(implied) >= 2 else 0.0
        winner = resolve_winner_for_fixture(fixture["team_a"], fixture["team_b"], match)

        for selection, row in earliest_by_selection.items():
            normalized_selection = normalize_team_name(selection)
            probability = implied[selection] / overround if overround > 0 else implied[selection]
            result = None
            if winner is not None:
                result = 1.0 if normalized_selection == normalize_team_name(winner) else 0.0
            db.execute(
                """
                INSERT OR IGNORE INTO market_baselines(
                    model_name, scope, fixture_id, match_id, market, selection, probability,
                    decimal_odds, overround, captured_at, result, brier, log_loss, correct, source
                )
                VALUES (?, 'historical_match', ?, ?, 'match_winner', ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?)
                """,
                (
                    HISTORICAL_MARKET_MODEL,
                    fixture["id"],
                    match["match_id"],
                    normalized_selection,
                    round(probability, 6),
                    float(row["odds"]),
                    round(overround, 4),
                    row["captured_at"],
                    result,
                    row["source"],
                ),
            )
            inserted += 1

    result_summary = {
        "fixtures_checked": len(fixtures),
        "linked": linked,
        "skipped_no_match": skipped_no_match,
        "rows_inserted": inserted,
    }
    db.log_event(
        "backtest",
        f"Backfilled {inserted} historical market baseline rows from {linked} linked fixtures.",
        result_summary,
    )
    return result_summary


def build_synthetic_market_baseline(db: Database) -> dict[str, Any]:
    rows = db.query(
        """
        SELECT match_id, match_date, competition, team_a, team_b, winner, pred_a, result_a
        FROM team_elo_history
        ORDER BY match_date, match_id
        """
    )
    if not rows:
        return {"rows": 0}
    n = len(rows)
    train_end = max(1, int(n * 0.70))
    val_end = max(train_end + 1, int(n * 0.85))
    probs = []
    prepared = []
    for idx, row in enumerate(rows):
        split = "train" if idx < train_end else "validation" if idx < val_end else "test"
        noise = _stable_noise(row["match_id"], -0.035, 0.035)
        probability = min(0.94, max(0.06, 0.5 + (float(row["pred_a"]) - 0.5) * 1.10 + noise))
        probs.append(probability)
        prepared.append(dict(row) | {"split": split})

    probs_array = np.array(probs, dtype=float)
    db.execute("DELETE FROM model_predictions WHERE model_name = ?", (SYNTHETIC_MARKET_MODEL,))
    prediction_rows = []
    for row, probability in zip(prepared, probs_array):
        brier = (probability - float(row["result_a"])) ** 2
        loss = binary_log_loss(probability, float(row["result_a"]))
        prediction_rows.append(
            (
                SYNTHETIC_MARKET_MODEL,
                row["match_id"],
                row["split"],
                row["match_date"],
                row["competition"],
                row["team_a"],
                row["team_b"],
                row["winner"],
                round(float(probability), 6),
                float(row["result_a"]),
                round(brier, 6),
                round(loss, 6),
                int((probability >= 0.5 and row["result_a"] == 1.0) or (probability < 0.5 and row["result_a"] == 0.0)),
                json.dumps({"source": "synthetic_elo_plus_noise", "not_real_market_odds": True}, sort_keys=True),
            )
        )
    db.executemany(
        """
        INSERT INTO model_predictions(
            model_name, match_id, split, match_date, competition, team_a, team_b, winner,
            pred_a, result_a, brier, log_loss, correct, features_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        prediction_rows,
    )
    metrics = {
        "model_name": SYNTHETIC_MARKET_MODEL,
        "n_matches": n,
        "timing": "historical_benchmark",
        "synthetic": True,
        "splits": {
            "train": split_metrics(prepared, probs_array, "train"),
            "validation": split_metrics(prepared, probs_array, "validation"),
            "test": split_metrics(prepared, probs_array, "test"),
        },
        "calibration": {
            "synthetic_market_test": calibration_bins(prepared, probs_array, "test"),
            "ece_test": expected_calibration_error(prepared, probs_array, "test"),
        },
        "warning": "Synthetic market baseline exists only to test market-comparison plumbing until real odds history is collected.",
    }
    test = metrics["splits"]["test"]
    db.execute(
        """
        INSERT INTO model_runs(model_name, generated_at, n_matches, brier, log_loss, accuracy, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            SYNTHETIC_MARKET_MODEL,
            utc_now(),
            n,
            round(float(test["brier"]), 6),
            round(float(test["log_loss"]), 6),
            round(float(test["accuracy"]), 6),
            json.dumps(metrics, sort_keys=True, default=float),
        ),
    )
    upsert_model_registry(
        db,
        model_name=SYNTHETIC_MARKET_MODEL,
        model_family="market_implied",
        timing="historical_benchmark",
        status="benchmark",
        active=0,
        calibrated=0,
        feature_names=["synthetic_elo_plus_noise"],
        metrics=metrics,
        notes="Synthetic placeholder. Replace with real closing odds as snapshots accumulate.",
    )
    db.log_event("market", "Built synthetic market-implied baseline for plumbing checks.", metrics)
    return {"rows": n, "test": test}


def update_paper_bet_evaluations(db: Database) -> dict[str, Any]:
    bets = db.query(
        """
        SELECT b.*, f.match_date
        FROM paper_bets b
        JOIN fixtures f ON f.id = b.fixture_id
        """
    )
    updated = 0
    for bet in bets:
        latest = db.query_one(
            """
            SELECT odds, captured_at
            FROM odds_snapshots
            WHERE fixture_id = ? AND market = ? AND selection = ?
            ORDER BY captured_at DESC, id DESC
            LIMIT 1
            """,
            (bet["fixture_id"], bet["market"], bet["selection"]),
        )
        latest_odds = float(latest["odds"]) if latest else None
        closing_odds = latest_odds if latest_odds and date.fromisoformat(bet["match_date"]) <= date.today() else None
        clv = (float(bet["odds"]) / closing_odds - 1.0) if closing_odds else None
        db.execute(
            """
            INSERT INTO paper_bet_evaluations(bet_id, entry_odds, latest_odds, closing_odds, clv, latest_checked_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bet_id) DO UPDATE SET
                entry_odds = excluded.entry_odds,
                latest_odds = excluded.latest_odds,
                closing_odds = excluded.closing_odds,
                clv = excluded.clv,
                latest_checked_at = excluded.latest_checked_at,
                notes = excluded.notes
            """,
            (
                bet["id"],
                float(bet["odds"]),
                latest_odds,
                closing_odds,
                clv,
                utc_now(),
                "CLV uses latest available odds as closing proxy when fixture date has arrived.",
            ),
        )
        updated += 1
    return {"paper_bets_evaluated": updated}


def latest_week4_report(db: Database) -> dict[str, Any]:
    synthetic = db.query_one(
        """
        SELECT *
        FROM model_runs
        WHERE model_name = ?
        ORDER BY generated_at DESC, id DESC
        LIMIT 1
        """,
        (SYNTHETIC_MARKET_MODEL,),
    )
    clv = db.query_one(
        """
        SELECT COUNT(*) AS bets, AVG(clv) AS avg_clv
        FROM paper_bet_evaluations
        WHERE clv IS NOT NULL
        """
    )
    market_counts = db.query_one(
        """
        SELECT COUNT(*) AS odds_rows, COUNT(DISTINCT fixture_id) AS fixtures
        FROM market_odds_snapshots
        """
    )
    source_counts = db.query(
        """
        SELECT source, COUNT(*) AS odds_rows, COUNT(DISTINCT fixture_id) AS fixtures, MAX(captured_at) AS latest_capture
        FROM market_odds_snapshots
        GROUP BY source
        ORDER BY odds_rows DESC
        """
    )
    real_recent = db.query(
        """
        SELECT m.*, f.team_a, f.team_b, f.competition, f.match_date, f.start_time
        FROM market_odds_snapshots m
        LEFT JOIN fixtures f ON f.id = m.fixture_id
        WHERE m.source IN ('bet365', 'the_odds_api')
        ORDER BY m.captured_at DESC, m.id DESC
        LIMIT 30
        """
    )
    odds_event = db.query_one(
        """
        SELECT *
        FROM events
        WHERE type = 'market'
          AND (message LIKE 'Fetched % cricket odds%' OR message LIKE '%ODDS_API_KEY%' OR message LIKE '%THE_ODDS_API_KEY%')
        ORDER BY timestamp DESC, id DESC
        LIMIT 1
        """
    )
    odds_event_payload: dict[str, Any] = {}
    if odds_event:
        try:
            odds_event_payload = json.loads(odds_event["payload_json"] or "{}")
        except json.JSONDecodeError:
            odds_event_payload = {}
    latest_real_capture = _latest_capture_for_sources(source_counts, REAL_ODDS_SOURCES)
    freshness = _capture_freshness(latest_real_capture)
    current = db.query(
        """
        SELECT *
        FROM market_baselines
        WHERE model_name = ?
        ORDER BY captured_at DESC, fixture_id, selection
        LIMIT 20
        """,
        (CURRENT_MARKET_MODEL,),
    )
    evaluations = db.query(
        """
        SELECT e.*, b.selection, b.market, f.team_a, f.team_b
        FROM paper_bet_evaluations e
        JOIN paper_bets b ON b.id = e.bet_id
        JOIN fixtures f ON f.id = b.fixture_id
        ORDER BY e.latest_checked_at DESC
        LIMIT 20
        """
    )
    return {
        "market_counts": market_counts or {},
        "source_counts": source_counts,
        "bet365_status": {
            "configured": bool(SETTINGS.odds_api_key or getattr(SETTINGS, "the_odds_api_key", "")),
            "max_events_per_fetch": SETTINGS.odds_api_max_events,
            "approved_sources": sorted(REAL_ODDS_SOURCES),
            "provider": odds_event_payload.get("provider", "Live odds aggregator"),
            "bookmakers": odds_event_payload.get("bookmakers", SETTINGS.odds_api_bookmakers),
            "sport": odds_event_payload.get("sport", SETTINGS.odds_api_io_sport),
            "latest_fetch_at": odds_event["timestamp"] if odds_event else "",
            "latest_capture": latest_real_capture,
            "events_checked": odds_event_payload.get("events_checked", 0),
            "odds_rows_inserted": odds_event_payload.get("odds_rows_inserted", 0),
            "fallback_used": odds_event_payload.get("fallback_used", False),
            "freshness": freshness,
            "is_fresh": freshness["is_fresh"],
            "freshness_status": freshness["status"],
            "latest_message": odds_event["message"] if odds_event else "",
            "latest_errors": odds_event_payload.get("errors", []),
        },
        "bet365_recent_odds": real_recent,
        "synthetic_market": {"latest_run": dict(synthetic) if synthetic else {}, "payload": _safe_json_loads(synthetic["payload_json"]) if synthetic else {}},
        "current_market": current,
        "paper_clv": clv or {},
        "paper_bet_evaluations": evaluations,
    }


def _upsert_bet365_fixture(db: Database, event: dict[str, Any], status_override: str | None = None) -> int:
    home = _team_name(event, "home")
    away = _team_name(event, "away")
    if not home or not away:
        raise ValueError("Bet365 event is missing home/away team names.")
    local_dt = _event_datetime(event)
    status = status_override or ("live" if str(event.get("time_status")) == "1" else "scheduled")
    league = event.get("league") if isinstance(event.get("league"), dict) else {}
    db.execute(
        """
        INSERT OR IGNORE INTO fixtures(
            match_date, start_time, competition, format, team_a, team_b, venue,
            status, weather_json, source, created_at
        )
        VALUES (?, ?, ?, 'T20', ?, ?, 'Bet365', ?, '{}', ?, ?)
        """,
        (
            local_dt.date().isoformat(),
            local_dt.strftime("%H:%M"),
            str(league.get("name") or "Bet365 Cricket"),
            home,
            away,
            status,
            BET365_SOURCE,
            utc_now(),
        ),
    )
    row = db.query_one(
        """
        SELECT id
        FROM fixtures
        WHERE match_date = ? AND start_time = ? AND team_a = ? AND team_b = ? AND venue = 'Bet365'
        """,
        (local_dt.date().isoformat(), local_dt.strftime("%H:%M"), home, away),
    )
    if not row:
        raise RuntimeError("Could not upsert Bet365 fixture.")
    db.execute(
        """
        UPDATE fixtures
        SET status = ?, source = ?
        WHERE id = ?
        """,
        (status, BET365_SOURCE, row["id"]),
    )
    return int(row["id"])


def _insert_bet365_odds(
    db: Database,
    fixture_id: int,
    event: dict[str, Any],
    outcomes: list[dict[str, Any]],
    raw_payload: dict[str, Any],
    is_live: bool,
) -> int:
    if not outcomes:
        return 0
    fetch_captured_at = utc_now()
    inserted = 0
    raw_context = {
        "bet365_event_id": str(event.get("id", "")),
        "league": event.get("league"),
        "home": event.get("home"),
        "away": event.get("away"),
        "time_status": event.get("time_status"),
        "is_live": is_live,
    }
    for outcome in outcomes:
        odds = float(outcome["decimal_odds"])
        selection = str(outcome["selection"])
        captured_at = str(outcome.get("captured_at") or fetch_captured_at)
        bookmaker = str(outcome.get("bookmaker") or "Bet365")
        if _bet365_snapshot_exists(db, fixture_id, bookmaker, selection, odds, captured_at):
            continue
        db.execute(
            """
            INSERT INTO odds_snapshots(fixture_id, market, selection, odds, source, captured_at)
            VALUES (?, 'match_winner', ?, ?, ?, ?)
            """,
            (fixture_id, selection, odds, BET365_SOURCE, captured_at),
        )
        db.execute(
            """
            INSERT INTO market_odds_snapshots(
                fixture_id, match_id, source, bookmaker, market, selection, decimal_odds,
                implied_probability, normalized_probability, overround, captured_at,
                is_closing_proxy, mapping_confidence, raw_json
            )
            VALUES (?, NULL, ?, ?, 'match_winner', ?, ?, ?, NULL, NULL, ?, 0, 1.0, ?)
            """,
            (
                fixture_id,
                BET365_SOURCE,
                bookmaker,
                selection,
                odds,
                implied_probability(odds),
                captured_at,
                json.dumps(raw_context | {"market": outcome.get("market"), "raw_payload_keys": list(raw_payload.keys())}, sort_keys=True, default=str),
            ),
        )
        inserted += 1
    return inserted


def _bet365_snapshot_exists(
    db: Database,
    fixture_id: int,
    bookmaker: str,
    selection: str,
    odds: float,
    captured_at: str,
) -> bool:
    row = db.query_one(
        """
        SELECT id
        FROM market_odds_snapshots
        WHERE fixture_id = ?
          AND source = ?
          AND bookmaker = ?
          AND market = 'match_winner'
          AND selection = ?
          AND decimal_odds = ?
          AND captured_at = ?
        LIMIT 1
        """,
        (fixture_id, BET365_SOURCE, bookmaker, selection, odds, captured_at),
    )
    return bool(row)


def _should_try_the_odds_api_fallback(db: Database, primary: dict[str, Any]) -> bool:
    if not getattr(SETTINGS, "the_odds_api_key", ""):
        return False
    if primary.get("errors"):
        return True
    if int(primary.get("odds_rows_inserted", 0) or 0) > 0 and _has_fresh_real_source(db, BET365_SOURCE):
        return False
    return not _has_fresh_real_source(db, BET365_SOURCE)


def _has_fresh_real_source(db: Database, source: str) -> bool:
    row = db.query_one(
        """
        SELECT MAX(captured_at) AS latest_capture
        FROM market_odds_snapshots
        WHERE source = ?
        """,
        (source,),
    )
    freshness = _capture_freshness(row["latest_capture"] if row else None)
    return bool(freshness["is_fresh"])


def _the_odds_api_sport_keys() -> list[str]:
    raw = getattr(SETTINGS, "the_odds_api_sport_keys", "")
    keys = [item.strip() for item in str(raw).split(",") if item.strip()]
    max_sports = max(1, int(getattr(SETTINGS, "the_odds_api_max_sports", 5) or 5))
    return keys[:max_sports]


def _upsert_the_odds_api_fixture(db: Database, event: dict[str, Any]) -> int:
    home = str(event.get("home_team") or "").strip()
    away = str(event.get("away_team") or "").strip()
    if not home or not away:
        raise ValueError("The Odds API event is missing home/away team names.")
    local_dt = _the_odds_api_event_datetime(event)
    db.execute(
        """
        INSERT OR IGNORE INTO fixtures(
            match_date, start_time, competition, format, team_a, team_b, venue,
            status, weather_json, source, created_at
        )
        VALUES (?, ?, ?, 'T20', ?, ?, 'The Odds API', 'scheduled', '{}', ?, ?)
        """,
        (
            local_dt.date().isoformat(),
            local_dt.strftime("%H:%M"),
            str(event.get("sport_title") or "The Odds API Cricket"),
            home,
            away,
            THE_ODDS_API_SOURCE,
            utc_now(),
        ),
    )
    row = db.query_one(
        """
        SELECT id
        FROM fixtures
        WHERE match_date = ? AND start_time = ? AND team_a = ? AND team_b = ? AND venue = 'The Odds API'
        """,
        (local_dt.date().isoformat(), local_dt.strftime("%H:%M"), home, away),
    )
    if not row:
        raise RuntimeError("Could not upsert The Odds API fixture.")
    return int(row["id"])


def _insert_the_odds_api_odds(
    db: Database,
    fixture_id: int,
    event: dict[str, Any],
    outcomes: list[dict[str, Any]],
) -> int:
    inserted = 0
    raw_context = {
        "the_odds_api_event_id": str(event.get("id", "")),
        "sport_key": event.get("sport_key"),
        "sport_title": event.get("sport_title"),
        "home": event.get("home_team"),
        "away": event.get("away_team"),
        "commence_time": event.get("commence_time"),
    }
    for outcome in outcomes:
        odds = float(outcome["decimal_odds"])
        selection = str(outcome["selection"])
        captured_at = str(outcome.get("captured_at") or utc_now())
        bookmaker = str(outcome.get("bookmaker") or "The Odds API")
        if _real_snapshot_exists(db, fixture_id, THE_ODDS_API_SOURCE, bookmaker, selection, odds, captured_at):
            continue
        db.execute(
            """
            INSERT INTO odds_snapshots(fixture_id, market, selection, odds, source, captured_at)
            VALUES (?, 'match_winner', ?, ?, ?, ?)
            """,
            (fixture_id, selection, odds, THE_ODDS_API_SOURCE, captured_at),
        )
        db.execute(
            """
            INSERT INTO market_odds_snapshots(
                fixture_id, match_id, source, bookmaker, market, selection, decimal_odds,
                implied_probability, normalized_probability, overround, captured_at,
                is_closing_proxy, mapping_confidence, raw_json
            )
            VALUES (?, NULL, ?, ?, 'match_winner', ?, ?, ?, NULL, NULL, ?, 0, 1.0, ?)
            """,
            (
                fixture_id,
                THE_ODDS_API_SOURCE,
                bookmaker,
                selection,
                odds,
                implied_probability(odds),
                captured_at,
                json.dumps(raw_context | {"market": outcome.get("market")}, sort_keys=True, default=str),
            ),
        )
        inserted += 1
    return inserted


def _real_snapshot_exists(
    db: Database,
    fixture_id: int,
    source: str,
    bookmaker: str,
    selection: str,
    odds: float,
    captured_at: str,
) -> bool:
    row = db.query_one(
        """
        SELECT id
        FROM market_odds_snapshots
        WHERE fixture_id = ?
          AND source = ?
          AND bookmaker = ?
          AND market = 'match_winner'
          AND selection = ?
          AND decimal_odds = ?
          AND captured_at = ?
        LIMIT 1
        """,
        (fixture_id, source, bookmaker, selection, odds, captured_at),
    )
    return bool(row)


def _team_name(event: dict[str, Any], side: str) -> str:
    team = event.get(side)
    if isinstance(team, dict):
        return str(team.get("name") or "").strip()
    if isinstance(team, str):
        return team.strip()
    return ""


def _event_datetime(event: dict[str, Any]) -> datetime:
    raw_date = event.get("date")
    if raw_date:
        try:
            return datetime.fromisoformat(str(raw_date).replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/London"))
        except ValueError:
            raise ValueError(f"Invalid event date for odds-api.io event {event.get('id')}: {raw_date}")
    raw_time = event.get("time")
    try:
        timestamp = int(str(raw_time))
    except (TypeError, ValueError):
        raise ValueError(f"Missing valid event date/time for odds-api.io event {event.get('id')}.")
    return datetime.fromtimestamp(timestamp, timezone.utc).astimezone(ZoneInfo("Europe/London"))


def _odds_api_io_fixture_status(event: dict[str, Any]) -> str:
    status = str(event.get("status") or "").lower()
    if status == "live":
        return "live"
    if status in {"settled", "ended", "finished"}:
        return "finished"
    return "scheduled"


def _the_odds_api_event_datetime(event: dict[str, Any]) -> datetime:
    raw = event.get("commence_time")
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/London"))
    except ValueError:
        raise ValueError(f"Invalid commence_time for The Odds API event {event.get('id')}: {raw}")


def _latest_capture_for_sources(source_counts: list[dict[str, Any]], sources: set[str]) -> str | None:
    latest: tuple[datetime, str] | None = None
    for row in source_counts:
        if row.get("source") not in sources or not row.get("latest_capture"):
            continue
        try:
            parsed = datetime.fromisoformat(str(row["latest_capture"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        comparable = parsed.astimezone(timezone.utc)
        if latest is None or comparable > latest[0]:
            latest = (comparable, str(row["latest_capture"]))
    return latest[1] if latest else None


def _capture_freshness(captured_at: str | None) -> dict[str, Any]:
    if not captured_at:
        return {
            "status": "no_odds",
            "is_fresh": False,
            "minutes_old": None,
            "stale_after_minutes": SETTINGS.odds_stale_minutes,
        }
    try:
        parsed = datetime.fromisoformat(str(captured_at).replace("Z", "+00:00"))
    except ValueError:
        return {
            "status": "unknown",
            "is_fresh": False,
            "minutes_old": None,
            "stale_after_minutes": SETTINGS.odds_stale_minutes,
        }
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    minutes_old = max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 60)
    is_fresh = minutes_old <= SETTINGS.odds_stale_minutes
    return {
        "status": "fresh" if is_fresh else "stale",
        "is_fresh": is_fresh,
        "minutes_old": round(minutes_old, 1),
        "stale_after_minutes": SETTINGS.odds_stale_minutes,
    }


def _safe_json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "invalid_json"}
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _nullable_int(raw: str | None) -> int | None:
    if not raw:
        return None
    return int(raw)


def _stable_noise(key: str, low: float, high: float) -> float:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    value = int(digest[:10], 16) / float(0xFFFFFFFFFF)
    return low + value * (high - low)
