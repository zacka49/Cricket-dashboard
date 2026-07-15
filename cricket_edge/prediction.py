from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import SETTINGS
from .database import Database, utc_now
from .features import build_match_features, sigmoid
from .live_model import build_live_match_features, data_confidence_factor, load_live_model_snapshot, predict_probability
from .model_scope import T20_MODEL_SCOPE, fixture_is_t20_eligible


MODEL_NAME = "baseline_t20_elo_market_v1"
APPROVED_REAL_ODDS_SOURCES = {"bet365", "the_odds_api"}
REAL_FIXTURE_SOURCES = {"bet365", "the_odds_api"}


class PredictionEngine:
    """Prediction engine with two feature paths.

    Demo fixtures (never bettable, see risk.py) keep the transparent deterministic
    placeholder features. Real fixtures ingested from Bet365/The Odds API run
    through the actual trained pre-toss logistic model against live Elo ratings
    and cumulative team stats. A real fixture without an active governed model
    produces an explicitly blocked prediction instead of falling back to the
    demo placeholder path.
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self._live_snapshot: dict[str, Any] | None | bool = False  # False = not yet loaded

    def run_for_open_fixtures(self) -> list[dict[str, Any]]:
        fixtures = self.db.query(
            """
            SELECT * FROM fixtures
            WHERE status IN ('scheduled', 'live')
            ORDER BY match_date, start_time
            """
        )
        outputs: list[dict[str, Any]] = []
        for fixture in fixtures:
            outputs.extend(self.run_for_fixture(fixture))
        self.db.log_event("model", f"Generated {len(outputs)} match-winner predictions.")
        return outputs

    def run_for_fixture(self, fixture: dict[str, Any]) -> list[dict[str, Any]]:
        if fixture.get('source') in REAL_FIXTURE_SOURCES:
            if not fixture_is_t20_eligible(fixture):
                return self._run_out_of_scope_live_fixture(fixture)
            snapshot = self._get_live_snapshot()
            if snapshot:
                return self._run_live_fixture(fixture, snapshot)
            return self._run_blocked_live_fixture(fixture)
        return self._run_demo_fixture(fixture)

    def _run_demo_fixture(self, fixture: dict[str, Any]) -> list[dict[str, Any]]:
        features = build_match_features(fixture) | {
            'model_artifact_status': 'demo_non_bettable',
            'model_eligible': False,
        }
        raw_prob_a = sigmoid(float(features["strength_delta"]))
        uncertainty = 0.08 + float(features["weather_penalty"])
        prob_a = 0.5 + (raw_prob_a - 0.5) * (1 - uncertainty)
        prob_a = min(0.78, max(0.22, prob_a))
        prob_b = 1 - prob_a
        rows = [
            self._prediction_row(fixture, fixture["team_a"], prob_a, features, MODEL_NAME),
            self._prediction_row(fixture, fixture["team_b"], prob_b, features, MODEL_NAME),
        ]
        for row in rows:
            self._upsert_prediction(row)
        return rows

    def _run_out_of_scope_live_fixture(self, fixture: dict[str, Any]) -> list[dict[str, Any]]:
        """Persist a visible but non-bettable result for a non-T20 live fixture."""
        blocked_model_name = "blocked_unsupported_format_v1"
        self.db.execute(
            "DELETE FROM predictions WHERE fixture_id = ? AND model_name != ?",
            (fixture["id"], blocked_model_name),
        )
        features = {
            "feature_source": "unsupported_model_scope",
            "model_artifact_status": "active_but_out_of_scope",
            "model_eligible": False,
            "model_block_reason": "unsupported_model_scope",
            "model_scope": T20_MODEL_SCOPE,
            "fixture_format": fixture.get("format"),
            "weather_penalty": 0.0,
        }
        rows = [
            self._prediction_row(fixture, fixture["team_a"], 0.5, features, blocked_model_name, 0.0),
            self._prediction_row(fixture, fixture["team_b"], 0.5, features, blocked_model_name, 0.0),
        ]
        for row in rows:
            self._upsert_prediction(row)
        return rows

    def _run_blocked_live_fixture(self, fixture: dict[str, Any]) -> list[dict[str, Any]]:
        '''Persist an auditable non-bettable outcome for a real fixture.'''
        blocked_model_name = 'blocked_no_active_model_v1'
        self.db.execute(
            'DELETE FROM predictions WHERE fixture_id = ? AND model_name != ?',
            (fixture['id'], blocked_model_name),
        )
        features = {
            'feature_source': 'unavailable_live_model',
            'model_artifact_status': 'missing_or_inactive',
            'model_eligible': False,
            'model_block_reason': 'no_valid_active_model',
            'weather_penalty': 0.0,
        }
        rows = [
            self._prediction_row(fixture, fixture['team_a'], 0.5, features, blocked_model_name, 0.0),
            self._prediction_row(fixture, fixture['team_b'], 0.5, features, blocked_model_name, 0.0),
        ]
        for row in rows:
            self._upsert_prediction(row)
        return rows

    def _run_live_fixture(self, fixture: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        # Keep exactly one model's predictions per fixture; a fixture scored under an
        # older/placeholder model name would otherwise linger as a stale extra row
        # rather than being replaced, since the UNIQUE key includes model_name.
        self.db.execute(
            "DELETE FROM predictions WHERE fixture_id = ? AND model_name != ?",
            (fixture["id"], snapshot["model_name"]),
        )
        context = build_live_match_features(fixture, snapshot, self.db)
        context['features'] |= {
            'model_artifact_status': 'active',
            'model_eligible': True,
            'model_registry_generated_at': snapshot['registry_generated_at'],
        }
        prob_a = predict_probability(snapshot, context["features"])
        confidence_scale = data_confidence_factor(context)
        prob_a = min(0.96, max(0.04, prob_a))
        prob_b = 1 - prob_a
        features = context["features"] | {
            "feature_source": context["feature_source"],
            "team_a_elo": context["team_a_elo"],
            "team_b_elo": context["team_b_elo"],
            "team_a_historical_matches": context["team_a_historical_matches"],
            "team_b_historical_matches": context["team_b_historical_matches"],
            "team_a_matched": context["team_a_matched"],
            "team_b_matched": context["team_b_matched"],
            "data_confidence_scale": round(confidence_scale, 3),
            "weather_penalty": 0.0,
        }
        rows = [
            self._prediction_row(fixture, fixture["team_a"], prob_a, features, snapshot["model_name"], confidence_scale),
            self._prediction_row(fixture, fixture["team_b"], prob_b, features, snapshot["model_name"], confidence_scale),
        ]
        for row in rows:
            self._upsert_prediction(row)
        return rows

    def _get_live_snapshot(self) -> dict[str, Any] | None:
        if self._live_snapshot is False:
            self._live_snapshot = load_live_model_snapshot(self.db)
        return self._live_snapshot

    def _prediction_row(
        self,
        fixture: dict[str, Any],
        selection: str,
        probability: float,
        features: dict[str, Any],
        model_name: str,
        confidence_scale: float = 1.0,
    ) -> dict[str, Any]:
        market_odds = self._latest_odds(int(fixture["id"]), selection)
        fair_odds = 1 / probability
        edge = (market_odds["odds"] * probability) - 1 if market_odds["is_fresh"] else -1.0
        enriched_features = features | {
            "market_source": market_odds["source"],
            "market_captured_at": market_odds["captured_at"],
            "market_status": market_odds["status"],
            "market_is_fresh": market_odds["is_fresh"],
            "market_stale_after_minutes": SETTINGS.odds_stale_minutes,
        }
        confidence = min(0.92, max(0.4, 0.5 + abs(probability - 0.5) * 1.35 - float(features["weather_penalty"])))
        confidence *= confidence_scale
        return {
            "fixture_id": fixture["id"],
            "model_name": model_name,
            "generated_at": utc_now(),
            "market": "match_winner",
            "selection": selection,
            "probability": round(probability, 4),
            "fair_odds": round(fair_odds, 3),
            "market_odds": round(market_odds["odds"], 3),
            "edge": round(edge, 4),
            "confidence": round(confidence, 4),
            "features_json": json.dumps(enriched_features, sort_keys=True),
        }

    def _latest_odds(self, fixture_id: int, selection: str) -> dict[str, Any]:
        row = self.db.query_one(
            """
            SELECT odds, source, captured_at FROM odds_snapshots
            WHERE fixture_id = ? AND market = 'match_winner' AND selection = ? AND source IN ('bet365', 'the_odds_api')
            ORDER BY captured_at DESC, id DESC
            LIMIT 1
            """,
            (fixture_id, selection),
        )
        if not row:
            return {"odds": 0.0, "source": None, "captured_at": None, "is_fresh": False, "status": "no_fresh_real_bookmaker_odds"}
        is_fresh = _is_fresh(row["captured_at"])
        source = str(row["source"])
        return {
            "odds": float(row["odds"]) if is_fresh else 0.0,
            "source": source,
            "captured_at": row["captured_at"],
            "is_fresh": is_fresh,
            "status": f"fresh_{source}_odds" if is_fresh else f"stale_{source}_odds",
        }

    def _upsert_prediction(self, row: dict[str, Any]) -> None:
        self.db.execute(
            """
            INSERT INTO predictions(
                fixture_id, model_name, generated_at, market, selection,
                probability, fair_odds, market_odds, edge, confidence, features_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fixture_id, model_name, market, selection)
            DO UPDATE SET
                generated_at = excluded.generated_at,
                probability = excluded.probability,
                fair_odds = excluded.fair_odds,
                market_odds = excluded.market_odds,
                edge = excluded.edge,
                confidence = excluded.confidence,
                features_json = excluded.features_json
            """,
            (
                row["fixture_id"],
                row["model_name"],
                row["generated_at"],
                row["market"],
                row["selection"],
                row["probability"],
                row["fair_odds"],
                row["market_odds"],
                row["edge"],
                row["confidence"],
                row["features_json"],
            ),
        )


def _is_fresh(captured_at: str | None) -> bool:
    if not captured_at:
        return False
    try:
        parsed = datetime.fromisoformat(str(captured_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    minutes_old = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 60
    return 0 <= minutes_old <= SETTINGS.odds_stale_minutes
