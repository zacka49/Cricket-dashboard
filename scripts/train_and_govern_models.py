from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cricket_edge.advanced_models import train_and_evaluate_models
from cricket_edge.database import Database
from cricket_edge.elo import EloTrainer


def main() -> None:
    db = Database()
    db.init_schema()
    elo_rows = db.query_one("SELECT COUNT(*) AS count FROM team_elo_history")
    if not elo_rows or int(elo_rows["count"]) == 0:
        EloTrainer(db).train()
    result = train_and_evaluate_models(db)
    print(json.dumps(result, indent=2, sort_keys=True, default=float))


if __name__ == "__main__":
    main()
