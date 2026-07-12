# Model Improvement Plan

Generated: 2026-07-12

## Executive Summary

The web app has a useful cricket betting research workflow, but the current model layer is still closer to a calibrated research baseline than a proven betting model. The strongest implemented production path is the pre-toss calibrated logistic model (`t20_logistic_pretoss_calibrated_v1`) fed by Cricsheet-derived rolling team features and Elo. Historical docs show it beats the Elo baseline on prediction metrics, but the current local SQLite database has no trained model runs or Cricsheet rows, and there is not yet enough real historical odds coverage to prove betting edge, ROI, yield, drawdown, or CLV.

The priority is not to jump straight to a more complex algorithm. First make evaluation reproducible from the current checkout, build a real odds-linked backtest dataset, and measure calibration plus betting utility by market segment. Once that is in place, add richer features and benchmark stronger models against simple baselines.

## Current Model Inventory

| Layer | Implementation | Current role | Notes |
|---|---|---|---|
| Demo fallback | `PredictionEngine._run_demo_fixture` in `cricket_edge/prediction.py` | Non-bettable placeholder path | Uses deterministic fixture features and clamps probabilities. Should remain visibly demo-only and never drive betting. |
| Elo baseline | `EloTrainer` in `cricket_edge/elo.py` | Baseline model and live feature input | Chronological team Elo with Brier, log loss, accuracy, and recent-window metrics. Keep it as a baseline even after stronger models are added. |
| Logistic baseline | `LogisticRegressionTrainer` in `cricket_edge/logistic_model.py` | Main supervised model family | NumPy logistic regression with chronological train/validation/test split, rolling team stats, optional toss features, L2 regularization, and Platt calibration. |
| Active live model | `t20_logistic_pretoss_calibrated_v1` loaded by `cricket_edge/live_model.py` | Main live/pre-match probability model | Uses no toss features, so it can run before match day/toss. Live features reuse current Elo and cumulative team stats. |
| Post-toss logistic | `t20_logistic_posttoss_calibrated_v1` | Candidate benchmark | Slightly better historical Brier/log loss than pre-toss, but not suitable for morning pre-toss decisions. |
| Boosted stumps | `StumpGradientBoostingTrainer` in `cricket_edge/advanced_models.py` | Nonlinear benchmark | In-repo gradient boosting over decision stumps. Higher historical accuracy, worse calibration metrics than logistic. |
| Market baselines | `cricket_edge/market.py` | Market-implied benchmarks and odds store | Supports current, historical, and synthetic market baselines. Synthetic market model is plumbing only, not a real edge benchmark. |
| Strategy backtest | `cricket_edge/backtesting.py` | Paper strategy evaluation | Joins model predictions to historical market baselines with timestamp guards, but current data coverage is too small locally. |

## Performance We Can Currently Cite

### Historical documented runs

The best available historical evidence is in `docs/WEEK2_RESULTS.md` and `docs/WEEK3_RESULTS.md`.

| Model | Split / data | Accuracy | Brier | Log loss | ECE |
|---|---:|---:|---:|---:|---:|
| Elo baseline (`t20_team_elo_v1`) | Week 2 test, 778 matches | 64.52% | 0.2176 | 0.6243 | not reported |
| Logistic with toss features (`t20_logistic_regression_v1`) | Week 2 test, 778 matches | 67.99% | 0.2022 | 0.5879 | not reported |
| Pre-toss calibrated logistic (`t20_logistic_pretoss_calibrated_v1`) | Week 3 test, 778 matches | 67.87% | 0.2030 | 0.5900 | 0.0438 |
| Post-toss calibrated logistic (`t20_logistic_posttoss_calibrated_v1`) | Week 3 test, 778 matches | 67.74% | 0.2027 | 0.5893 | 0.0483 |
| Post-toss boosted stumps (`t20_gradient_boosting_posttoss_calibrated_v1`) | Week 3 test, 778 matches | 69.41% | 0.2043 | 0.5936 | 0.0514 |
| Synthetic market baseline (`market_implied_synthetic_v1`) | Week 4 test, 778 matches | 64.52% | 0.2170 | 0.6222 | not reported |

Interpretation:

- The logistic family is meaningfully better than Elo on Brier and log loss.
- The pre-toss model is the right active model for pre-match automation because it avoids toss-time data dependency.
- The boosted-stump model is not better for betting yet because its accuracy improvement comes with worse Brier, log loss, and calibration error.
- No current documented result proves profitable betting. Prediction quality is not the same as positive expected value after bookmaker margin.

### Current local database state

A direct SQLite read of `data/cricket_edge.sqlite3` on 2026-07-12 found:

| Table | Rows |
|---|---:|
| `cricsheet_matches` | 0 |
| `team_elo_history` | 0 |
| `model_predictions` | 0 |
| `model_runs` | 0 |
| `backtest_runs` | 0 |
| `market_baselines` | 10 |
| `odds_snapshots` | 20 |
| `market_odds_snapshots` | 10 |
| `paper_bets` | 0 |

This means the current checkout cannot show model performance from the DB until the data and training scripts are rerun. The plan below treats reproducible local evaluation as the first deliverable.

## Main Weaknesses

1. Reproducibility gap: model results exist in historical Markdown, but the local DB has no trained model runs.
2. Betting utility gap: there is no meaningful real-odds backtest sample yet, so ROI, yield, drawdown, edge-bucket performance, and CLV are not decision-grade.
3. Market baseline gap: synthetic market baselines are useful for plumbing but should not be used to validate edge.
4. Feature ceiling: current features are mostly team-level historical aggregates. There is no player/XI strength, venue-condition model, innings phase information, bookmaker movement feature, or competition-strength hierarchy.
5. Segmentation gap: men's/women's cricket, domestic/international cricket, and competition strength are mixed into one global model with a few flags.
6. Calibration governance is too thin: ECE is reported, but there is no promotion rule combining calibration, log loss, CLV, and betting utility by segment.
7. Live coverage risk: teams with zero Cricsheet history are handled defensively, but alias coverage and thin-history confidence should be monitored as first-class model-health metrics.

## Prioritized Improvement Roadmap

### Phase 1: Rebuild the measurement foundation

Goal: make performance reproducible from a clean checkout.

Tasks:

- Add a single command or script that runs: Cricsheet ingest, Elo training, candidate model training, market layer build, strategy backtest, and report export.
- Persist a machine-readable evaluation artifact under `results/` or `reports/` with model metrics, calibration buckets, top coefficients/features, and backtest summary.
- Add a dashboard/readiness warning when `model_runs` is empty or the active model snapshot is missing.
- Keep the current pre-toss logistic model active until a candidate beats it on out-of-sample Brier/log loss and calibration.

Acceptance criteria:

- A fresh run populates `cricsheet_matches`, `team_elo_history`, `model_runs`, `model_predictions`, and `model_registry`.
- The generated report reproduces the Week 3 style model comparison without manually reading the database.
- Tests cover the empty-model-run warning and the active-model selection rule.

### Phase 2: Build a real odds-linked evaluation set

Goal: evaluate betting decisions against real bookmaker prices, not synthetic odds.

Tasks:

- Continue collecting Bet365/The Odds API snapshots append-only with raw payload retention.
- Backfill historical market baselines only when a fixture links to a resolved Cricsheet match and has real captured odds.
- Store opening, latest, and closing-proxy prices separately for each fixture/market/selection.
- Extend `run_strategy_backtest` to report CLV and performance by competition, model, source, edge bucket, confidence bucket, and closing-line result.
- Add duplicate-bet protection by fixture/market/selection in the historical backtest, matching live paper-bet behavior.

Acceptance criteria:

- Backtests report `n_candidates`, bets, ROI, yield, max drawdown, CLV, and bucket breakdowns from real sources only.
- Reports explicitly show when sample size is too small to trust.
- Synthetic market rows are excluded from any model-promotion or edge-validation decision.

### Phase 3: Improve features before changing algorithms

Goal: add signal that the current team-level model cannot see.

Tasks:

- Add competition-strength features: international vs domestic, league/team pool rating, and competition fixed effects or target-smoothed strength.
- Split or interact features by men's/women's cricket instead of relying only on a single `female_match` flag.
- Add richer recent-form windows: last 5/10 matches, recency-weighted runs, wickets, net run rate proxy, and opponent-adjusted form.
- Add toss-neutral venue conditions for pre-toss models: venue scoring baseline, chasing advantage, historical first-innings par, and team venue experience.
- Build player/XI strength once lineup data exists; until then, create a placeholder interface rather than hard-coding unavailable data.
- Add odds-derived features only for evaluation modes that guarantee timestamp safety: opening implied probability, line movement, bookmaker dispersion, and overround.

Acceptance criteria:

- Every new feature is computed chronologically using only data available before the simulated decision timestamp.
- Feature rows include coverage/missingness metadata so confidence can be reduced when inputs are thin.
- Each feature group has an ablation result against the current pre-toss logistic baseline.

### Phase 4: Add stronger candidate models

Goal: benchmark modern models only after data and features are stable.

Tasks:

- Add scikit-learn as the first modeling dependency so logistic regression, calibration, cross-validation, and preprocessing are less bespoke.
- Benchmark regularized logistic, elastic-net logistic, random forest, histogram gradient boosting, XGBoost/LightGBM if dependencies are acceptable, and a simple ensemble.
- Use time-series validation or rolling-origin folds rather than one fixed 70/15/15 split only.
- Tune hyperparameters with Optuna only after the rolling evaluation harness is in place.
- Keep Elo and current logistic as permanent baselines.

Acceptance criteria:

- Candidate models are compared on Brier, log loss, ECE, calibration buckets, and betting metrics.
- A candidate can become active only if it improves out-of-sample calibration and expected betting utility, not accuracy alone.
- Model artifacts include feature names, preprocessing statistics, calibrator details, split windows, and training data cutoff.

### Phase 5: Tighten model governance

Goal: prevent accidental promotion of a model that looks good for the wrong reason.

Tasks:

- Replace single-test-Brier promotion with a scoring rule that includes Brier, log loss, ECE, recent-window drift, minimum sample size, and real-odds backtest evidence.
- Add segment-level guardrails: do not promote if a model improves globally but fails badly in major competitions or gender segments.
- Add calibration drift alerts comparing recent predictions to actuals as Cricsheet results arrive.
- Track active model lineage: training data cutoff, feature schema version, code version, and promotion reason.
- Add model-health dashboard panels for coverage, missing aliases, thin-history teams, and stale model age.

Acceptance criteria:

- `model_registry` clearly distinguishes candidate, benchmark, active, retired, and blocked models.
- Promotion writes a decision record with all metric deltas and the reason.
- A stale or missing active model blocks paper betting rather than silently falling back to demo behavior for real fixtures.

## Near-Term Implementation Sequence

1. Create `scripts/evaluate_models.py` that rebuilds or checks data, trains candidates, runs backtests, and writes `reports/model_evaluation_latest.json` plus Markdown summary.
2. Add readiness checks for empty `model_runs`, empty `model_predictions`, missing active model, and insufficient real-odds backtest sample.
3. Extend `backtesting.py` to report CLV, confidence buckets, source buckets, and sample-size warnings.
4. Add competition/gender segmentation metrics before changing the active model.
5. Add recency-weighted team-form features and run an ablation against `t20_logistic_pretoss_calibrated_v1`.
6. Introduce scikit-learn logistic/calibration as a parity replacement for the bespoke NumPy trainer, then benchmark stronger models.

## Success Metrics

A model improvement should count only if it improves the decision process, not just the classifier scoreboard.

Required metrics:

- Prediction: Brier, log loss, accuracy, calibration buckets, ECE.
- Betting: ROI, yield, max drawdown, hit rate, average edge, average CLV, positive-CLV rate.
- Robustness: metrics by competition, gender, source, edge bucket, confidence bucket, and team-history coverage bucket.
- Operations: active model age, training data cutoff, missing-feature rate, unmatched-team count, stale-odds block count.

Minimum promotion bar:

- Beats current active pre-toss logistic on test Brier or log loss.
- Does not worsen ECE materially.
- Has no severe segment regression on high-volume segments.
- Shows positive or improving CLV on real odds, with sample size clearly reported.
- Keeps paper-betting gates fail-closed for stale/missing odds and thin model coverage.

## Recommended First PR

Do not start with LightGBM/XGBoost. Start with a reproducible evaluation/reporting PR:

- `scripts/evaluate_models.py`
- `reports/model_evaluation_latest.json` and generated Markdown output
- readiness checks for missing/empty model evaluation state
- backtest sample-size warnings
- tests around report generation and fail-closed behavior

That work will make every later model change measurable. After that, the highest-value modeling work is richer chronological features and segment-aware calibration, then stronger algorithms.