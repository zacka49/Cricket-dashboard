from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cricket_edge.advanced_models import model_comparison, train_and_evaluate_models
from cricket_edge.backtesting import latest_backtest_report, run_latest_strategy_backtest
from cricket_edge.config import RAW_DIR
from cricket_edge.cricsheet import ingest_t20_json_zip
from cricket_edge.data_sources import FreeDataSources
from cricket_edge.database import Database, utc_now
from cricket_edge.elo import EloTrainer
from cricket_edge.market import run_week4_market_build
from cricket_edge.readiness import portfolio_readiness_report


DEFAULT_REPORT_DIR = PROJECT_ROOT / "reports"
LOCAL_CRICSHEET_ZIP = RAW_DIR / "cricsheet" / "t20s_json.zip"
COUNT_TABLES = [
    "cricsheet_matches",
    "team_elo_history",
    "model_runs",
    "model_predictions",
    "model_registry",
    "market_baselines",
    "market_odds_snapshots",
    "backtest_runs",
    "paper_bets",
]


def run_evaluation_pipeline(
    db: Database,
    *,
    build_data: bool = False,
    skip_download: bool = False,
    cricsheet_limit: int | None = None,
    train_models: bool = False,
    build_market: bool = False,
    market_csv: Path | None = None,
    run_backtest: bool = False,
) -> dict[str, Any]:
    db.init_schema()
    actions: dict[str, Any] = {}
    if build_data:
        actions["data_build"] = build_training_data(db, skip_download=skip_download, limit=cricsheet_limit)
    if train_models:
        actions["model_training"] = train_models_and_govern(db)
    if build_market:
        actions["market_build"] = run_week4_market_build(db, market_csv)
    report = build_evaluation_report(db, run_backtest=run_backtest)
    report["actions"] = actions
    return report


def build_training_data(db: Database, *, skip_download: bool = False, limit: int | None = None) -> dict[str, Any]:
    zip_path = LOCAL_CRICSHEET_ZIP if skip_download else FreeDataSources(db).download_cricsheet_t20_json_zip()
    if skip_download and not zip_path.exists():
        raise FileNotFoundError(f"Cricsheet archive not found at {zip_path}; run without --skip-download once.")
    ingest_stats = ingest_t20_json_zip(db, zip_path, limit=limit)
    elo_summary = EloTrainer(db).train()
    return {"zip_path": str(zip_path), "ingest": ingest_stats.__dict__, "elo": elo_summary}


def train_models_and_govern(db: Database) -> dict[str, Any]:
    elo_rows = db.query_one("SELECT COUNT(*) AS count FROM team_elo_history")
    if not elo_rows or int(elo_rows["count"] or 0) == 0:
        EloTrainer(db).train()
    return train_and_evaluate_models(db)


def build_evaluation_report(db: Database, run_backtest: bool = False) -> dict[str, Any]:
    db.init_schema()
    backtest_result = run_latest_strategy_backtest(db) if run_backtest else latest_backtest_report(db)
    latest_runs = _latest_model_runs(db)
    return {
        "generated_at": utc_now(),
        "counts": _table_counts(db),
        "active_model": _active_model(db),
        "model_runs": latest_runs,
        "model_comparison": model_comparison(db),
        "latest_backtest": backtest_result,
        "readiness": portfolio_readiness_report(db),
        "warnings": _warnings(latest_runs, backtest_result, db),
    }


def write_report_files(report: dict[str, Any], output_dir: Path = DEFAULT_REPORT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "model_evaluation_latest.json"
    md_path = output_dir / "model_evaluation_latest.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Model Evaluation Report",
        "",
        f"Generated: {report.get('generated_at', '')}",
        "",
        "## Summary",
        "",
    ]
    active = report.get("active_model") or {}
    lines.append(f"- Active model: {active.get('model_name') or 'none'}")
    counts = report.get("counts") or {}
    lines.append(f"- Model runs: {counts.get('model_runs', 0)}")
    lines.append(f"- Historical predictions: {counts.get('model_predictions', 0)}")
    lines.append(f"- Backtest runs: {counts.get('backtest_runs', 0)}")
    actions = report.get("actions") or {}
    if actions:
        lines.append(f"- Pipeline actions: {', '.join(sorted(actions))}")
    lines.append("")

    warnings = report.get("warnings") or []
    lines.append("## Warnings")
    lines.append("")
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Latest Model Runs")
    lines.append("")
    model_runs = report.get("model_runs") or []
    if model_runs:
        lines.append("| Model | Generated | Matches | Brier | Log loss | Accuracy |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for row in model_runs:
            lines.append(
                "| {model_name} | {generated_at} | {n_matches} | {brier:.4f} | {log_loss:.4f} | {accuracy:.2%} |".format(
                    model_name=row.get("model_name", ""),
                    generated_at=row.get("generated_at", ""),
                    n_matches=int(row.get("n_matches", 0) or 0),
                    brier=float(row.get("brier", 0) or 0),
                    log_loss=float(row.get("log_loss", 0) or 0),
                    accuracy=float(row.get("accuracy", 0) or 0),
                )
            )
    else:
        lines.append("No model runs are stored in the database.")
    lines.append("")

    lines.append("## Backtest")
    lines.append("")
    payload = ((report.get("latest_backtest") or {}).get("payload") or {})
    lines.append(f"- Candidates: {payload.get('n_candidates', 0)}")
    lines.append(f"- Bets: {payload.get('bets', 0)}")
    lines.append(f"- ROI: {float(payload.get('roi', 0) or 0):.2%}")
    lines.append(f"- Max drawdown: {float(payload.get('max_drawdown', 0) or 0):.2f}")
    if payload.get("avg_clv") is not None:
        lines.append(f"- Average CLV: {float(payload.get('avg_clv')):.2%}")
    if payload.get("sample_warning"):
        lines.append(f"- Sample warning: {payload.get('sample_warning')}")
    lines.append("")

    lines.append("## Readiness")
    lines.append("")
    for item in (report.get("readiness") or {}).get("items", []):
        lines.append(f"- {item['status']}: {item['label']} - {item['detail']}")
    lines.append("")
    return "\n".join(lines)


def _latest_model_runs(db: Database) -> list[dict[str, Any]]:
    rows = db.query(
        """
        SELECT *
        FROM model_runs
        ORDER BY generated_at DESC, id DESC
        """
    )
    latest_by_model: dict[str, dict[str, Any]] = {}
    for row in rows:
        latest_by_model.setdefault(str(row["model_name"]), row)
    return list(latest_by_model.values())


def _active_model(db: Database) -> dict[str, Any]:
    return db.query_one("SELECT * FROM model_registry WHERE active = 1 LIMIT 1") or {}


def _table_counts(db: Database) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in COUNT_TABLES:
        row = db.query_one(f"SELECT COUNT(*) AS count FROM {table}")
        counts[table] = int(row["count"] or 0) if row else 0
    return counts


def _warnings(model_runs: list[dict[str, Any]], backtest: dict[str, Any], db: Database) -> list[str]:
    warnings: list[str] = []
    counts = _table_counts(db)
    if counts.get("cricsheet_matches", 0) == 0 or counts.get("team_elo_history", 0) == 0:
        warnings.append("Training data is missing or incomplete; run the Cricsheet/Elo build before trusting model evaluation.")
    if not model_runs:
        warnings.append("No model_runs are stored; train/govern models before comparing candidates.")
    if counts.get("model_predictions", 0) == 0:
        warnings.append("No historical model_predictions are stored; calibration and backtesting cannot be reproduced.")
    payload = (backtest.get("payload") if isinstance(backtest, dict) else {}) or {}
    if payload.get("sample_warning"):
        warnings.append(str(payload["sample_warning"]))
    return warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Cricket Edge model evaluation and backtest readiness reports.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR, help="Directory for JSON and Markdown report files.")
    parser.add_argument("--build-data", action="store_true", help="Ingest Cricsheet T20 data and rebuild Elo before reporting.")
    parser.add_argument("--skip-download", action="store_true", help="Use the local Cricsheet zip and fail if it is missing.")
    parser.add_argument("--cricsheet-limit", type=int, default=None, help="Optional number of Cricsheet JSON files to ingest.")
    parser.add_argument("--train-models", action="store_true", help="Train/govern Elo, logistic, and boosted candidate models before reporting.")
    parser.add_argument("--build-market", action="store_true", help="Rebuild market baselines and CLV plumbing before reporting.")
    parser.add_argument("--market-csv", type=Path, default=None, help="Optional manual odds CSV for market build.")
    parser.add_argument("--run-backtest", action="store_true", help="Run the latest available strategy backtest before exporting.")
    args = parser.parse_args()

    report = run_evaluation_pipeline(
        Database(),
        build_data=args.build_data,
        skip_download=args.skip_download,
        cricsheet_limit=args.cricsheet_limit,
        train_models=args.train_models,
        build_market=args.build_market,
        market_csv=args.market_csv,
        run_backtest=args.run_backtest,
    )
    written = write_report_files(report, args.output_dir)
    print(json.dumps({"written": written, "warnings": report["warnings"], "actions": report.get("actions", {})}, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
