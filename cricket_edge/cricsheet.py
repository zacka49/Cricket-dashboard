from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database import Database, utc_now


@dataclass(frozen=True)
class IngestStats:
    files_seen: int
    matches_inserted: int
    innings_inserted: int
    skipped: int


def ingest_t20_json_zip(db: Database, zip_path: Path, limit: int | None = None) -> IngestStats:
    db.init_schema()
    files_seen = 0
    matches_inserted = 0
    innings_inserted = 0
    skipped = 0

    with zipfile.ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".json")]
        names.sort()
        if limit:
            names = names[:limit]

        with db.connect() as conn:
            for name in names:
                files_seen += 1
                try:
                    payload = json.loads(archive.read(name).decode("utf-8"))
                    parsed = parse_match_json(name, payload)
                except (json.JSONDecodeError, KeyError, TypeError, UnicodeDecodeError):
                    skipped += 1
                    continue

                if not parsed:
                    skipped += 1
                    continue

                match_row, innings_rows = parsed
                inserted = _upsert_match_conn(conn, match_row)
                if inserted:
                    matches_inserted += 1
                for innings in innings_rows:
                    _upsert_innings_conn(conn, innings)
                    innings_inserted += 1

    db.log_event(
        "ingestion",
        "Ingested Cricsheet T20 JSON archive.",
        {
            "zip_path": str(zip_path),
            "files_seen": files_seen,
            "matches_inserted": matches_inserted,
            "innings_inserted": innings_inserted,
            "skipped": skipped,
        },
    )
    return IngestStats(files_seen, matches_inserted, innings_inserted, skipped)


def parse_match_json(source_file: str, payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    info = payload.get("info", {})
    teams = info.get("teams") or []
    if len(teams) != 2:
        return None
    dates = info.get("dates") or []
    match_date = str(dates[0]) if dates else ""
    if not match_date:
        return None

    innings_payload = payload.get("innings") or []
    innings_rows = []
    totals_by_team: dict[str, dict[str, int]] = {str(teams[0]): _empty_total(), str(teams[1]): _empty_total()}
    match_id = Path(source_file).stem

    for idx, innings in enumerate(innings_payload, start=1):
        batting_team = str(innings.get("team", ""))
        total = _aggregate_innings(innings)
        if batting_team in totals_by_team:
            totals_by_team[batting_team] = total
        innings_rows.append(
            {
                "match_id": match_id,
                "innings_number": idx,
                "batting_team": batting_team,
                "runs": total["runs"],
                "wickets": total["wickets"],
                "legal_balls": total["legal_balls"],
            }
        )

    outcome = info.get("outcome") or {}
    winner = outcome.get("winner")
    if not winner:
        if "result" in outcome:
            winner = None
            outcome_text = str(outcome.get("result"))
        else:
            outcome_text = "unknown"
    else:
        outcome_text = "winner"

    toss = info.get("toss") or {}
    event = info.get("event") or {}
    team_a = str(teams[0])
    team_b = str(teams[1])
    team_a_total = totals_by_team.get(team_a, _empty_total())
    team_b_total = totals_by_team.get(team_b, _empty_total())

    match_row = {
        "match_id": match_id,
        "source_file": source_file,
        "match_date": match_date,
        "competition": str(event.get("name") or info.get("competition") or "Unknown"),
        "gender": str(info.get("gender") or "unknown"),
        "match_type": str(info.get("match_type") or "T20"),
        "team_a": team_a,
        "team_b": team_b,
        "venue": str(info.get("venue") or "Unknown"),
        "city": str(info.get("city") or ""),
        "toss_winner": toss.get("winner"),
        "toss_decision": toss.get("decision"),
        "winner": winner,
        "outcome": outcome_text,
        "team_a_runs": team_a_total["runs"],
        "team_a_wickets": team_a_total["wickets"],
        "team_a_balls": team_a_total["legal_balls"],
        "team_b_runs": team_b_total["runs"],
        "team_b_wickets": team_b_total["wickets"],
        "team_b_balls": team_b_total["legal_balls"],
        "inserted_at": utc_now(),
    }
    return match_row, innings_rows


def _empty_total() -> dict[str, int]:
    return {"runs": 0, "wickets": 0, "legal_balls": 0}


def _aggregate_innings(innings: dict[str, Any]) -> dict[str, int]:
    total = _empty_total()
    for over in innings.get("overs") or []:
        for delivery in over.get("deliveries") or []:
            runs = delivery.get("runs") or {}
            total["runs"] += int(runs.get("total") or 0)
            extras = delivery.get("extras") or {}
            if "wides" not in extras:
                total["legal_balls"] += 1
            total["wickets"] += len(delivery.get("wickets") or [])
    return total


def _upsert_match(db: Database, row: dict[str, Any]) -> bool:
    with db.connect() as conn:
        return _upsert_match_conn(conn, row)


def _upsert_match_conn(conn: Any, row: dict[str, Any]) -> bool:
    existing = conn.execute("SELECT match_id FROM cricsheet_matches WHERE match_id = ?", (row["match_id"],)).fetchone()
    conn.execute(
        """
        INSERT INTO cricsheet_matches(
            match_id, source_file, match_date, competition, gender, match_type,
            team_a, team_b, venue, city, toss_winner, toss_decision, winner,
            outcome, team_a_runs, team_a_wickets, team_a_balls, team_b_runs,
            team_b_wickets, team_b_balls, inserted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id) DO UPDATE SET
            source_file = excluded.source_file,
            match_date = excluded.match_date,
            competition = excluded.competition,
            gender = excluded.gender,
            match_type = excluded.match_type,
            team_a = excluded.team_a,
            team_b = excluded.team_b,
            venue = excluded.venue,
            city = excluded.city,
            toss_winner = excluded.toss_winner,
            toss_decision = excluded.toss_decision,
            winner = excluded.winner,
            outcome = excluded.outcome,
            team_a_runs = excluded.team_a_runs,
            team_a_wickets = excluded.team_a_wickets,
            team_a_balls = excluded.team_a_balls,
            team_b_runs = excluded.team_b_runs,
            team_b_wickets = excluded.team_b_wickets,
            team_b_balls = excluded.team_b_balls
        """,
        (
            row["match_id"],
            row["source_file"],
            row["match_date"],
            row["competition"],
            row["gender"],
            row["match_type"],
            row["team_a"],
            row["team_b"],
            row["venue"],
            row["city"],
            row["toss_winner"],
            row["toss_decision"],
            row["winner"],
            row["outcome"],
            row["team_a_runs"],
            row["team_a_wickets"],
            row["team_a_balls"],
            row["team_b_runs"],
            row["team_b_wickets"],
            row["team_b_balls"],
            row["inserted_at"],
        ),
    )
    return existing is None


def _upsert_innings(db: Database, row: dict[str, Any]) -> None:
    with db.connect() as conn:
        _upsert_innings_conn(conn, row)


def _upsert_innings_conn(conn: Any, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO cricsheet_innings(match_id, innings_number, batting_team, runs, wickets, legal_balls)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id, innings_number) DO UPDATE SET
            batting_team = excluded.batting_team,
            runs = excluded.runs,
            wickets = excluded.wickets,
            legal_balls = excluded.legal_balls
        """,
        (
            row["match_id"],
            row["innings_number"],
            row["batting_team"],
            row["runs"],
            row["wickets"],
            row["legal_balls"],
        ),
    )
