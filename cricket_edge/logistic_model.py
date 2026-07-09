from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

from .database import Database, utc_now
from .elo import MODEL_NAME as ELO_MODEL_NAME


MODEL_NAME = "t20_logistic_regression_v1"
PRETOSS_MODEL_NAME = "t20_logistic_pretoss_calibrated_v1"
POSTTOSS_MODEL_NAME = "t20_logistic_posttoss_calibrated_v1"


@dataclass(frozen=True)
class LogisticConfig:
    train_fraction: float = 0.70
    validation_fraction: float = 0.15
    epochs: int = 2500
    learning_rate: float = 0.055
    l2: float = 0.015


BASE_FEATURE_NAMES = [
    "elo_diff",
    "experience_diff",
    "win_rate_diff",
    "avg_runs_for_diff",
    "avg_runs_against_diff",
    "avg_wickets_taken_diff",
    "venue_experience_diff",
    "rest_days_diff",
    "female_match",
    "world_cup_match",
]

TOSS_FEATURE_NAMES = [
    "toss_team_a",
    "toss_bat_team_a",
]

FEATURE_NAMES = [
    "elo_diff",
    "experience_diff",
    "win_rate_diff",
    "avg_runs_for_diff",
    "avg_runs_against_diff",
    "avg_wickets_taken_diff",
    "venue_experience_diff",
    "toss_team_a",
    "toss_bat_team_a",
    "female_match",
    "world_cup_match",
]


class LogisticRegressionTrainer:
    def __init__(
        self,
        db: Database,
        config: LogisticConfig | None = None,
        model_name: str = MODEL_NAME,
        feature_names: list[str] | None = None,
        timing: str = "post_toss",
        calibrated: bool = False,
        notes: str = "",
    ) -> None:
        self.db = db
        self.config = config or LogisticConfig()
        self.model_name = model_name
        self.feature_names = feature_names or FEATURE_NAMES
        self.timing = timing
        self.calibrated = calibrated
        self.notes = notes

    def train(self) -> dict[str, Any]:
        self.db.init_schema()
        rows = build_feature_rows(self.db)
        if len(rows) < 200:
            raise RuntimeError("Not enough Cricsheet/Elo rows to train logistic regression. Run Week 1 first.")

        n = len(rows)
        train_end = max(1, int(n * self.config.train_fraction))
        val_end = max(train_end + 1, int(n * (self.config.train_fraction + self.config.validation_fraction)))
        val_end = min(val_end, n - 1)
        for idx, row in enumerate(rows):
            row["split"] = "train" if idx < train_end else "validation" if idx < val_end else "test"

        x = np.array([[float(row["features"][name]) for name in self.feature_names] for row in rows], dtype=float)
        y = np.array([float(row["result_a"]) for row in rows], dtype=float)
        x_train = x[:train_end]
        y_train = y[:train_end]
        means = x_train.mean(axis=0)
        stds = x_train.std(axis=0)
        stds = np.where(stds < 1e-9, 1.0, stds)
        x_scaled = (x - means) / stds
        x_design = np.column_stack([np.ones(n), x_scaled])

        weights = np.zeros(x_design.shape[1], dtype=float)
        for _ in range(self.config.epochs):
            logits = np.clip(x_design[:train_end] @ weights, -35, 35)
            probs = 1.0 / (1.0 + np.exp(-logits))
            gradient = (x_design[:train_end].T @ (probs - y_train)) / train_end
            regularizer = self.config.l2 * weights
            regularizer[0] = 0.0
            weights -= self.config.learning_rate * (gradient + regularizer)

        logits_all = np.clip(x_design @ weights, -35, 35)
        raw_probs_all = 1.0 / (1.0 + np.exp(-logits_all))
        calibrator = {"a": 1.0, "b": 0.0}
        probs_all = raw_probs_all
        if self.calibrated:
            calibrator = fit_platt_calibrator(logits_all[train_end:val_end], y[train_end:val_end])
            probs_all = apply_platt_calibrator(logits_all, calibrator)

        self.db.execute("DELETE FROM model_predictions WHERE model_name = ?", (self.model_name,))
        prediction_rows = []
        for row, pred in zip(rows, probs_all):
            brier = (float(pred) - float(row["result_a"])) ** 2
            loss = binary_log_loss(float(pred), float(row["result_a"]))
            prediction_rows.append(
                (
                    self.model_name,
                    row["match_id"],
                    row["split"],
                    row["match_date"],
                    row["competition"],
                    row["team_a"],
                    row["team_b"],
                    row["winner"],
                    round(float(pred), 6),
                    float(row["result_a"]),
                    round(brier, 6),
                    round(loss, 6),
                    int((pred >= 0.5 and row["result_a"] == 1.0) or (pred < 0.5 and row["result_a"] == 0.0)),
                    json.dumps(row["features"], sort_keys=True),
                )
            )
        self.db.executemany(
            """
            INSERT INTO model_predictions(
                model_name, match_id, split, match_date, competition, team_a, team_b, winner,
                pred_a, result_a, brier, log_loss, correct, features_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            prediction_rows,
        )

        metrics = {
            "model_name": self.model_name,
            "n_matches": n,
            "feature_names": self.feature_names,
            "timing": self.timing,
            "calibrated": self.calibrated,
            "splits": {
                "train": split_metrics(rows, probs_all, "train"),
                "validation": split_metrics(rows, probs_all, "validation"),
                "test": split_metrics(rows, probs_all, "test"),
                "recent_365": recent_metrics(rows, probs_all, 365),
            },
            "elo_comparison": {
                "train": elo_split_metrics(rows, "train"),
                "validation": elo_split_metrics(rows, "validation"),
                "test": elo_split_metrics(rows, "test"),
                "recent_365": elo_recent_metrics(rows, 365),
            },
            "calibration": {
                "logistic_test": calibration_bins(rows, probs_all, "test"),
                "logistic_validation": calibration_bins(rows, probs_all, "validation"),
                "elo_test": calibration_bins(rows, np.array([row["elo_pred_a"] for row in rows], dtype=float), "test"),
                "ece_test": expected_calibration_error(rows, probs_all, "test"),
            },
            "coefficients": coefficients(weights, means, stds, self.feature_names),
            "calibrator": calibrator,
            "config": self.config.__dict__,
        }
        test = metrics["splits"]["test"]
        self.db.execute(
            """
            INSERT INTO model_runs(model_name, generated_at, n_matches, brier, log_loss, accuracy, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.model_name,
                utc_now(),
                n,
                round(float(test["brier"]), 6),
                round(float(test["log_loss"]), 6),
                round(float(test["accuracy"]), 6),
                json.dumps(metrics, sort_keys=True, default=float),
            ),
        )
        upsert_model_registry(
            self.db,
            model_name=self.model_name,
            model_family="logistic_regression",
            timing=self.timing,
            status="candidate",
            active=0,
            calibrated=int(self.calibrated),
            feature_names=self.feature_names,
            metrics=metrics,
            notes=self.notes,
        )
        self.db.log_event("model", f"Trained logistic regression model {self.model_name}.", metrics)
        return metrics


def build_feature_rows(db: Database) -> list[dict[str, Any]]:
    matches = db.query(
        """
        SELECT
            h.match_id, h.match_date, h.competition, h.team_a, h.team_b, h.winner,
            h.pre_elo_a, h.pre_elo_b, h.pred_a AS elo_pred_a, h.result_a,
            m.gender, m.venue, m.city, m.toss_winner, m.toss_decision,
            m.team_a_runs, m.team_a_wickets, m.team_a_balls,
            m.team_b_runs, m.team_b_wickets, m.team_b_balls
        FROM team_elo_history h
        JOIN cricsheet_matches m ON m.match_id = h.match_id
        ORDER BY h.match_date, h.match_id
        """
    )
    team_stats: defaultdict[str, dict[str, Any]] = defaultdict(_empty_team_stats)
    rows: list[dict[str, Any]] = []
    for row in matches:
        team_a = row["team_a"]
        team_b = row["team_b"]
        stats_a = team_stats[team_a]
        stats_b = team_stats[team_b]
        features = {
            "elo_diff": (float(row["pre_elo_a"]) - float(row["pre_elo_b"])) / 400.0,
            "experience_diff": (math.log1p(stats_a["matches"]) - math.log1p(stats_b["matches"])) / 5.0,
            "win_rate_diff": _win_rate(stats_a) - _win_rate(stats_b),
            "avg_runs_for_diff": (_avg(stats_a, "runs_for", "matches", 155.0) - _avg(stats_b, "runs_for", "matches", 155.0)) / 55.0,
            "avg_runs_against_diff": (_avg(stats_a, "runs_against", "matches", 155.0) - _avg(stats_b, "runs_against", "matches", 155.0)) / 55.0,
            "avg_wickets_taken_diff": (_avg(stats_a, "wickets_for", "matches", 6.0) - _avg(stats_b, "wickets_for", "matches", 6.0)) / 4.0,
            "venue_experience_diff": (math.log1p(stats_a["venues"][row["venue"]]) - math.log1p(stats_b["venues"][row["venue"]])) / 3.0,
            "rest_days_diff": (_rest_days(stats_a, row["match_date"]) - _rest_days(stats_b, row["match_date"])) / 60.0,
            "toss_team_a": _toss_team_a(row),
            "toss_bat_team_a": _toss_bat_team_a(row),
            "female_match": 1.0 if row["gender"] == "female" else 0.0,
            "world_cup_match": 1.0 if "world" in str(row["competition"]).lower() else 0.0,
        }
        rows.append(
            {
                "match_id": row["match_id"],
                "match_date": row["match_date"],
                "competition": row["competition"],
                "team_a": team_a,
                "team_b": team_b,
                "winner": row["winner"],
                "result_a": float(row["result_a"]),
                "elo_pred_a": float(row["elo_pred_a"]),
                "features": features,
            }
        )
        _update_team_stats(team_stats, row)
    return rows


def current_team_stats(db: Database) -> dict[str, dict[str, Any]]:
    """Each team's cumulative stats after its most recent historical match.

    Reuses the exact accumulation the leakage-safe training features are built from,
    so a live prediction's inputs are computed the same way the model was trained on.
    """
    matches = db.query(
        """
        SELECT h.match_id, h.match_date, h.team_a, h.team_b, h.winner,
               m.team_a_runs, m.team_a_wickets, m.team_b_runs, m.team_b_wickets, m.venue
        FROM team_elo_history h
        JOIN cricsheet_matches m ON m.match_id = h.match_id
        ORDER BY h.match_date, h.match_id
        """
    )
    team_stats: defaultdict[str, dict[str, Any]] = defaultdict(_empty_team_stats)
    for row in matches:
        _update_team_stats(team_stats, row)
    return team_stats


def latest_week2_report(db: Database) -> dict[str, Any]:
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
    recent_predictions = db.query(
        """
        SELECT *
        FROM model_predictions
        WHERE model_name = ?
        ORDER BY match_date DESC, id DESC
        LIMIT 10
        """,
        (MODEL_NAME,),
    )
    return {"latest_run": dict(latest), "payload": payload, "recent_predictions": recent_predictions}


def split_metrics(rows: list[dict[str, Any]], probs: np.ndarray, split: str) -> dict[str, float | int]:
    idx = [i for i, row in enumerate(rows) if row["split"] == split]
    return _metrics_for_indices(rows, probs, idx)


def recent_metrics(rows: list[dict[str, Any]], probs: np.ndarray, days: int) -> dict[str, float | int]:
    latest = max(date.fromisoformat(row["match_date"]) for row in rows)
    idx = [i for i, row in enumerate(rows) if (latest - date.fromisoformat(row["match_date"])).days <= days]
    return _metrics_for_indices(rows, probs, idx)


def elo_split_metrics(rows: list[dict[str, Any]], split: str) -> dict[str, float | int]:
    idx = [i for i, row in enumerate(rows) if row["split"] == split]
    probs = np.array([row["elo_pred_a"] for row in rows], dtype=float)
    return _metrics_for_indices(rows, probs, idx)


def elo_recent_metrics(rows: list[dict[str, Any]], days: int) -> dict[str, float | int]:
    latest = max(date.fromisoformat(row["match_date"]) for row in rows)
    idx = [i for i, row in enumerate(rows) if (latest - date.fromisoformat(row["match_date"])).days <= days]
    probs = np.array([row["elo_pred_a"] for row in rows], dtype=float)
    return _metrics_for_indices(rows, probs, idx)


def calibration_bins(rows: list[dict[str, Any]], probs: np.ndarray, split: str, bins: int = 10) -> list[dict[str, Any]]:
    selected = [(float(probs[i]), float(row["result_a"])) for i, row in enumerate(rows) if row["split"] == split]
    output = []
    for bucket in range(bins):
        low = bucket / bins
        high = (bucket + 1) / bins
        items = [(p, y) for p, y in selected if low <= p < high or (bucket == bins - 1 and p == 1.0)]
        if not items:
            continue
        output.append(
            {
                "bucket": f"{low:.1f}-{high:.1f}",
                "n": len(items),
                "avg_prediction": round(sum(p for p, _ in items) / len(items), 4),
                "actual_rate": round(sum(y for _, y in items) / len(items), 4),
            }
        )
    return output


def coefficients(
    weights: np.ndarray,
    means: np.ndarray,
    stds: np.ndarray,
    feature_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    feature_names = feature_names or FEATURE_NAMES
    rows = [{"feature": "intercept", "weight": round(float(weights[0]), 5)}]
    for name, weight, mean, std in zip(feature_names, weights[1:], means, stds):
        rows.append(
            {
                "feature": name,
                "weight": round(float(weight), 5),
                "train_mean": round(float(mean), 5),
                "train_std": round(float(std), 5),
            }
        )
    return sorted(rows, key=lambda item: abs(float(item["weight"])), reverse=True)


def _metrics_for_indices(rows: list[dict[str, Any]], probs: np.ndarray, idx: list[int]) -> dict[str, float | int]:
    if not idx:
        return {"n_matches": 0, "brier": 0, "log_loss": 0, "accuracy": 0}
    brier = 0.0
    loss = 0.0
    correct = 0
    for i in idx:
        p = float(probs[i])
        y = float(rows[i]["result_a"])
        brier += (p - y) ** 2
        loss += binary_log_loss(p, y)
        correct += int((p >= 0.5 and y == 1.0) or (p < 0.5 and y == 0.0))
    return {
        "n_matches": len(idx),
        "brier": brier / len(idx),
        "log_loss": loss / len(idx),
        "accuracy": correct / len(idx),
    }


def binary_log_loss(probability: float, result: float) -> float:
    p = min(0.999, max(0.001, probability))
    return -(result * math.log(p) + (1 - result) * math.log(1 - p))


def fit_platt_calibrator(logits: np.ndarray, y: np.ndarray, epochs: int = 1200, learning_rate: float = 0.04) -> dict[str, float]:
    if len(logits) == 0:
        return {"a": 1.0, "b": 0.0}
    a = 1.0
    b = 0.0
    for _ in range(epochs):
        z = np.clip(a * logits + b, -35, 35)
        p = 1.0 / (1.0 + np.exp(-z))
        error = p - y
        grad_a = float(np.mean(error * logits))
        grad_b = float(np.mean(error))
        a -= learning_rate * grad_a
        b -= learning_rate * grad_b
    return {"a": round(float(a), 6), "b": round(float(b), 6)}


def apply_platt_calibrator(logits: np.ndarray, calibrator: dict[str, float]) -> np.ndarray:
    z = np.clip(float(calibrator["a"]) * logits + float(calibrator["b"]), -35, 35)
    return 1.0 / (1.0 + np.exp(-z))


def expected_calibration_error(rows: list[dict[str, Any]], probs: np.ndarray, split: str, bins: int = 10) -> float:
    selected = [(float(probs[i]), float(row["result_a"])) for i, row in enumerate(rows) if row["split"] == split]
    if not selected:
        return 0.0
    ece = 0.0
    total = len(selected)
    for bucket in range(bins):
        low = bucket / bins
        high = (bucket + 1) / bins
        items = [(p, y) for p, y in selected if low <= p < high or (bucket == bins - 1 and p == 1.0)]
        if not items:
            continue
        avg_prediction = sum(p for p, _ in items) / len(items)
        actual_rate = sum(y for _, y in items) / len(items)
        ece += (len(items) / total) * abs(avg_prediction - actual_rate)
    return round(ece, 6)


def upsert_model_registry(
    db: Database,
    model_name: str,
    model_family: str,
    timing: str,
    status: str,
    active: int,
    calibrated: int,
    feature_names: list[str],
    metrics: dict[str, Any],
    notes: str,
) -> None:
    db.execute(
        """
        INSERT INTO model_registry(
            model_name, model_family, timing, status, generated_at, active,
            calibrated, feature_names_json, metrics_json, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(model_name) DO UPDATE SET
            model_family = excluded.model_family,
            timing = excluded.timing,
            status = excluded.status,
            generated_at = excluded.generated_at,
            active = excluded.active,
            calibrated = excluded.calibrated,
            feature_names_json = excluded.feature_names_json,
            metrics_json = excluded.metrics_json,
            notes = excluded.notes
        """,
        (
            model_name,
            model_family,
            timing,
            status,
            utc_now(),
            active,
            calibrated,
            json.dumps(feature_names, sort_keys=True),
            json.dumps(metrics, sort_keys=True, default=float),
            notes,
        ),
    )


def _empty_team_stats() -> dict[str, Any]:
    return {
        "matches": 0,
        "wins": 0,
        "runs_for": 0,
        "runs_against": 0,
        "wickets_for": 0,
        "wickets_against": 0,
        "venues": defaultdict(int),
        "last_date": None,
    }


def _win_rate(stats: dict[str, Any]) -> float:
    return float(stats["wins"]) / float(stats["matches"]) if stats["matches"] else 0.5


def _avg(stats: dict[str, Any], numerator: str, denominator: str, default: float) -> float:
    return float(stats[numerator]) / float(stats[denominator]) if stats[denominator] else default


def _rest_days(stats: dict[str, Any], match_date: str) -> float:
    if not stats.get("last_date"):
        return 30.0
    current = date.fromisoformat(match_date)
    previous = date.fromisoformat(str(stats["last_date"]))
    return float(max(0, min(180, (current - previous).days)))


def _toss_team_a(row: dict[str, Any]) -> float:
    if row["toss_winner"] == row["team_a"]:
        return 1.0
    if row["toss_winner"] == row["team_b"]:
        return -1.0
    return 0.0


def _toss_bat_team_a(row: dict[str, Any]) -> float:
    if row["toss_decision"] not in {"bat", "field"}:
        return 0.0
    if row["toss_winner"] == row["team_a"]:
        return 1.0 if row["toss_decision"] == "bat" else -1.0
    if row["toss_winner"] == row["team_b"]:
        return -1.0 if row["toss_decision"] == "bat" else 1.0
    return 0.0


def _update_team_stats(team_stats: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    team_a = row["team_a"]
    team_b = row["team_b"]
    stats_a = team_stats[team_a]
    stats_b = team_stats[team_b]
    stats_a["matches"] += 1
    stats_b["matches"] += 1
    stats_a["wins"] += int(row["winner"] == team_a)
    stats_b["wins"] += int(row["winner"] == team_b)
    stats_a["runs_for"] += int(row["team_a_runs"])
    stats_a["runs_against"] += int(row["team_b_runs"])
    stats_b["runs_for"] += int(row["team_b_runs"])
    stats_b["runs_against"] += int(row["team_a_runs"])
    stats_a["wickets_for"] += int(row["team_b_wickets"])
    stats_a["wickets_against"] += int(row["team_a_wickets"])
    stats_b["wickets_for"] += int(row["team_a_wickets"])
    stats_b["wickets_against"] += int(row["team_b_wickets"])
    stats_a["venues"][row["venue"]] += 1
    stats_b["venues"][row["venue"]] += 1
    stats_a["last_date"] = row["match_date"]
    stats_b["last_date"] = row["match_date"]
