import json
from pathlib import Path

from cricket_edge.advanced_models import MODEL_GOVERNANCE_AGENT_NAME, _evaluate_promotion, _read_incumbent
from cricket_edge.database import Database, utc_now


def _insert_registry(db: Database, model_name: str, active: int) -> None:
    db.execute(
        """
        INSERT INTO model_registry(
            model_name, model_family, timing, status, generated_at, active, calibrated,
            feature_names_json, metrics_json, notes
        )
        VALUES (?, 'logistic', 'pre_toss', ?, ?, ?, 1, '[]', '{}', '')
        """,
        (model_name, "active" if active else "candidate", utc_now(), active),
    )


def _insert_run(db: Database, model_name: str, test_brier: float) -> None:
    payload = {"splits": {"test": {"brier": test_brier}}}
    db.execute(
        """
        INSERT INTO model_runs(model_name, generated_at, n_matches, brier, log_loss, accuracy, payload_json)
        VALUES (?, ?, 100, ?, 0.5, 0.6, ?)
        """,
        (model_name, utc_now(), test_brier, json.dumps(payload)),
    )


def test_read_incumbent_returns_none_when_no_active_model(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()

    assert _read_incumbent(db) is None


def test_read_incumbent_returns_latest_test_brier_for_active_model(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    _insert_registry(db, "old_model", active=1)
    _insert_run(db, "old_model", test_brier=0.230)

    incumbent = _read_incumbent(db)

    assert incumbent == {"model_name": "old_model", "test_brier": 0.230}


def test_promotes_candidate_with_lower_brier(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    _insert_registry(db, "old_model", active=1)
    _insert_run(db, "old_model", test_brier=0.230)

    result = _evaluate_promotion(db, {"model_name": "old_model", "test_brier": 0.230}, "new_model", 0.200)

    assert result["promoted"] is True
    assert result["active_model"] == "new_model"
    row = db.query_one("SELECT * FROM agent_decisions WHERE agent_name = ?", (MODEL_GOVERNANCE_AGENT_NAME,))
    assert row["decision"] == "promoted"


def test_retains_incumbent_when_candidate_does_not_beat_it(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    _insert_registry(db, "old_model", active=1)
    _insert_run(db, "old_model", test_brier=0.200)

    result = _evaluate_promotion(db, {"model_name": "old_model", "test_brier": 0.200}, "new_model", 0.230)

    assert result["promoted"] is False
    assert result["active_model"] == "old_model"
    registry = db.query_one("SELECT * FROM model_registry WHERE model_name = 'old_model'")
    assert registry["active"] == 1
    row = db.query_one("SELECT * FROM agent_decisions WHERE agent_name = ?", (MODEL_GOVERNANCE_AGENT_NAME,))
    assert row["decision"] == "retained_incumbent"


def test_retains_incumbent_re_asserts_active_flag_after_a_same_name_retrain(tmp_path: Path) -> None:
    # Simulates the real scenario: retraining a model that IS the incumbent resets
    # its own active flag to 0 as a side effect of upsert_model_registry -- the
    # gate must restore it rather than leaving the registry with no active model.
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    _insert_registry(db, "pretoss_v1", active=0)  # simulates the post-retrain reset
    _insert_run(db, "pretoss_v1", test_brier=0.230)

    result = _evaluate_promotion(db, {"model_name": "pretoss_v1", "test_brier": 0.230}, "pretoss_v1", 0.240)

    assert result["promoted"] is False
    assert result["active_model"] == "pretoss_v1"
    registry = db.query_one("SELECT * FROM model_registry WHERE model_name = 'pretoss_v1'")
    assert registry["active"] == 1


def test_bootstrap_case_always_promotes_when_no_incumbent(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.sqlite3")
    db.init_schema()
    _insert_registry(db, "first_model", active=0)

    result = _evaluate_promotion(db, None, "first_model", 0.300)

    assert result["promoted"] is True
    assert result["active_model"] == "first_model"
    registry = db.query_one("SELECT * FROM model_registry WHERE model_name = 'first_model'")
    assert registry["active"] == 1
