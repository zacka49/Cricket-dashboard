from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DB_PATH = DATA_DIR / "cricket_edge.sqlite3"


def _load_local_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


_load_local_env()


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if not raw:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    """Runtime configuration.

    Real-money execution is deliberately not represented here. The broker in
    this project is paper-only by design.
    """

    host: str = os.getenv("CRICKET_EDGE_HOST", "127.0.0.1")
    port: int = _env_int("CRICKET_EDGE_PORT", 8765)
    database_path: Path = Path(os.getenv("CRICKET_EDGE_DB", str(DB_PATH)))
    starting_bankroll: float = _env_float("CRICKET_EDGE_STARTING_BANKROLL", 1000.0)
    max_stake_fraction: float = _env_float("CRICKET_EDGE_MAX_STAKE_FRACTION", 0.01)
    max_daily_exposure_fraction: float = _env_float("CRICKET_EDGE_MAX_DAILY_EXPOSURE_FRACTION", 0.08)
    max_portfolio_run_exposure_fraction: float = _env_float(
        "CRICKET_EDGE_MAX_PORTFOLIO_RUN_EXPOSURE_FRACTION", 0.08
    )
    min_edge: float = _env_float("CRICKET_EDGE_MIN_EDGE", 0.035)
    min_confidence: float = _env_float("CRICKET_EDGE_MIN_CONFIDENCE", 0.56)
    odds_stale_minutes: int = _env_int("CRICKET_EDGE_ODDS_STALE_MINUTES", 30)
    odds_api_key: str = os.getenv("ODDS_API_KEY", os.getenv("BET365_API_KEY", ""))
    odds_api_regions: str = os.getenv("ODDS_API_REGIONS", "uk")
    odds_api_bookmakers: str = os.getenv("ODDS_API_BOOKMAKERS", "Bet365")
    odds_api_io_base_url: str = os.getenv("ODDS_API_IO_BASE_URL", "https://api.odds-api.io/v3")
    odds_api_io_sport: str = os.getenv("ODDS_API_IO_SPORT", "cricket")
    odds_api_max_events: int = _env_int("ODDS_API_MAX_EVENTS", 25)
    odds_api_max_workers: int = _env_int("ODDS_API_MAX_WORKERS", 6)
    odds_api_overall_timeout_seconds: int = _env_int("ODDS_API_OVERALL_TIMEOUT_SECONDS", 45)
    the_odds_api_key: str = os.getenv("THE_ODDS_API_KEY", "")
    the_odds_api_base_url: str = os.getenv("THE_ODDS_API_BASE_URL", "https://api.the-odds-api.com")
    the_odds_api_regions: str = os.getenv("THE_ODDS_API_REGIONS", "uk,eu,au")
    the_odds_api_markets: str = os.getenv("THE_ODDS_API_MARKETS", "h2h")
    the_odds_api_bookmakers: str = os.getenv("THE_ODDS_API_BOOKMAKERS", "")
    the_odds_api_sport_keys: str = os.getenv(
        "THE_ODDS_API_SPORT_KEYS",
        "cricket_international_t20,cricket_t20_blast,cricket_ipl,cricket_odi,cricket_test_match",
    )
    the_odds_api_max_sports: int = _env_int("THE_ODDS_API_MAX_SPORTS", 5)
    bet365_api_key: str = os.getenv("BET365_API_KEY", os.getenv("BETSAPI_TOKEN", ""))
    bet365_base_url: str = os.getenv("BET365_BASE_URL", "https://api.b365api.com")
    bet365_auth_param: str = os.getenv("BET365_AUTH_PARAM", "token")
    bet365_max_events: int = _env_int("BET365_MAX_EVENTS", 25)
    scheduler_enabled: bool = _env_bool("CRICKET_EDGE_SCHEDULER_ENABLED", True)
    scheduler_tick_seconds: int = _env_int("CRICKET_EDGE_SCHEDULER_TICK_SECONDS", 300)
    scheduler_retrain_interval_hours: int = _env_int("CRICKET_EDGE_SCHEDULER_RETRAIN_INTERVAL_HOURS", 24)
    scheduler_retrain_new_match_threshold: int = _env_int(
        "CRICKET_EDGE_SCHEDULER_RETRAIN_NEW_MATCH_THRESHOLD", 20
    )


def ensure_directories() -> None:
    for path in (DATA_DIR, RAW_DIR, PROCESSED_DIR):
        path.mkdir(parents=True, exist_ok=True)


SETTINGS = Settings()
