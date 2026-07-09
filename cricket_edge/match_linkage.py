from __future__ import annotations

from typing import Any

from .database import Database, utc_now
from .live_model import normalize_team_name


def link_fixture_to_cricsheet(
    db: Database, fixture_id: int, team_a: str, team_b: str, match_date: str
) -> dict[str, Any] | None:
    """Finds the real Cricsheet match for a live-tracked fixture, if one exists yet.

    Matches on exact date + normalized team names (either order). Only links when
    there is exactly one candidate -- never guesses on zero or multiple matches, so
    callers can tell "not resolved yet" from "resolved". Once linked, the link is
    stored so repeat calls (e.g. across scheduler ticks) don't re-scan.
    """
    existing = db.query_one(
        """
        SELECT m.*
        FROM fixture_cricsheet_links l
        JOIN cricsheet_matches m ON m.match_id = l.match_id
        WHERE l.fixture_id = ?
        """,
        (fixture_id,),
    )
    if existing:
        return existing

    norm_a = normalize_team_name(team_a)
    norm_b = normalize_team_name(team_b)
    candidates = db.query(
        """
        SELECT * FROM cricsheet_matches
        WHERE match_date = ?
          AND ((team_a = ? AND team_b = ?) OR (team_a = ? AND team_b = ?))
        """,
        (match_date, norm_a, norm_b, norm_b, norm_a),
    )
    if len(candidates) != 1:
        return None

    match = candidates[0]
    db.execute(
        """
        INSERT OR IGNORE INTO fixture_cricsheet_links(fixture_id, match_id, linked_at, match_method)
        VALUES (?, ?, ?, 'team_date_exact')
        """,
        (fixture_id, match["match_id"], utc_now()),
    )
    return match


def resolve_winner_for_fixture(team_a: str, team_b: str, match: dict[str, Any]) -> str | None:
    """Maps a linked Cricsheet match's winner back to the fixture's own team spelling.

    Returns None for a tie/no-result/abandoned match (`winner` is NULL) -- callers
    must treat that as void, not as "still unresolved".
    """
    winner = match.get("winner")
    if not winner:
        return None
    return team_a if winner == normalize_team_name(team_a) else team_b
