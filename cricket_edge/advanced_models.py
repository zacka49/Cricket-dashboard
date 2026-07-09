from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from .database import Database, utc_now
from .logistic_model import (
    BASE_FEATURE_NAMES,
    POSTTOSS_MODEL_NAME,
    PRETOSS_MODEL_NAME,
    TOSS_FEATURE_NAMES,
    LogisticRegressionTrainer,
    apply_platt_calibrator,
    binary_log_loss,
    build_feature_rows,
    calibration_bins,
    expected_calibration_error,
    fit_platt_calibrator,
    recent_metrics,
    split_metrics,
    upsert_model_registry,
)


GB_MODEL_NAME = "t20_gradient_boosting_posttoss_calibrated_v1"
WEEK3_MODEL_NAMES = [PRETOSS_MODEL_NAME, POSTTOSS_MODEL_NAME, GB_MODEL_NAME]


@dataclass(frozen=True)
class StumpBoostingConfig:
    train_fraction: float = 0.70
    validation_fraction: float = 0.15
    estimators: int = 140
    learning_rate: float = 0.09
    threshold_count: int = 16


def train_week3_models(db: Database) -> dict[str, Any]:
    pretoss = LogisticRegressionTrainer(
        db,
        model_name=PRETOSS_MODEL_NAME,
        feature_names=BASE_FEATURE_NAMES,
        timing="pre_toss",
        calibrated=True,
        notes="Week 3 candidate: morning/pre-toss calibrated logistic model.",
    ).train()
    posttoss = LogisticRegressionTrainer(
        db,
        model_name=POSTTOSS_MODEL_NAME,
        feature_names=BASE_FEATURE_NAMES + TOSS_FEATURE_NAMES,
        timing="post_toss",
        calibrated=True,
        notes="Week 3 candidate: post-toss calibrated logistic model.",
    ).train()
    boosted = StumpGradientBoostingTrainer(db).train()
    set_active_model(db, PRETOSS_MODEL_NAME, "Active for paper mode because morning automation must not rely on toss data.")
    return {
        "pretoss_logistic": pretoss,
        "posttoss_logistic": posttoss,
        "gradient_boosting": boosted,
        "active_model": PRETOSS_MODEL_NAME,
        "comparison": model_comparison(db),
    }


class StumpGradientBoostingTrainer:
    def __init__(self, db: Database, config: StumpBoostingConfig | None = None) -> None:
        self.db = db
        self.config = config or StumpBoostingConfig()
        self.feature_names = BASE_FEATURE_NAMES + TOSS_FEATURE_NAMES

    def train(self) -> dict[str, Any]:
        rows = build_feature_rows(self.db)
        if len(rows) < 200:
            raise RuntimeError("Not enough feature rows to train gradient boosting. Run Week 1 first.")

        n = len(rows)
        train_end = max(1, int(n * self.config.train_fraction))
        val_end = max(train_end + 1, int(n * (self.config.train_fraction + self.config.validation_fraction)))
        val_end = min(val_end, n - 1)
        for idx, row in enumerate(rows):
            row["split"] = "train" if idx < train_end else "validation" if idx < val_end else "test"

        x = np.array([[float(row["features"][name]) for name in self.feature_names] for row in rows], dtype=float)
        y = np.array([float(row["result_a"]) for row in rows], dtype=float)
        means = x[:train_end].mean(axis=0)
        stds = x[:train_end].std(axis=0)
        stds = np.where(stds < 1e-9, 1.0, stds)
        x = (x - means) / stds

        base_rate = min(0.98, max(0.02, float(y[:train_end].mean())))
        scores = np.full(n, np.log(base_rate / (1 - base_rate)), dtype=float)
        stumps: list[dict[str, Any]] = []
        for _ in range(self.config.estimators):
            train_probs = sigmoid(scores[:train_end])
            residual = y[:train_end] - train_probs
            stump = self._best_stump(x[:train_end], residual)
            if not stump:
                break
            update = np.where(x[:, stump["feature_index"]] <= stump["threshold"], stump["left_value"], stump["right_value"])
            scores += self.config.learning_rate * update
            stumps.append(stump)

        calibrator = fit_platt_calibrator(scores[train_end:val_end], y[train_end:val_end])
        probs = apply_platt_calibrator(scores, calibrator)
        self._store_predictions(rows, probs)

        metrics = {
            "model_name": GB_MODEL_NAME,
            "n_matches": n,
            "feature_names": self.feature_names,
            "timing": "post_toss",
            "calibrated": True,
            "splits": {
                "train": split_metrics(rows, probs, "train"),
                "validation": split_metrics(rows, probs, "validation"),
                "test": split_metrics(rows, probs, "test"),
                "recent_365": recent_metrics(rows, probs, 365),
            },
            "calibration": {
                "gradient_boosting_test": calibration_bins(rows, probs, "test"),
                "ece_test": expected_calibration_error(rows, probs, "test"),
            },
            "stump_count": len(stumps),
            "top_stump_features": self._top_stump_features(stumps),
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
                GB_MODEL_NAME,
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
            model_name=GB_MODEL_NAME,
            model_family="stump_gradient_boosting",
            timing="post_toss",
            status="candidate",
            active=0,
            calibrated=1,
            feature_names=self.feature_names,
            metrics=metrics,
            notes="Week 3 nonlinear benchmark using in-repo boosted decision stumps.",
        )
        self.db.log_event("model", f"Trained gradient boosting model {GB_MODEL_NAME}.", metrics)
        return metrics

    def _best_stump(self, x_train: np.ndarray, residual: np.ndarray) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        best_loss = float("inf")
        for feature_index, feature_name in enumerate(self.feature_names):
            values = x_train[:, feature_index]
            thresholds = np.quantile(values, np.linspace(0.05, 0.95, self.config.threshold_count))
            for threshold in np.unique(thresholds):
                left_mask = values <= threshold
                right_mask = ~left_mask
                if left_mask.sum() < 20 or right_mask.sum() < 20:
                    continue
                left_value = float(residual[left_mask].mean())
                right_value = float(residual[right_mask].mean())
                pred = np.where(left_mask, left_value, right_value)
                loss = float(np.mean((residual - pred) ** 2))
                if loss < best_loss:
                    best_loss = loss
                    best = {
                        "feature_index": int(feature_index),
                        "feature": feature_name,
                        "threshold": round(float(threshold), 6),
                        "left_value": round(left_value, 6),
                        "right_value": round(right_value, 6),
                        "loss": round(best_loss, 8),
                    }
        return best

    def _store_predictions(self, rows: list[dict[str, Any]], probs: np.ndarray) -> None:
        self.db.execute("DELETE FROM model_predictions WHERE model_name = ?", (GB_MODEL_NAME,))
        prediction_rows = []
        for row, pred in zip(rows, probs):
            brier = (float(pred) - float(row["result_a"])) ** 2
            loss = binary_log_loss(float(pred), float(row["result_a"]))
            prediction_rows.append(
                (
                    GB_MODEL_NAME,
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

    def _top_stump_features(self, stumps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for stump in stumps:
            counts[stump["feature"]] = counts.get(stump["feature"], 0) + 1
        return [
            {"feature": feature, "count": count}
            for feature, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:8]
        ]


def set_active_model(db: Database, model_name: str, reason: str) -> None:
    db.execute("UPDATE model_registry SET active = 0")
    db.execute(
        """
        UPDATE model_registry
        SET active = 1, status = 'active', notes = ?
        WHERE model_name = ?
        """,
        (reason, model_name),
    )
    db.log_event("model_registry", f"Set active model to {model_name}.", {"reason": reason})


def latest_week3_report(db: Database) -> dict[str, Any]:
    return {
        "registry": db.query(
            """
            SELECT *
            FROM model_registry
            ORDER BY active DESC, generated_at DESC, model_name
            """
        ),
        "comparison": model_comparison(db),
    }


def model_comparison(db: Database) -> list[dict[str, Any]]:
    rows = db.query(
        """
        SELECT *
        FROM model_runs
        WHERE model_name IN (?, ?, ?)
        ORDER BY generated_at DESC
        """,
        (PRETOSS_MODEL_NAME, POSTTOSS_MODEL_NAME, GB_MODEL_NAME),
    )
    latest_by_model: dict[str, dict[str, Any]] = {}
    for row in rows:
        latest_by_model.setdefault(row["model_name"], row)
    output = []
    registry = {row["model_name"]: row for row in db.query("SELECT * FROM model_registry")}
    for model_name, row in latest_by_model.items():
        payload = json.loads(row["payload_json"])
        test = payload.get("splits", {}).get("test", {})
        recent = payload.get("splits", {}).get("recent_365", {})
        calibration = payload.get("calibration", {})
        reg = registry.get(model_name, {})
        output.append(
            {
                "model_name": model_name,
                "timing": payload.get("timing", reg.get("timing", "")),
                "active": int(reg.get("active", 0) or 0),
                "calibrated": bool(payload.get("calibrated", reg.get("calibrated", 0))),
                "test_accuracy": test.get("accuracy", 0),
                "test_brier": test.get("brier", 0),
                "test_log_loss": test.get("log_loss", 0),
                "recent_365_brier": recent.get("brier", 0),
                "ece_test": calibration.get("ece_test", 0),
            }
        )
    return sorted(output, key=lambda item: (item["active"] == 0, item["test_brier"]))


def sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -35, 35)))
