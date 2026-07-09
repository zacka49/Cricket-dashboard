from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .database import utc_now
from .odds_math import parse_decimal_odds


class TheOddsApiProviderError(RuntimeError):
    pass


class RetryableTheOddsApiError(TheOddsApiProviderError):
    pass


class RawTheOddsApiResult(BaseModel):
    data: Any
    raw_path: str
    rate_limit: dict[str, str | None] = Field(default_factory=dict)


class TheOddsApiSport(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    group: str = ""
    title: str = ""
    active: bool = False
    has_outrights: bool = False


class TheOddsApiOutcome(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    price: float


class TheOddsApiMarket(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    outcomes: list[TheOddsApiOutcome] = Field(default_factory=list)
    last_update: datetime | str | None = None


class TheOddsApiBookmaker(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    title: str
    last_update: datetime | str | None = None
    markets: list[TheOddsApiMarket] = Field(default_factory=list)


class TheOddsApiEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    sport_key: str
    sport_title: str = ""
    commence_time: datetime | str
    home_team: str
    away_team: str
    bookmakers: list[TheOddsApiBookmaker] = Field(default_factory=list)


class ParsedTheOddsApiOutcome(BaseModel):
    selection: str
    decimal_odds: float
    market: str
    bookmaker: str
    bookmaker_key: str
    captured_at: str


class TheOddsApiClient:
    def __init__(self, api_key: str, base_url: str, raw_dir: Path, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.raw_dir = raw_dir
        self.timeout = timeout

    def fetch_sports(self) -> RawTheOddsApiResult:
        return self._get("/v4/sports", {}, "the_odds_api_sports")

    def fetch_odds(
        self,
        sport_key: str,
        regions: str,
        markets: str,
        bookmakers: str | None = None,
    ) -> RawTheOddsApiResult:
        params = {
            "markets": markets,
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        if bookmakers:
            params["bookmakers"] = bookmakers
        else:
            params["regions"] = regions
        return self._get(f"/v4/sports/{sport_key}/odds", params, f"the_odds_api_{sport_key}_odds")

    def _get(self, path: str, params: dict[str, str], label: str) -> RawTheOddsApiResult:
        if not self.api_key:
            raise TheOddsApiProviderError("THE_ODDS_API_KEY is not set. Add it to .env or your shell environment.")
        query = dict(params)
        query["apiKey"] = self.api_key
        data, rate_limit = self._request_json(path, query)
        raw_path = self._write_raw(label, data)
        return RawTheOddsApiResult(data=data, raw_path=str(raw_path), rate_limit=rate_limit)

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, RetryableTheOddsApiError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _request_json(self, path: str, params: dict[str, str]) -> tuple[Any, dict[str, str | None]]:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout, headers={"User-Agent": "CricketEdge/0.1"}) as client:
            response = client.get(url, params=params)
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableTheOddsApiError(f"The Odds API retryable HTTP {response.status_code}: {response.text[:240]}")
        if response.status_code >= 400:
            raise TheOddsApiProviderError(f"The Odds API HTTP {response.status_code}: {response.text[:240]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise TheOddsApiProviderError("The Odds API returned invalid JSON.") from exc
        rate_limit = {
            "requests_remaining": response.headers.get("x-requests-remaining"),
            "requests_used": response.headers.get("x-requests-used"),
            "requests_last": response.headers.get("x-requests-last"),
        }
        return data, rate_limit

    def _write_raw(self, label: str, data: Any) -> Path:
        safe_label = re.sub(r"[^a-zA-Z0-9_.-]+", "_", label).strip("_")
        target = self.raw_dir / "odds" / f"{safe_label}_{utc_now().replace(':', '-')}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return target


def parse_sports(payload: Any, only_active_cricket: bool = False) -> list[TheOddsApiSport]:
    _raise_payload_error(payload)
    if not isinstance(payload, list):
        raise TheOddsApiProviderError("The Odds API sports response was not a list.")
    sports = [TheOddsApiSport.model_validate(item) for item in payload if isinstance(item, dict)]
    if only_active_cricket:
        return [sport for sport in sports if sport.active and sport.group.casefold() == "cricket"]
    return sports


def parse_odds_events(payload: Any) -> list[TheOddsApiEvent]:
    _raise_payload_error(payload)
    if not isinstance(payload, list):
        raise TheOddsApiProviderError("The Odds API odds response was not a list.")
    return [TheOddsApiEvent.model_validate(item) for item in payload if isinstance(item, dict)]


def extract_match_winner_outcomes(
    payload: Any,
    allowed_bookmakers: set[str] | None = None,
) -> list[ParsedTheOddsApiOutcome]:
    event = TheOddsApiEvent.model_validate(payload)
    allowed = {name.casefold() for name in allowed_bookmakers} if allowed_bookmakers else None
    outcomes: dict[tuple[str, str], ParsedTheOddsApiOutcome] = {}
    for bookmaker in event.bookmakers:
        if allowed is not None and bookmaker.key.casefold() not in allowed and bookmaker.title.casefold() not in allowed:
            continue
        for market in bookmaker.markets:
            if market.key != "h2h":
                continue
            captured_at = _timestamp_text(market.last_update or bookmaker.last_update)
            for row in market.outcomes:
                if row.name not in {event.home_team, event.away_team}:
                    continue
                odds = parse_decimal_odds(row.price)
                if odds and odds > 1.0:
                    outcomes[(bookmaker.key, row.name)] = ParsedTheOddsApiOutcome(
                        selection=row.name,
                        decimal_odds=round(odds, 4),
                        market=market.key,
                        bookmaker=bookmaker.title,
                        bookmaker_key=bookmaker.key,
                        captured_at=captured_at,
                    )
    return list(outcomes.values())


def _raise_payload_error(payload: Any) -> None:
    if isinstance(payload, dict) and payload.get("message"):
        raise TheOddsApiProviderError(str(payload["message"]))


def _timestamp_text(raw: datetime | str | None) -> str:
    if isinstance(raw, datetime):
        return raw.isoformat()
    return str(raw or utc_now())
