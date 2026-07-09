from __future__ import annotations

import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cricket_edge.database import Database
from cricket_edge.live_data import pull_all_live_data


def main() -> None:
    db = Database()
    result = pull_all_live_data(db)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
