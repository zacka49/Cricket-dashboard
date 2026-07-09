from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cricket_edge.scheduler import PaperSchedulerConfig, run_paper_scheduler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Cricket Edge morning and monitor cycles in paper mode.")
    parser.add_argument("--monitor-cycles", type=int, default=6)
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--settle-after", action="store_true")
    args = parser.parse_args()
    result = run_paper_scheduler(
        PaperSchedulerConfig(
            monitor_cycles=args.monitor_cycles,
            interval_seconds=args.interval_seconds,
            settle_after=args.settle_after,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
