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


class OddsApiProviderError(RuntimeError):
    pass


class RetryableOddsApiError(OddsApiProviderError):
    pass


class RawApiResult(BaseModel):
    data: Any
    raw_path: str
    rate_limit: dict[str, str | None] = Field(default_factory=dict)


class OddsApiSport(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    slug: str


class OddsApiLeague(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    slug: str = ""


class OddsApiEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | int
    home: str
    away: str
    date: datetime | str
    status: str = "pending"
    league: OddsApiLeague | dict[str, Any] | None = None
    sport: OddsApiSport | dict[str, Any] | None = None


class OddsApiMarket(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    odds: list[dict[str, Any]] = Field(default_factory=list)
    updatedAt: datetime | str | None = None


class OddsApiOddsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | int
    home: str
    away: str
    date: datetime | str
    status: str = "pending"
    urls: dict[str, str] = Field(default_factory=dict)
    bookmakers: dict[str, list[OddsApiMarket]] = Field(default_factory=dict)


class ParsedOddsOutcome(BaseModel):
    selection: str
    decimal_odds: float
    market: str
    bookmaker: str
    captured_at: str | None = None


class OddsApiIoClient:
    def __init__(self, api_key: str, base_url: str, raw_dir: Path, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.raw_dir = raw_dir
        self.timeout = timeout

    def fetch_sports(self) -> RawApiResult:
        return self._get("/sports", {}, "odds_api_io_sports", requires_key=False)

    def fetch_events(self, sport: str, status: str | None = None, limit: int | None = None) -> RawApiResult:
        params: dict[str, str] = {"sport": sport}
        if status:
            params["status"] = status
        if limit:
            params["limit"] = str(limit)
        return self._get("/events", params, f"odds_api_io_events_{sport}_{status or 'all'}")

    def fetch_event_odds(self, event_id: str | int, bookmakers: str) -> RawApiResult:
        return self._get(
            "/odds",
            {"eventId": str(event_id), "bookmakers": bookmakers},
            f"odds_api_io_event_{event_id}",
        )

    def _get(self, path: str, params: dict[str, str], label: str, requires_key: bool = True) -> RawApiResult:
        if requires_key and not self.api_key:
            raise OddsApiProviderError("ODDS_API_KEY is not set. Add it to .env or your shell environment.")
        query = dict(params)
        if requires_key:
            query["apiKey"] = self.api_key
        data, rate_limit = self._request_json(path, query)
        raw_path = self._write_raw(label, data)
        return RawApiResult(data=data, raw_path=str(raw_path), rate_limit=rate_limit)

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, RetryableOddsApiError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _request_json(self, path: str, params: dict[str, str]) -> tuple[Any, dict[str, str | None]]:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout, headers={"User-Agent": "CricketEdge/0.1"}) as client:
            response = client.get(url, params=params)
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableOddsApiError(f"odds-api.io retryable HTTP {response.status_code}: {response.text[:240]}")
        if response.status_code >= 400:
            raise OddsApiProviderError(f"odds-api.io HTTP {response.status_code}: {response.text[:240]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise OddsApiProviderError("odds-api.io returned invalid JSON.") from exc
        rate_limit = {
            "limit": response.headers.get("X-RateLimit-Limit"),
            "remaining": response.headers.get("X-RateLimit-Remaining"),
            "reset": response.headers.get("X-RateLimit-Reset"),
        }
        return data, rate_limit

    def _write_raw(self, label: str, data: Any) -> Path:
        safe_label = re.sub(r"[^a-zA-Z0-9_.-]+", "_", label).strip("_")
        target = self.raw_dir / "odds" / f"{safe_label}_{utc_now().replace(':', '-')}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return target


def parse_sports(payload: Any) -> list[OddsApiSport]:
    _raise_payload_error(payload)
    if not isinstance(payload, list):
        raise OddsApiProviderError("odds-api.io sports response was not a list.")
    return [OddsApiSport.model_validate(item) for item in payload if isinstance(item, dict)]


def parse_events(payload: Any) -> list[OddsApiEvent]:
    _raise_payload_error(payload)
    if not isinstance(payload, list):
        raise OddsApiProviderError("odds-api.io events response was not a list.")
    return [OddsApiEvent.model_validate(item) for item in payload if isinstance(item, dict)]


def parse_odds_response(payload: Any) -> OddsApiOddsResponse:
    _raise_payload_error(payload)
    if not isinstance(payload, dict):
        raise OddsApiProviderError("odds-api.io odds response was not an object.")
    return OddsApiOddsResponse.model_validate(payload)


def extract_match_winner_outcomes(
    payload: Any,
    allowed_bookmakers: set[str] | None = None,
) -> list[ParsedOddsOutcome]:
    response = parse_odds_response(payload)
    outcomes: dict[tuple[str, str], ParsedOddsOutcome] = {}
    allowed = {name.casefold() for name in allowed_bookmakers} if allowed_bookmakers else None
    for bookmaker, markets in response.bookmakers.items():
        if allowed is not None and bookmaker.casefold() not in allowed:
            continue
        for market in markets:
            market_name = market.name or "ML"
            if not _is_match_winner_market(market_name):
                continue
            for row in market.odds:
                home_odds = parse_decimal_odds(row.get("home"))
                away_odds = parse_decimal_odds(row.get("away"))
                captured = str(market.updatedAt) if market.updatedAt else None
                if home_odds and home_odds > 1.0:
                    outcomes[(bookmaker, response.home)] = ParsedOddsOutcome(
                        selection=response.home,
                        decimal_odds=round(home_odds, 4),
                        market=market_name,
                        bookmaker=bookmaker,
                        captured_at=captured,
                    )
                if away_odds and away_odds > 1.0:
                    outcomes[(bookmaker, response.away)] = ParsedOddsOutcome(
                        selection=response.away,
                        decimal_odds=round(away_odds, 4),
                        market=market_name,
                        bookmaker=bookmaker,
                        captured_at=captured,
                    )
    return list(outcomes.values())


def _raise_payload_error(payload: Any) -> None:
    if isinstance(payload, dict) and payload.get("error"):
        raise OddsApiProviderError(str(payload["error"]))


def _is_match_winner_market(raw: str) -> bool:
    text = raw.strip().lower()
    return text in {"ml", "moneyline"} or any(
        part in text for part in ("match winner", "to win match", "match betting")
    )
