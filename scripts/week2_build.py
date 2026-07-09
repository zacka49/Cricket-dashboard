from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cricket_edge.database import Database
from cricket_edge.elo import EloTrainer
from cricket_edge.logistic_model import LogisticRegressionTrainer, latest_week2_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Week 2: train logistic regression and compare against Elo.")
    parser.add_argument("--retrain-elo", action="store_true", help="Retrain the Elo baseline before logistic regression.")
    args = parser.parse_args()

    db = Database()
    db.init_schema()
    elo_rows = db.query_one("SELECT COUNT(*) AS count FROM team_elo_history")
    if args.retrain_elo or not elo_rows or int(elo_rows["count"]) == 0:
        EloTrainer(db).train()

    summary = LogisticRegressionTrainer(db).train()
    report = latest_week2_report(db)
    output = {
        "summary": summary,
        "latest_report_available": bool(report),
    }
    print(json.dumps(output, indent=2, sort_keys=True, default=float))


if __name__ == "__main__":
    main()
