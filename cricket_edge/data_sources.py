from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import RAW_DIR, SETTINGS
from .database import Database, utc_now
from .odds_api_io import OddsApiIoClient
from .the_odds_api import TheOddsApiClient


CRICSHEET_T20_JSON_ZIP = "https://cricsheet.org/downloads/t20s_json.zip"
CRICSHEET_T20_CSV_ZIP = "https://cricsheet.org/downloads/t20s_csv2.zip"
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
ODDS_API_CRICKET = "https://api.the-odds-api.com/v4/sports/cricket/odds"
BETSAPI_CRICKET_SPORT_ID = "3"
CRICSHEET_REFRESH_SECONDS = 24 * 60 * 60


class FreeDataSources:
    """Free-source adapters.

    These methods are deliberately simple and safe. They store raw responses
    first, then the modelling pipeline can choose what to parse.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def download_cricsheet_t20_json_zip(self, force: bool = False) -> Path:
        target = RAW_DIR / "cricsheet" / "t20s_json.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
        age_seconds = time.time() - target.stat().st_mtime if target.exists() else None
        is_stale = age_seconds is None or age_seconds > CRICSHEET_REFRESH_SECONDS
        if force or not target.exists() or target.stat().st_size == 0 or is_stale:
            urllib.request.urlretrieve(CRICSHEET_T20_JSON_ZIP, target)
            self.db.log_event("ingestion", "Downloaded Cricsheet T20 JSON zip.", {"path": str(target)})
        else:
            self.db.log_event(
                "ingestion",
                "Cricsheet T20 JSON zip already fresh; skipped re-download.",
                {"path": str(target), "age_seconds": round(age_seconds, 0)},
            )
        return target

    def fetch_open_meteo_forecast(self, latitude: float, longitude: float, label: str) -> dict[str, Any]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,wind_speed_10m",
            "forecast_days": 3,
            "timezone": "Europe/London",
        }
        url = f"{OPEN_METEO_FORECAST}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        target = RAW_DIR / "weather" / f"{label.lower().replace(' ', '_')}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.db.log_event("ingestion", f"Fetched Open-Meteo forecast for {label}.", {"path": str(target)})
        return data

    def fetch_odds_api_cricket(self, regions: str = "uk", markets: str = "h2h") -> dict[str, Any]:
        if not SETTINGS.odds_api_key:
            raise RuntimeError("ODDS_API_KEY is not set. The Odds API free tier requires an API key.")
        params = {
            "apiKey": SETTINGS.odds_api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal",
        }
        url = f"{ODDS_API_CRICKET}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        target = RAW_DIR / "odds" / f"odds_api_cricket_{utc_now().replace(':', '-')}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.db.log_event("ingestion", "Fetched cricket odds from The Odds API.", {"path": str(target)})
        return data

    def fetch_odds_api_io_sports(self) -> dict[str, Any]:
        result = self._odds_api_io_client().fetch_sports()
        return self._record_odds_api_io_result(result, "sports")

    def fetch_odds_api_io_events(self, sport: str, status: str | None = None, limit: int | None = None) -> dict[str, Any]:
        result = self._odds_api_io_client().fetch_events(sport=sport, status=status, limit=limit)
        return self._record_odds_api_io_result(result, f"events_{sport}_{status or 'all'}")

    def fetch_odds_api_io_event_odds(self, event_id: str | int, bookmakers: str) -> dict[str, Any]:
        result = self._odds_api_io_client().fetch_event_odds(event_id=event_id, bookmakers=bookmakers)
        return self._record_odds_api_io_result(result, f"event_{event_id}")

    def fetch_the_odds_api_sports(self) -> dict[str, Any]:
        result = self._the_odds_api_client().fetch_sports()
        return self._record_the_odds_api_result(result, "sports")

    def fetch_the_odds_api_odds(
        self,
        sport_key: str,
        regions: str,
        markets: str,
        bookmakers: str | None = None,
    ) -> dict[str, Any]:
        result = self._the_odds_api_client().fetch_odds(
            sport_key=sport_key,
            regions=regions,
            markets=markets,
            bookmakers=bookmakers,
        )
        return self._record_the_odds_api_result(result, f"{sport_key}_odds")

    def _odds_api_io_client(self) -> OddsApiIoClient:
        return OddsApiIoClient(
            api_key=SETTINGS.odds_api_key,
            base_url=SETTINGS.odds_api_io_base_url,
            raw_dir=RAW_DIR,
        )

    def _the_odds_api_client(self) -> TheOddsApiClient:
        return TheOddsApiClient(
            api_key=SETTINGS.the_odds_api_key,
            base_url=SETTINGS.the_odds_api_base_url,
            raw_dir=RAW_DIR,
        )

    def _record_odds_api_io_result(self, result: Any, label: str) -> dict[str, Any]:
        self.db.log_event(
            "ingestion",
            f"Fetched odds-api.io data: {label}.",
            {"path": result.raw_path, "rate_limit": {k: v for k, v in result.rate_limit.items() if v}},
        )
        return {"data": result.data, "raw_path": result.raw_path, "rate_limit": result.rate_limit}

    def _record_the_odds_api_result(self, result: Any, label: str) -> dict[str, Any]:
        self.db.log_event(
            "ingestion",
            f"Fetched The Odds API data: {label}.",
            {"path": result.raw_path, "rate_limit": {k: v for k, v in result.rate_limit.items() if v}},
        )
        return {"data": result.data, "raw_path": result.raw_path, "rate_limit": result.rate_limit}

    def fetch_bet365_upcoming_cricket(self, page: int = 1) -> dict[str, Any]:
        return self._fetch_bet365_json(
            "/v1/bet365/upcoming",
            {"sport_id": BETSAPI_CRICKET_SPORT_ID, "page": str(page)},
            f"bet365_upcoming_cricket_p{page}",
        )

    def fetch_bet365_inplay_cricket(self) -> dict[str, Any]:
        return self._fetch_bet365_json(
            "/v1/bet365/inplay_filter",
            {"sport_id": BETSAPI_CRICKET_SPORT_ID},
            "bet365_inplay_cricket",
        )

    def fetch_bet365_prematch_odds(self, fixture_id: str) -> dict[str, Any]:
        return self._fetch_bet365_json(
            "/v4/bet365/prematch",
            {"FI": fixture_id},
            f"bet365_prematch_{fixture_id}",
        )

    def fetch_bet365_inplay_event(self, fixture_id: str) -> dict[str, Any]:
        return self._fetch_bet365_json(
            "/v1/bet365/event",
            {"FI": fixture_id, "stats": "1"},
            f"bet365_inplay_event_{fixture_id}",
        )

    def _fetch_bet365_json(self, path: str, params: dict[str, str], label: str) -> dict[str, Any]:
        if not SETTINGS.bet365_api_key:
            raise RuntimeError("BET365_API_KEY is not set. Add it to .env or your shell environment.")
        query = dict(params)
        query[SETTINGS.bet365_auth_param or "token"] = SETTINGS.bet365_api_key
        url = f"{SETTINGS.bet365_base_url.rstrip('/')}{path}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(url, headers={"User-Agent": "CricketEdge/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            headers = {
                "limit": response.headers.get("X-RateLimit-Limit"),
                "remaining": response.headers.get("X-RateLimit-Remaining"),
                "reset": response.headers.get("X-RateLimit-Reset"),
            }
        target = RAW_DIR / "odds" / f"{label}_{utc_now().replace(':', '-')}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.db.log_event(
            "ingestion",
            f"Fetched Bet365 cricket data: {label}.",
            {"path": str(target), "rate_limit": {k: v for k, v in headers.items() if v}},
        )
        return {"data": data, "raw_path": str(target), "rate_limit": headers}
