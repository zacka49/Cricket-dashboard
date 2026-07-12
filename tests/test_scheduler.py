from pathlib import Path
from typing import Any
from unittest.mock import patch

from cricket_edge.scheduler import BackgroundScheduler
from cricket_edge.database import Database, utc_now


class _FakeOrchestrator:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.calls: list[str] = []

    def morning_run(self) -> dict[str, Any]:
        self.calls.append("morning_run")
        return {}

    def monitor_tick(self) -> dict[str, Any]:
        self.calls.append("monitor_tick")
        return {}

    def settle(self) -> dict[str, Any]:
        self.calls.append("settle")
        return {}

    def train_week3_models(self) -> dict[str, Any]:
        self.calls.append("train_week3_models")
        return {}


def _insert_cricsheet_match(db: Database, match_id: str) -> None:
    db.execute(
        """
        INSERT INTO cricsheet_matches(
            match_id, source_file, match_date, competition, gender, match_type,
            team_a, team_b, venue, city, winner, outcome,
            team_a_runs, team_a_wickets, team_a_balls,
            team_b_runs, team_b_wickets, team_b_balls, inserted_at
        )
        VALUES (?, 'test.json', '2026-01-01', 'Test League', 'male', 'T20', 'Alpha', 'Beta', 'Test Ground', 'Test City',
                'Alpha', 'normal', 160, 6, 120, 150, 7, 120, ?)
        """,
        (match_id, utc_now()),
    )


def _make_scheduler(tmp_path: Path) -> tuple[BackgroundScheduler, _FakeOrchestrator]:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    fake = _FakeOrchestrator(db)
    scheduler = BackgroundScheduler(fake)
    return scheduler, fake


def test_tick_always_runs_monitor_and_settle(tmp_path: Path) -> None:
    scheduler, fake = _make_scheduler(tmp_path)

    scheduler.tick()

    assert "monitor_tick" in fake.calls
    assert "settle" in fake.calls


def test_tick_runs_morning_run_only_once_per_calendar_day(tmp_path: Path) -> None:
    scheduler, fake = _make_scheduler(tmp_path)

    scheduler.tick()
    scheduler.tick()

    assert fake.calls.count("morning_run") == 1


def test_tick_retrains_on_first_ever_tick(tmp_path: Path) -> None:
    scheduler, fake = _make_scheduler(tmp_path)

    scheduler.tick()

    assert "train_week3_models" in fake.calls
    row = scheduler.db.query_one("SELECT * FROM scheduler_state WHERE id = 1")
    assert row["last_retrain_at"] is not None


def test_tick_updates_heartbeat_even_when_retrain_fails(tmp_path: Path) -> None:
    # Real-world case: a fresh system has no training data yet, so the first
    # retrain attempt raises. The scheduler must still report itself alive --
    # last_tick_at must not depend on the retrain step succeeding.
    scheduler, fake = _make_scheduler(tmp_path)

    def _failing_train() -> dict[str, Any]:
        raise RuntimeError("not enough rows to train")

    fake.train_week3_models = _failing_train  # type: ignore[method-assign]

    scheduler.tick()

    row = scheduler.db.query_one("SELECT * FROM scheduler_state WHERE id = 1")
    assert row["last_tick_at"] is not None
    assert row["last_retrain_at"] is None
    events = scheduler.db.query("SELECT * FROM events WHERE type = 'scheduler'")
    assert any("Retrain failed" in row["message"] for row in events)


def test_tick_does_not_retrain_again_immediately(tmp_path: Path) -> None:
    scheduler, fake = _make_scheduler(tmp_path)
    scheduler.tick()
    fake.calls.clear()

    scheduler.tick()

    assert "train_week3_models" not in fake.calls


def test_tick_retrains_when_new_match_threshold_crossed(tmp_path: Path) -> None:
    scheduler, fake = _make_scheduler(tmp_path)
    scheduler.tick()  # first tick always retrains, establishes a baseline count of 0
    fake.calls.clear()

    for i in range(20):
        _insert_cricsheet_match(scheduler.db, f"m{i}")

    scheduler.tick()

    assert "train_week3_models" in fake.calls


def test_tick_does_not_retrain_below_new_match_threshold(tmp_path: Path) -> None:
    scheduler, fake = _make_scheduler(tmp_path)
    scheduler.tick()
    fake.calls.clear()

    for i in range(5):
        _insert_cricsheet_match(scheduler.db, f"m{i}")

    scheduler.tick()

    assert "train_week3_models" not in fake.calls


def test_run_forever_survives_a_failing_tick(tmp_path: Path) -> None:
    scheduler, fake = _make_scheduler(tmp_path)
    call_count = {"n": 0}

    def _sleep_then_stop(_seconds: float) -> None:
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise StopIteration

    original_tick = scheduler.tick

    def _failing_then_ok_tick() -> dict:
        if call_count["n"] == 0:
            raise RuntimeError("simulated transient failure")
        return original_tick()

    scheduler.tick = _failing_then_ok_tick  # type: ignore[method-assign]

    with patch("cricket_edge.scheduler.time.sleep", side_effect=_sleep_then_stop):
        try:
            scheduler.run_forever()
        except StopIteration:
            pass

    events = scheduler.db.query("SELECT * FROM events WHERE type = 'scheduler'")
    assert any("Tick failed" in row["message"] for row in events)
