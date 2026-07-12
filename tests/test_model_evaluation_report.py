import json
from pathlib import Path

from cricket_edge.database import Database, utc_now
from scripts.evaluate_models import build_evaluation_report, render_markdown_report, write_report_files


def test_evaluation_report_surfaces_empty_model_state(tmp_path: Path) -> None:
    db = Database(tmp_path / "empty.sqlite3")
    db.init_schema()

    report = build_evaluation_report(db)

    assert report["counts"]["model_runs"] == 0
    assert report["counts"]["model_predictions"] == 0
    assert report["active_model"] == {}
    assert any("No model_runs" in warning for warning in report["warnings"])
    assert any(item["key"] == "model_runs" and item["status"] == "gap" for item in report["readiness"]["items"])


def test_evaluation_report_writes_json_and_markdown(tmp_path: Path) -> None:
    db = Database(tmp_path / "report.sqlite3")
    db.init_schema()
    db.execute(
        """
        INSERT INTO model_runs(model_name, generated_at, n_matches, brier, log_loss, accuracy, payload_json)
        VALUES ('candidate_v1', ?, 12, 0.21, 0.61, 0.67, ?)
        """,
        (utc_now(), json.dumps({"splits": {"test": {"brier": 0.21}}})),
    )
    report = build_evaluation_report(db)

    written = write_report_files(report, tmp_path / "reports")

    json_path = Path(written["json"])
    markdown_path = Path(written["markdown"])
    assert json_path.exists()
    assert markdown_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["counts"]["model_runs"] == 1
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Model Evaluation Report" in markdown
    assert "candidate_v1" in markdown


def test_render_markdown_report_includes_backtest_warning(tmp_path: Path) -> None:
    db = Database(tmp_path / "warning.sqlite3")
    db.init_schema()

    report = build_evaluation_report(db)
    markdown = render_markdown_report(report)

    assert "## Backtest" in markdown
    assert "No strategy backtest has been run yet" in markdown
