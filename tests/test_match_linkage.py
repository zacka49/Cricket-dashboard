from pathlib import Path

from cricket_edge.database import Database, utc_now
from cricket_edge.match_linkage import link_fixture_to_cricsheet, resolve_winner_for_fixture


def _insert_fixture(db: Database, team_a: str, team_b: str, match_date: str) -> int:
    return db.execute(
        """
        INSERT INTO fixtures(
            match_date, start_time, competition, format, team_a, team_b, venue,
            status, source, created_at
        )
        VALUES (?, '09:00', 'Test League', 'T20', ?, ?, 'Test Ground', 'scheduled', 'bet365', ?)
        """,
        (match_date, team_a, team_b, utc_now()),
    )


def _insert_cricsheet_match(
    db: Database, match_id: str, match_date: str, team_a: str, team_b: str, winner: str | None
) -> None:
    db.execute(
        """
        INSERT INTO cricsheet_matches(
            match_id, source_file, match_date, competition, gender, match_type,
            team_a, team_b, venue, city, winner, outcome,
            team_a_runs, team_a_wickets, team_a_balls,
            team_b_runs, team_b_wickets, team_b_balls, inserted_at
        )
        VALUES (?, 'test.json', ?, 'Test League', 'male', 'T20', ?, ?, 'Test Ground', 'Test City',
                ?, 'normal', 160, 6, 120, 150, 7, 120, ?)
        """,
        (match_id, match_date, team_a, team_b, winner, utc_now()),
    )


def test_links_fixture_by_normalized_team_names_and_date(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "USA", "Hong Kong, China", "2026-05-01")
    _insert_cricsheet_match(db, "m1", "2026-05-01", "United States of America", "Hong Kong", "Hong Kong")

    match = link_fixture_to_cricsheet(db, fixture_id, "USA", "Hong Kong, China", "2026-05-01")

    assert match is not None
    assert match["match_id"] == "m1"


def test_links_fixture_regardless_of_team_order(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Beta", "Alpha", "2026-05-01")
    _insert_cricsheet_match(db, "m1", "2026-05-01", "Alpha", "Beta", "Alpha")

    match = link_fixture_to_cricsheet(db, fixture_id, "Beta", "Alpha", "2026-05-01")

    assert match is not None
    assert match["match_id"] == "m1"


def test_returns_none_when_no_candidate_exists(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta", "2026-05-01")

    assert link_fixture_to_cricsheet(db, fixture_id, "Alpha", "Beta", "2026-05-01") is None


def test_refuses_to_guess_when_multiple_candidates_exist(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta", "2026-05-01")
    _insert_cricsheet_match(db, "m1", "2026-05-01", "Alpha", "Beta", "Alpha")
    _insert_cricsheet_match(db, "m2", "2026-05-01", "Alpha", "Beta", "Beta")

    assert link_fixture_to_cricsheet(db, fixture_id, "Alpha", "Beta", "2026-05-01") is None


def test_link_is_idempotent_and_reuses_stored_link(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta", "2026-05-01")
    _insert_cricsheet_match(db, "m1", "2026-05-01", "Alpha", "Beta", "Alpha")

    first = link_fixture_to_cricsheet(db, fixture_id, "Alpha", "Beta", "2026-05-01")
    # A second cricsheet match with the same teams/date appears later -- since a
    # link already exists, it must not be re-scanned into an ambiguous result.
    _insert_cricsheet_match(db, "m2", "2026-05-01", "Alpha", "Beta", "Beta")
    second = link_fixture_to_cricsheet(db, fixture_id, "Alpha", "Beta", "2026-05-01")

    assert first is not None and first["match_id"] == "m1"
    assert second is not None and second["match_id"] == "m1"


def test_resolve_winner_returns_none_for_no_result_match(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    _insert_cricsheet_match(db, "m1", "2026-05-01", "Alpha", "Beta", None)
    match = db.query_one("SELECT * FROM cricsheet_matches WHERE match_id = 'm1'")

    assert resolve_winner_for_fixture("Alpha", "Beta", match) is None


def test_resolve_winner_maps_aliased_name_back_to_fixture_spelling(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    _insert_cricsheet_match(db, "m1", "2026-05-01", "United States of America", "Hong Kong", "Hong Kong")
    match = db.query_one("SELECT * FROM cricsheet_matches WHERE match_id = 'm1'")

    winner = resolve_winner_for_fixture("USA", "Hong Kong, China", match)

    assert winner == "Hong Kong, China"
