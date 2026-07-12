# Modelling Upgrade Plan

Purpose: upgrade Cricket Edge from a solid baseline modelling stack into a more serious probability, edge, and staking research system while keeping paper-only execution, chronological validation, and fail-closed betting gates.

Operating constraints:
- Paper-only. Do not add real-money placement.
- No lookahead. Every feature, odds snapshot, and backtest row must be available at the simulated decision timestamp.
- Keep Elo and logistic regression as permanent baselines, even after stronger models are added.
- Select active models by out-of-sample calibration and betting utility, not raw accuracy.
- Missing/stale/demo odds must block bet eligibility, not become neutral assumptions.

Status values: `todo`, `in_progress`, `done`. If these are copied into `.agents/TASKS.md`, claim one task by filling `owner`, `claimed_at`, and setting `status: in_progress`.

## M1 - Modelling Data Audit And Dataset Contract
- owner_recommendation: Codex
- owner:
- claimed_at:
- status: todo
- depends_on: []
- files: cricket_edge/logistic_model.py, cricket_edge/live_model.py, cricket_edge/database.py, tests/test_model_dataset.py (new)
- goal: Define one canonical modelling dataset contract for historical training and live prediction. The contract should list each feature, timing (`pre_toss`, `post_toss`, future `in_play`), source table, leakage boundary, missing-value policy, and live availability. Add a small builder-level validation that rejects rows with impossible dates, missing result labels, duplicate match ids, or features that are unavailable at the requested timing.
- acceptance_criteria: A dataset metadata payload is stored in every model run; historical and live feature builders use the same feature definitions; tests prove post-toss features are absent from pre-toss models and that duplicate/malformed rows are rejected.
- verification: `python -m pytest tests/test_model_dataset.py -q`

## M2 - Feature Store V2: Better Cricket Signal
- owner_recommendation: Codex
- owner:
- claimed_at:
- status: todo
- depends_on: [M1]
- files: cricket_edge/logistic_model.py, cricket_edge/live_model.py, cricket_edge/database.py, scripts/build_data_and_elo.py, tests/test_feature_store.py (new)
- goal: Add stronger leakage-safe features computed only from prior matches: rolling form windows (last 3/5/10), batting run-rate and wickets-lost rates, bowling economy proxy, chase/defend split, toss-decision historical impact, venue/country experience, competition strength buckets, gender-specific baselines, days since last match, and data-coverage counts. Store feature provenance and coverage flags with model predictions.
- acceptance_criteria: Feature rows are deterministic, chronological, and reproducible from raw Cricsheet tables; live features use the same transforms with neutral/default values only when the source is genuinely unavailable; every neutral/default has an explicit coverage flag.
- verification: `python -m pytest tests/test_feature_store.py tests/test_live_model.py -q`

## M3 - Market-Aware Training Dataset
- owner_recommendation: Codex
- owner:
- claimed_at:
- status: todo
- depends_on: [M1]
- files: cricket_edge/market.py, cricket_edge/backtesting.py, cricket_edge/database.py, cricket_edge/logistic_model.py, tests/test_market_training_dataset.py (new)
- goal: Build a market-aware training/evaluation view that joins model rows to opening/latest/closing-proxy prices without leaking future odds into features. Calculate no-vig market probability, overround, closing proxy, implied edge, and CLV labels for each eligible historical match.
- acceptance_criteria: Backtests and model evaluation can report ROI/yield/drawdown/CLV by competition, market, model, edge bucket, confidence bucket, and closing-line result; no row uses a market price captured after the simulated decision timestamp.
- verification: `python -m pytest tests/test_market_training_dataset.py tests/test_backtesting_readiness.py -q`

## M4 - Walk-Forward Evaluation Harness
- owner_recommendation: Codex
- owner:
- claimed_at:
- status: todo
- depends_on: [M1, M2, M3]
- files: cricket_edge/model_selection.py (new), cricket_edge/advanced_models.py, cricket_edge/logistic_model.py, scripts/train_and_govern_models.py, tests/test_model_selection.py (new)
- goal: Replace single train/validation/test splits as the main selection signal with rolling walk-forward folds. Each fold should train on historical data up to a cutoff, calibrate on a forward validation window, and test on the next chronological window. Aggregate Brier score, log loss, ECE, ROI, yield, drawdown, CLV, and sample counts.
- acceptance_criteria: Model run payloads include fold-level and aggregate metrics; the old split metrics may remain for dashboard continuity but promotion decisions use walk-forward aggregate metrics; tests catch shuffled or overlapping folds.
- verification: `python -m pytest tests/test_model_selection.py -q`

## M5 - Calibration Layer Upgrade
- owner_recommendation: Codex
- owner:
- claimed_at:
- status: todo
- depends_on: [M4]
- files: cricket_edge/calibration.py (new), cricket_edge/logistic_model.py, cricket_edge/advanced_models.py, tests/test_calibration.py (new)
- goal: Move calibration into a reusable module supporting Platt scaling, isotonic-style monotonic bin calibration, and optional shrinkage toward 0.5 for thin samples. Select calibration method per model family using validation/window performance, and store calibration diagnostics in model runs.
- acceptance_criteria: Calibration never fits on test rows; every active model has Brier/log-loss/ECE before and after calibration; calibration method and parameters are serializable and usable by live prediction.
- verification: `python -m pytest tests/test_calibration.py tests/test_model_selection.py -q`

## M6 - Stronger Model Families With Baseline Discipline
- owner_recommendation: Codex
- owner:
- claimed_at:
- status: todo
- depends_on: [M2, M4, M5]
- files: cricket_edge/advanced_models.py, cricket_edge/model_selection.py, requirements.txt, tests/test_advanced_models.py (new or expanded)
- goal: Add regularized logistic variants and one production-grade tree booster only if the dependency is available and justified (`lightgbm` preferred, otherwise keep the in-repo stump booster). Model families should include: Elo baseline, calibrated pre-toss logistic, calibrated post-toss logistic, regularized interaction logistic, and boosted trees. Keep coefficients/feature importance explainable.
- acceptance_criteria: The system can train and compare all configured families; missing optional booster dependencies degrade cleanly to the in-repo stump booster; no boosted model can become active unless it beats the logistic baseline on calibration and betting utility.
- verification: `python -m pytest tests/test_advanced_models.py tests/test_model_selection.py -q`

## M7 - Promotion Gate Based On Betting Utility
- owner_recommendation: Codex
- owner:
- claimed_at:
- status: todo
- depends_on: [M3, M4, M5, M6]
- files: cricket_edge/advanced_models.py, cricket_edge/model_selection.py, cricket_edge/backtesting.py, tests/test_model_governance.py
- goal: Replace the current `test_brier`-only promotion rule with a multi-metric gate: candidate must beat incumbent on walk-forward Brier or log loss, have acceptable ECE, avoid worse drawdown, and show non-negative CLV/yield on eligible real-odds backtests. Include minimum sample thresholds and keep incumbent on ties or insufficient data.
- acceptance_criteria: Promotion reasons state every metric used; candidates with better accuracy but worse calibration/CLV are rejected; candidates with sparse market data are marked inconclusive rather than promoted.
- verification: `python -m pytest tests/test_model_governance.py tests/test_backtesting_readiness.py -q`

## M8 - Probability Uncertainty And Confidence Redesign
- owner_recommendation: Codex
- owner:
- claimed_at:
- status: todo
- depends_on: [M4, M5]
- files: cricket_edge/prediction.py, cricket_edge/live_model.py, cricket_edge/risk.py, tests/test_prediction_confidence.py (new), tests/test_risk.py (new or expanded)
- goal: Replace the current heuristic confidence with an uncertainty-aware score based on data coverage, model calibration bucket reliability, feature out-of-distribution distance, market freshness, and historical sample size for similar matches. Confidence should explain why a bet was allowed or skipped.
- acceptance_criteria: Predictions include probability, fair odds, edge, model uncertainty, data coverage, calibration bucket support, and confidence components; risk rules can skip low-confidence rows with explicit reasons.
- verification: `python -m pytest tests/test_prediction_confidence.py tests/test_risk.py -q`

## M9 - Backtest Engine V2: Portfolio And Staking Simulation
- owner_recommendation: Codex
- owner:
- claimed_at:
- status: todo
- depends_on: [M3, M7, M8]
- files: cricket_edge/backtesting.py, cricket_edge/risk.py, cricket_edge/database.py, tests/test_backtesting_v2.py (new)
- goal: Expand backtesting from flat stake to portfolio simulation: flat stake, fractional Kelly, capped Kelly, exposure caps, daily loss limits, duplicate-market prevention, odds freshness windows, and market-source filters. Record equity curve, drawdown, turnover, hit rate, ROI, yield, CLV, and skip reasons.
- acceptance_criteria: Backtest output matches live risk rules where possible; duplicate bets on the same fixture/market are impossible; results are broken down by competition, model, edge bucket, confidence bucket, source, and closing-line result.
- verification: `python -m pytest tests/test_backtesting_v2.py tests/test_backtesting_readiness.py -q`

## M10 - Model Registry And Artifact Versioning
- owner_recommendation: Codex
- owner:
- claimed_at:
- status: todo
- depends_on: [M4, M5, M6, M7]
- files: cricket_edge/database.py, cricket_edge/model_artifacts.py (new), cricket_edge/live_model.py, cricket_edge/advanced_models.py, tests/test_model_artifacts.py (new)
- goal: Store complete model artifacts in a stable, versioned format: feature list, scaler stats, coefficients/trees, calibrator, dataset hash, fold config, training code version marker, and promotion metrics. Live prediction should load only active, valid artifacts.
- acceptance_criteria: A model can be trained, persisted, reloaded, and used for live prediction with identical probabilities; artifact validation fails closed when required fields are missing or version-incompatible.
- verification: `python -m pytest tests/test_model_artifacts.py tests/test_live_model.py -q`

## M11 - Dashboard Model Health Panels
- owner_recommendation: either
- owner:
- claimed_at:
- status: todo
- depends_on: [M4, M5, M7, M9, M10]
- files: cricket_edge/charts.py, cricket_edge/orchestrator.py, cricket_edge/web/templates/index.html, cricket_edge/web/static/app.js, docs/ARCHITECTURE.md
- goal: Surface the modelling improvements clearly in the dashboard: active model card, walk-forward metrics, calibration before/after, CLV by bucket, uncertainty/confidence distribution, promotion decision history, and backtest portfolio summary.
- acceptance_criteria: Dashboard shows why the active model is active, where it is weak, and whether paper betting performance is improving; charts render when no data exists with useful empty states.
- verification: `python -m pytest tests/ -q`; manual dashboard check after running training/backtest scripts

## M12 - End-To-End Modelling Rebuild Command
- owner_recommendation: Codex
- owner:
- claimed_at:
- status: todo
- depends_on: [M1, M2, M3, M4, M5, M6, M7, M8, M9, M10]
- files: scripts/rebuild_modelling_stack.py (new), scripts/train_and_govern_models.py, README.md, tests/test_modelling_workflow.py (new)
- goal: Add one reproducible command that rebuilds the modelling stack in the correct order: ingest/verify data, build features, train candidates, calibrate, walk-forward evaluate, backtest, run promotion gate, and print a concise summary.
- acceptance_criteria: A fresh checkout with data present can run the command and produce an active model or a clear fail-closed reason; the command exits non-zero for dataset/odds/schema problems that invalidate modelling.
- verification: `python -m pytest tests/test_modelling_workflow.py -q`; `python scripts/rebuild_modelling_stack.py --dry-run`

## Suggested Implementation Order

1. M1: lock the dataset contract before adding features.
2. M2 and M3 can run in parallel after M1: one improves cricket signal, the other improves market labels.
3. M4 and M5 create the evaluation/calibration foundation.
4. M6 adds stronger models only after evaluation is trustworthy.
5. M7 changes promotion once the metrics are defensible.
6. M8 and M9 connect model probabilities to risk and portfolio simulation.
7. M10 makes artifacts reliable for live prediction.
8. M11 and M12 make the work visible and reproducible.

## First Modelling Expert Recommendations

- Do not chase a fancy model first. The biggest current upside is better leakage-safe features, walk-forward validation, and market-aware evaluation.
- Promote only pre-toss models for real live fixtures until fixture feeds reliably include toss/venue/team context. Keep post-toss models as research/benchmark until live inputs are actually available.
- Treat sparse historical odds as a modelling risk. Brier/log-loss can select the probability model, but betting deployment should wait for enough real market rows to evaluate CLV by edge bucket.
- Keep the current logistic model as the reference champion. A boosted model should be allowed to win only if calibration survives out-of-sample and betting utility improves after costs/overround.
- Every model run should answer five questions: what data was available, what features were used, how calibration performed, whether it beat the market, and why it was or was not promoted.