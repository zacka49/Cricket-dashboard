from __future__ import annotations

from typing import Any

from .config import RAW_DIR, SETTINGS
from .data_sources import FreeDataSources
from .database import Database, utc_now
from .market import fetch_bet365_cricket_odds


def pull_all_live_data(db: Database, refresh_cricsheet: bool = True) -> dict[str, Any]:
    """Fetch every free live/historical data source this project supports and persist it.

    Odds (Bet365 via odds-api.io, with The Odds API as fallback) are saved both as raw
    JSON snapshots under data/raw/odds and as structured rows in market_odds_snapshots /
    odds_snapshots, so every pull is available later for backtesting or CLV analysis.
    """
    db.init_schema()
    started_at = utc_now()

    odds_result = fetch_bet365_cricket_odds(db)

    cricsheet_path: str | None = None
    cricsheet_error: str | None = None
    if refresh_cricsheet:
        try:
            cricsheet_path = str(FreeDataSources(db).download_cricsheet_t20_json_zip())
        except Exception as exc:
            cricsheet_error = str(exc)

    summary = {
        "started_at": started_at,
        "finished_at": utc_now(),
        "odds": {
            "ok": odds_result.get("ok", False),
            "provider": odds_result.get("provider"),
            "events_checked": odds_result.get("events_checked", 0),
            "odds_rows_inserted": odds_result.get("odds_rows_inserted", 0),
            "fallback_used": odds_result.get("fallback_used", False),
            "errors": odds_result.get("errors", []),
            "needs_api_key": odds_result.get("needs_api_key", False),
        },
        "cricsheet_archive": cricsheet_path,
        "cricsheet_error": cricsheet_error,
        "raw_data_dir": str(RAW_DIR),
        "keys_configured": {
            "odds_api_key": bool(SETTINGS.odds_api_key),
            "the_odds_api_key": bool(SETTINGS.the_odds_api_key),
        },
    }
    db.log_event("ingestion", "Pulled all available free live data sources.", summary)
    return summary
