from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cricket_edge.cricsheet import ingest_t20_json_zip
from cricket_edge.database import Database
from cricket_edge.data_sources import FreeDataSources
from cricket_edge.elo import EloTrainer, latest_elo_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Week 1: ingest Cricsheet T20 data and train Elo.")
    parser.add_argument("--limit", type=int, default=None, help="Optional number of Cricsheet files to parse.")
    parser.add_argument("--skip-download", action="store_true", help="Use an existing data/raw/cricsheet/t20s_json.zip.")
    args = parser.parse_args()

    db = Database()
    db.init_schema()

    sources = FreeDataSources(db)
    if args.skip_download:
        zip_path = sources.download_cricsheet_t20_json_zip()
    else:
        zip_path = sources.download_cricsheet_t20_json_zip()

    ingest_stats = ingest_t20_json_zip(db, zip_path, limit=args.limit)
    elo_summary = EloTrainer(db).train()
    report = latest_elo_report(db)
    output = {
        "ingest": ingest_stats.__dict__,
        "elo": elo_summary,
        "latest_report_available": bool(report),
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
