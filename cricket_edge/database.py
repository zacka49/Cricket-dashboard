from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import SETTINGS, ensure_directories


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path | str | None = None) -> None:
        ensure_directories()
        if str(path) == ":memory:":
            self.path: Path | str = ":memory:"
        else:
            self.path = Path(path or SETTINGS.database_path)
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            return int(cursor.lastrowid or 0)

    def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> None:
        with self.connect() as conn:
            conn.executemany(sql, params)

    def log_event(self, event_type: str, message: str, payload: dict[str, Any] | None = None) -> None:
        self.execute(
            """
            INSERT INTO events(timestamp, type, message, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (utc_now(), event_type, message, json.dumps(payload or {}, sort_keys=True, default=str)),
        )


SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    starting_bankroll REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fixtures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    competition TEXT NOT NULL,
    format TEXT NOT NULL,
    team_a TEXT NOT NULL,
    team_b TEXT NOT NULL,
    venue TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    result_winner TEXT,
    weather_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'demo',
    created_at TEXT NOT NULL,
    UNIQUE(match_date, start_time, team_a, team_b, venue)
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    odds REAL NOT NULL,
    source TEXT NOT NULL,
    captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    probability REAL NOT NULL,
    fair_odds REAL NOT NULL,
    market_odds REAL NOT NULL,
    edge REAL NOT NULL,
    confidence REAL NOT NULL,
    features_json TEXT NOT NULL,
    UNIQUE(fixture_id, model_name, market, selection)
);

CREATE TABLE IF NOT EXISTS agent_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER REFERENCES fixtures(id) ON DELETE SET NULL,
    agent_name TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    decision TEXT NOT NULL,
    stake REAL NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0,
    reason TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    decision_id INTEGER REFERENCES agent_decisions(id) ON DELETE SET NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    stake REAL NOT NULL,
    odds REAL NOT NULL,
    status TEXT NOT NULL,
    placed_at TEXT NOT NULL,
    closed_at TEXT,
    pnl REAL NOT NULL DEFAULT 0,
    cashout_value REAL NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS cricsheet_matches (
    match_id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    match_date TEXT NOT NULL,
    competition TEXT NOT NULL,
    gender TEXT NOT NULL,
    match_type TEXT NOT NULL,
    team_a TEXT NOT NULL,
    team_b TEXT NOT NULL,
    venue TEXT NOT NULL,
    city TEXT NOT NULL,
    toss_winner TEXT,
    toss_decision TEXT,
    winner TEXT,
    outcome TEXT NOT NULL,
    team_a_runs INTEGER NOT NULL DEFAULT 0,
    team_a_wickets INTEGER NOT NULL DEFAULT 0,
    team_a_balls INTEGER NOT NULL DEFAULT 0,
    team_b_runs INTEGER NOT NULL DEFAULT 0,
    team_b_wickets INTEGER NOT NULL DEFAULT 0,
    team_b_balls INTEGER NOT NULL DEFAULT 0,
    inserted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fixture_cricsheet_links (
    fixture_id INTEGER PRIMARY KEY REFERENCES fixtures(id) ON DELETE CASCADE,
    match_id TEXT NOT NULL REFERENCES cricsheet_matches(match_id) ON DELETE CASCADE,
    linked_at TEXT NOT NULL,
    match_method TEXT NOT NULL DEFAULT 'team_date_exact'
);

CREATE TABLE IF NOT EXISTS cricsheet_innings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL REFERENCES cricsheet_matches(match_id) ON DELETE CASCADE,
    innings_number INTEGER NOT NULL,
    batting_team TEXT NOT NULL,
    runs INTEGER NOT NULL,
    wickets INTEGER NOT NULL,
    legal_balls INTEGER NOT NULL,
    UNIQUE(match_id, innings_number)
);

CREATE TABLE IF NOT EXISTS team_elo_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL REFERENCES cricsheet_matches(match_id) ON DELETE CASCADE,
    match_date TEXT NOT NULL,
    competition TEXT NOT NULL,
    team_a TEXT NOT NULL,
    team_b TEXT NOT NULL,
    winner TEXT NOT NULL,
    pre_elo_a REAL NOT NULL,
    pre_elo_b REAL NOT NULL,
    pred_a REAL NOT NULL,
    pred_b REAL NOT NULL,
    result_a REAL NOT NULL,
    post_elo_a REAL NOT NULL,
    post_elo_b REAL NOT NULL,
    brier REAL NOT NULL,
    log_loss REAL NOT NULL,
    correct INTEGER NOT NULL,
    UNIQUE(match_id)
);

CREATE TABLE IF NOT EXISTS model_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    n_matches INTEGER NOT NULL,
    brier REAL NOT NULL,
    log_loss REAL NOT NULL,
    accuracy REAL NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    match_id TEXT NOT NULL REFERENCES cricsheet_matches(match_id) ON DELETE CASCADE,
    split TEXT NOT NULL,
    match_date TEXT NOT NULL,
    competition TEXT NOT NULL,
    team_a TEXT NOT NULL,
    team_b TEXT NOT NULL,
    winner TEXT NOT NULL,
    pred_a REAL NOT NULL,
    result_a REAL NOT NULL,
    brier REAL NOT NULL,
    log_loss REAL NOT NULL,
    correct INTEGER NOT NULL,
    features_json TEXT NOT NULL,
    UNIQUE(model_name, match_id)
);

CREATE TABLE IF NOT EXISTS model_registry (
    model_name TEXT PRIMARY KEY,
    model_family TEXT NOT NULL,
    timing TEXT NOT NULL,
    status TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    calibrated INTEGER NOT NULL DEFAULT 0,
    feature_names_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS market_odds_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id INTEGER REFERENCES fixtures(id) ON DELETE SET NULL,
    match_id TEXT REFERENCES cricsheet_matches(match_id) ON DELETE SET NULL,
    source TEXT NOT NULL,
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    decimal_odds REAL NOT NULL,
    implied_probability REAL NOT NULL,
    normalized_probability REAL,
    overround REAL,
    captured_at TEXT NOT NULL,
    is_closing_proxy INTEGER NOT NULL DEFAULT 0,
    mapping_confidence REAL NOT NULL DEFAULT 1.0,
    raw_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS market_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    scope TEXT NOT NULL,
    fixture_id INTEGER REFERENCES fixtures(id) ON DELETE SET NULL,
    match_id TEXT REFERENCES cricsheet_matches(match_id) ON DELETE SET NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    probability REAL NOT NULL,
    decimal_odds REAL NOT NULL,
    overround REAL NOT NULL DEFAULT 0,
    captured_at TEXT NOT NULL,
    result REAL,
    brier REAL,
    log_loss REAL,
    correct INTEGER,
    source TEXT NOT NULL,
    UNIQUE(model_name, scope, fixture_id, match_id, market, selection, captured_at)
);

CREATE TABLE IF NOT EXISTS paper_bet_evaluations (
    bet_id INTEGER PRIMARY KEY REFERENCES paper_bets(id) ON DELETE CASCADE,
    entry_odds REAL NOT NULL,
    latest_odds REAL,
    closing_odds REAL,
    clv REAL,
    latest_checked_at TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    n_candidates INTEGER NOT NULL,
    bets INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    staked REAL NOT NULL,
    pnl REAL NOT NULL,
    roi REAL NOT NULL,
    yield REAL NOT NULL,
    max_drawdown REAL NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fixtures_date ON fixtures(match_date);
CREATE INDEX IF NOT EXISTS idx_odds_fixture ON odds_snapshots(fixture_id, market, selection, captured_at);
CREATE INDEX IF NOT EXISTS idx_predictions_fixture ON predictions(fixture_id, market, selection);
CREATE INDEX IF NOT EXISTS idx_bets_status ON paper_bets(status);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_cricsheet_matches_date ON cricsheet_matches(match_date);
CREATE INDEX IF NOT EXISTS idx_cricsheet_matches_teams ON cricsheet_matches(team_a, team_b);
CREATE INDEX IF NOT EXISTS idx_fixture_cricsheet_links_match ON fixture_cricsheet_links(match_id);
CREATE INDEX IF NOT EXISTS idx_team_elo_date ON team_elo_history(match_date);
CREATE INDEX IF NOT EXISTS idx_model_predictions_model ON model_predictions(model_name, split, match_date);
CREATE INDEX IF NOT EXISTS idx_model_registry_active ON model_registry(active, status);
CREATE INDEX IF NOT EXISTS idx_market_odds_fixture ON market_odds_snapshots(fixture_id, market, captured_at);
CREATE INDEX IF NOT EXISTS idx_market_odds_match ON market_odds_snapshots(match_id, market, captured_at);
CREATE INDEX IF NOT EXISTS idx_market_baselines_model ON market_baselines(model_name, scope, captured_at);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_model ON backtest_runs(model_name, generated_at);
"""
