from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cricket_edge.database import Database
from cricket_edge.backtesting import run_latest_strategy_backtest
from cricket_edge.market import run_week4_market_build


def main() -> None:
    parser = argparse.ArgumentParser(description="Build odds snapshots, market baselines, and CLV plumbing.")
    parser.add_argument("--csv", type=Path, default=None, help="Optional manual odds CSV to import.")
    args = parser.parse_args()
    db = Database()
    db.init_schema()
    result = run_week4_market_build(db, args.csv)
    result["strategy_backtest"] = run_latest_strategy_backtest(db)
    print(json.dumps(result, indent=2, sort_keys=True, default=float))


if __name__ == "__main__":
    main()
