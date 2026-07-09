from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .database import Database, utc_now


MODEL_NAME = "t20_team_elo_v1"


@dataclass(frozen=True)
class EloConfig:
    start_rating: float = 1500.0
    k_factor: float = 24.0
    home_advantage: float = 18.0
    min_matches_for_eval: int = 50


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def log_loss(probability: float, result: float) -> float:
    p = min(0.999, max(0.001, probability))
    return -(result * math.log(p) + (1 - result) * math.log(1 - p))


class EloTrainer:
    def __init__(self, db: Database, config: EloConfig | None = None) -> None:
        self.db = db
        self.config = config or EloConfig()

    def train(self) -> dict[str, Any]:
        self.db.init_schema()
        matches = self.db.query(
            """
            SELECT *
            FROM cricsheet_matches
            WHERE winner IN (team_a, team_b)
            ORDER BY match_date, match_id
            """
        )
        self.db.execute("DELETE FROM team_elo_history")
        ratings: defaultdict[str, float] = defaultdict(lambda: self.config.start_rating)
        history_rows: list[tuple[Any, ...]] = []
        briers: list[float] = []
        losses: list[float] = []
        correct = 0

        for row in matches:
            team_a = row["team_a"]
            team_b = row["team_b"]
            winner = row["winner"]
            result_a = 1.0 if winner == team_a else 0.0

            pre_a = ratings[team_a]
            pre_b = ratings[team_b]
            adjusted_a = pre_a + self._venue_adjustment(row)
            pred_a = expected_score(adjusted_a, pre_b)
            pred_b = 1 - pred_a
            brier = (pred_a - result_a) ** 2
            loss = log_loss(pred_a, result_a)
            is_correct = int((pred_a >= 0.5 and result_a == 1.0) or (pred_a < 0.5 and result_a == 0.0))

            ratings[team_a] = pre_a + self.config.k_factor * (result_a - pred_a)
            ratings[team_b] = pre_b + self.config.k_factor * ((1 - result_a) - pred_b)

            briers.append(brier)
            losses.append(loss)
            correct += is_correct
            history_rows.append(
                (
                    row["match_id"],
                    row["match_date"],
                    row["competition"],
                    team_a,
                    team_b,
                    winner,
                    round(pre_a, 3),
                    round(pre_b, 3),
                    round(pred_a, 5),
                    round(pred_b, 5),
                    result_a,
                    round(ratings[team_a], 3),
                    round(ratings[team_b], 3),
                    round(brier, 6),
                    round(loss, 6),
                    is_correct,
                )
            )

        if history_rows:
            self.db.executemany(
                """
                INSERT INTO team_elo_history(
                    match_id, match_date, competition, team_a, team_b, winner,
                    pre_elo_a, pre_elo_b, pred_a, pred_b, result_a,
                    post_elo_a, post_elo_b, brier, log_loss, correct
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                history_rows,
            )

        summary = {
            "model_name": MODEL_NAME,
            "n_matches": len(history_rows),
            "teams": len(ratings),
            "brier": _mean(briers),
            "log_loss": _mean(losses),
            "accuracy": correct / len(history_rows) if history_rows else 0,
            "top_ratings": _top_ratings(ratings),
            "recent_365": self._window_metrics(365),
            "recent_180": self._window_metrics(180),
            "config": self.config.__dict__,
        }
        self.db.execute(
            """
            INSERT INTO model_runs(model_name, generated_at, n_matches, brier, log_loss, accuracy, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                MODEL_NAME,
                utc_now(),
                summary["n_matches"],
                round(summary["brier"], 6),
                round(summary["log_loss"], 6),
                round(summary["accuracy"], 6),
                json.dumps(summary, sort_keys=True),
            ),
        )
        self.db.log_event("model", "Trained T20 team Elo model.", summary)
        return summary

    def _venue_adjustment(self, row: dict[str, Any]) -> float:
        venue = str(row.get("venue") or "")
        team_a = str(row.get("team_a") or "")
        city = str(row.get("city") or "")
        if team_a and (team_a.lower() in venue.lower() or team_a.lower() in city.lower()):
            return self.config.home_advantage
        return 0.0

    def _window_metrics(self, days: int) -> dict[str, float | int]:
        rows = self.db.query(
            """
            SELECT brier, log_loss, correct
            FROM team_elo_history
            WHERE match_date >= DATE((SELECT MAX(match_date) FROM team_elo_history), ?)
            """,
            (f"-{days} day",),
        )
        if not rows:
            return {"n_matches": 0, "brier": 0, "log_loss": 0, "accuracy": 0}
        return {
            "n_matches": len(rows),
            "brier": _mean([float(r["brier"]) for r in rows]),
            "log_loss": _mean([float(r["log_loss"]) for r in rows]),
            "accuracy": sum(int(r["correct"]) for r in rows) / len(rows),
        }


def current_team_elo_ratings(db: Database) -> dict[str, float]:
    """Each team's rating after its most recent historical match.

    Rows are chronological (match_date, id), so the last write for a team wins.
    Teams absent from Cricsheet history simply have no entry here; callers should
    fall back to EloConfig.start_rating for those.
    """
    rows = db.query(
        """
        SELECT match_date, id, team_a, team_b, post_elo_a, post_elo_b
        FROM team_elo_history
        ORDER BY match_date, id
        """
    )
    ratings: dict[str, float] = {}
    for row in rows:
        ratings[row["team_a"]] = float(row["post_elo_a"])
        ratings[row["team_b"]] = float(row["post_elo_b"])
    return ratings


def latest_elo_report(db: Database) -> dict[str, Any]:
    latest = db.query_one(
        """
        SELECT *
        FROM model_runs
        WHERE model_name = ?
        ORDER BY generated_at DESC, id DESC
        LIMIT 1
        """,
        (MODEL_NAME,),
    )
    if not latest:
        return {}
    payload = json.loads(latest["payload_json"])
    history = db.query(
        """
        SELECT *
        FROM team_elo_history
        ORDER BY match_date DESC, id DESC
        LIMIT 10
        """
    )
    return {"latest_run": dict(latest), "payload": payload, "recent_predictions": history}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _top_ratings(ratings: dict[str, float], limit: int = 12) -> list[dict[str, Any]]:
    ranked = sorted(ratings.items(), key=lambda item: item[1], reverse=True)
    return [{"team": team, "rating": round(rating, 1)} for team, rating in ranked[:limit]]
