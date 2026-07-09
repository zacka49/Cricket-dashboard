from pathlib import Path

from cricket_edge.database import Database, utc_now
from cricket_edge.paper_broker import PaperBroker


def _insert_fixture(db: Database, team_a: str, team_b: str, match_date: str, source: str = "bet365") -> int:
    return db.execute(
        """
        INSERT INTO fixtures(
            match_date, start_time, competition, format, team_a, team_b, venue,
            status, source, created_at
        )
        VALUES (?, '09:00', 'Test League', 'T20', ?, ?, 'Test Ground', 'scheduled', ?, ?)
        """,
        (match_date, team_a, team_b, source, utc_now()),
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


def _place_open_bet(db: Database, fixture_id: int, selection: str, odds: float, stake: float = 10.0) -> int:
    return db.execute(
        """
        INSERT INTO paper_bets(
            fixture_id, decision_id, market, selection, stake, odds, status, placed_at, notes
        )
        VALUES (?, NULL, 'match_winner', ?, ?, ?, 'open', ?, '')
        """,
        (fixture_id, selection, stake, odds, utc_now()),
    )


def test_bet_stays_open_when_no_cricsheet_match_is_linkable(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta", "2026-01-01")
    bet_id = _place_open_bet(db, fixture_id, "Alpha", 2.0)

    result = PaperBroker(db).settle_due_bets()

    bet = db.query_one("SELECT * FROM paper_bets WHERE id = ?", (bet_id,))
    assert bet["status"] == "open"
    assert result["still_open_awaiting_result"] == 1
    assert result["settled"] == 0


def test_bet_settles_win_from_real_linked_winner(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta", "2026-01-01")
    _insert_cricsheet_match(db, "m1", "2026-01-01", "Alpha", "Beta", "Alpha")
    bet_id = _place_open_bet(db, fixture_id, "Alpha", 2.0, stake=10.0)

    result = PaperBroker(db).settle_due_bets()

    bet = db.query_one("SELECT * FROM paper_bets WHERE id = ?", (bet_id,))
    assert bet["status"] == "settled"
    assert bet["pnl"] == 10.0
    fixture = db.query_one("SELECT * FROM fixtures WHERE id = ?", (fixture_id,))
    assert fixture["result_winner"] == "Alpha"
    assert result["settled"] == 1


def test_bet_settles_loss_from_real_linked_winner(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta", "2026-01-01")
    _insert_cricsheet_match(db, "m1", "2026-01-01", "Alpha", "Beta", "Beta")
    bet_id = _place_open_bet(db, fixture_id, "Alpha", 2.0, stake=10.0)

    PaperBroker(db).settle_due_bets()

    bet = db.query_one("SELECT * FROM paper_bets WHERE id = ?", (bet_id,))
    assert bet["status"] == "settled"
    assert bet["pnl"] == -10.0


def test_bet_voids_at_zero_pnl_when_linked_match_has_no_result(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta", "2026-01-01")
    _insert_cricsheet_match(db, "m1", "2026-01-01", "Alpha", "Beta", None)
    bet_id = _place_open_bet(db, fixture_id, "Alpha", 2.0, stake=10.0)

    result = PaperBroker(db).settle_due_bets()

    bet = db.query_one("SELECT * FROM paper_bets WHERE id = ?", (bet_id,))
    assert bet["status"] == "settled"
    assert bet["pnl"] == 0.0
    assert result["voided"] == 1


def test_settle_does_not_crash_on_a_bet_with_no_real_odds_source(tmp_path: Path) -> None:
    # Defensive case: risk.py's real-odds-source gate should prevent this in the
    # normal pipeline, but settle_due_bets must not assume that invariant forever.
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fixture_id = _insert_fixture(db, "Alpha", "Beta", "2026-01-01", source="demo-market")
    _place_open_bet(db, fixture_id, "Alpha", 2.0)

    result = PaperBroker(db).settle_due_bets()

    assert result["still_open_awaiting_result"] == 1
