import json
import zipfile
from pathlib import Path

from cricket_edge.cricsheet import ingest_t20_json_zip
from cricket_edge.database import Database


def _match_payload(winner: str = "Alpha") -> dict:
    return {
        "info": {
            "dates": ["2025-01-01"],
            "teams": ["Alpha", "Beta"],
            "event": {"name": "Tiny T20"},
            "gender": "male",
            "match_type": "T20",
            "venue": "Alpha Ground",
            "city": "Alpha City",
            "toss": {"winner": "Alpha", "decision": "bat"},
            "outcome": {"winner": winner},
        },
        "innings": [
            {
                "team": "Alpha",
                "overs": [
                    {
                        "over": 0,
                        "deliveries": [
                            {"runs": {"total": 1}},
                            {"runs": {"total": 4}},
                        ],
                    }
                ],
            },
            {
                "team": "Beta",
                "overs": [
                    {
                        "over": 0,
                        "deliveries": [
                            {"runs": {"total": 0}, "wickets": [{"kind": "bowled", "player_out": "B One"}]},
                            {"runs": {"total": 2}},
                        ],
                    }
                ],
            },
        ],
    }


def _write_zip(path: Path, count: int) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for idx in range(count):
            archive.writestr(f"{idx + 1}.json", json.dumps(_match_payload()))


def test_ingest_uses_bulk_transaction_instead_of_per_row_execute(tmp_path, monkeypatch) -> None:
    zip_path = tmp_path / "t20s_json.zip"
    _write_zip(zip_path, count=3)
    db = Database(tmp_path / "cricket_edge.sqlite3")
    execute_calls = 0
    original_execute = db.execute

    def counting_execute(*args, **kwargs):
        nonlocal execute_calls
        execute_calls += 1
        return original_execute(*args, **kwargs)

    monkeypatch.setattr(db, "execute", counting_execute)

    stats = ingest_t20_json_zip(db, zip_path)

    assert stats.matches_inserted == 3
    assert stats.innings_inserted == 6
    assert execute_calls <= 1
