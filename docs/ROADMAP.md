# Roadmap

## Phase 1: Working Paper Dashboard

- local web app
- demo fixtures
- demo odds
- baseline prediction model
- paper broker
- decision log
- cash-out simulation
- event/audit log

Status: implemented.

## Phase 2: Real Free Data Ingestion

- download Cricsheet T20 JSON
- parse matches and deliveries into SQLite or DuckDB
- build team and player feature tables
- fetch Open-Meteo weather by venue
- collect real odds snapshots with The Odds API

Week 1 implementation now includes:

- Cricsheet T20 JSON ZIP ingestion
- aggregate match and innings tables
- chronological team Elo training
- Brier score, log loss, and accuracy evaluation
- Week 1 dashboard model-lab panel

See `docs/WEEK1_RESULTS.md` for the first full run.

## Phase 3: Better Prediction Models

- train/test splits by date
- Elo baseline
- logistic regression baseline
- gradient boosting model
- probability calibration
- Brier score and log loss dashboard
- closing-line value dashboard

Week 2 implementation includes:

- chronological rolling feature builder
- dependency-light logistic regression
- train/validation/test split by date order
- comparison against Elo on the same splits
- test-set calibration buckets
- Week 2 dashboard panel

See `docs/WEEK2_RESULTS.md` for the first supervised-model run.

## Phase 4: Stronger Decision Rules

- automated backtest critique checks
- automated research-management checks
- automated feature-engineering pipeline
- correlated-exposure risk checks

Detailed Week 3 and Week 4 execution plan:

- `docs/WEEK3_WEEK4_PLAN.md`
- `docs/BULLETPROOFING_CHECKLIST.md`

Implemented Week 3/4 build scripts:

- `scripts/week3_build.py`
- `scripts/week4_build.py`

See also:

- `docs/WEEK3_RESULTS.md`
- `docs/WEEK4_RESULTS.md`

## Phase 5: In-Play Paper Trading

- live score state ingestion from a free or manual source
- in-play win probability model
- hedge/cash-out simulation from current odds
- strict market-staleness rules

## Phase 6: Real-Money Readiness Review

Only consider this after hundreds of paper decisions and strong closing-line value.

Required checks:

- no data leakage
- stable calibration
- maximum drawdown understood
- market liquidity assumptions tested
- exact broker API failure modes documented
- manual kill switch
- daily hard loss limit
- separate paper/live configuration
