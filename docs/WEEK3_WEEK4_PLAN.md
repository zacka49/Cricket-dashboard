# Week 3 and Week 4 Plan

This plan assumes the Week 1 Cricsheet/Elo baseline and Week 2 logistic-regression model are already built.

The next two weeks should focus on turning the project from a prediction dashboard into a measured betting research system. The priority is not more complexity for its own sake. The priority is proving which model outputs are calibrated, stable, and useful against market prices.

## Week 3: Stronger Models and Calibration

### Goal

Build stronger prediction models, separate model variants properly, and add calibration so probabilities can be trusted before they reach the paper broker.

### Deliverables

1. Pre-toss logistic model
2. Post-toss logistic model
3. Gradient boosting model
4. Calibration layer
5. Model comparison dashboard
6. Model registry table
7. Backtest report by split, gender, competition, and confidence bucket

### Model Variants

Create these model variants explicitly:

| Model | Timing | Purpose |
|---|---|---|
| `t20_elo_v1` | pre-match | simple benchmark |
| `t20_logistic_pretoss_v1` | morning/pre-toss | main early-day model |
| `t20_logistic_posttoss_v1` | post-toss | improved late-entry model |
| `t20_gradient_boosting_v1` | pre/post variants | nonlinear benchmark |
| `market_implied_v1` | once odds exist | market benchmark |

The current Week 2 model includes toss features, so treat it as closer to a post-toss model. Week 3 should add a true morning/pre-toss version with toss features removed.

### Feature Work

Add feature groups:

- team Elo difference
- rolling win rate
- rolling runs scored and conceded
- rolling wickets taken and lost
- venue par score
- venue familiarity
- gender flag
- competition strength proxy
- recent match volume
- days since last match
- batting first/chasing historical bias
- toss features only in the post-toss model

Avoid leakage:

- every rolling feature must use matches before the current match only
- no final score, innings result, winner, or post-match derived value can enter pre-match features
- train/validation/test split must remain chronological
- never random split sports time-series data

### Gradient Boosting

Use the best available dependency path:

- If `scikit-learn` is available, use `HistGradientBoostingClassifier` or `GradientBoostingClassifier`.
- If `lightgbm` becomes available later, use LightGBM.
- If no package is available, keep Week 3 focused on calibrated logistic variants and add gradient boosting later.

Target metrics:

- Brier score
- log loss
- calibration error
- accuracy
- confidence-bucket performance
- stability across recent 365 days

Do not optimise for raw ROI yet. Without historical market odds, ROI backtests are incomplete.

### Calibration

Add:

- calibration bins for every model
- expected calibration error
- reliability table
- optional Platt-style calibration using validation predictions

Acceptance criteria:

- calibrated model should improve or preserve test-set log loss
- high-confidence buckets should be directionally reliable
- calibration must be calculated out of sample

### Dashboard Additions

Add a `Model Comparison` panel:

- model name
- timing: pre-toss/post-toss
- test Brier
- test log loss
- test accuracy
- recent 365-day Brier
- calibration error
- top feature drivers

Add a `Calibration` panel:

- bucket
- average predicted probability
- actual win rate
- sample size
- gap

Add a `Model Registry` panel:

- model version
- features used
- training date
- data range
- status: experimental / candidate / active

### Week 3 Exit Criteria

Week 3 is done when:

- pre-toss and post-toss models exist separately
- logistic vs gradient/logistic variants are compared on the same date splits
- calibration is visible in the dashboard
- the app can mark exactly one model as the active paper-trading model
- the active model choice is justified by Brier/log-loss/calibration, not accuracy alone

## Week 4: Odds, Paper Trading, and Decision Quality

### Goal

Start measuring betting value properly by collecting market odds snapshots, comparing model probabilities to market-implied probabilities, and upgrading paper execution to use real decision logs instead of demo odds.

### Deliverables

1. Odds snapshot collector
2. Market-implied probability baseline
3. Closing-line value tracker
4. Paper bet settlement from real fixture results where possible
5. Risk engine upgrade
6. Agent review upgrade
7. Daily paper-trading report

### Odds Collection

Use free sources only:

- The Odds API free tier if an API key is available
- manual CSV import as a fallback
- stored local snapshots as the main long-term asset

Schema requirements:

- fixture id
- source
- bookmaker/exchange
- market
- selection
- decimal odds
- implied probability
- overround-adjusted probability
- captured timestamp
- fixture mapping confidence
- market status: open/suspended/closed if available

Important: historical odds are usually paid, so start collecting now. Even limited daily snapshots become valuable over time.

### Market Baselines

Add:

- raw implied probability
- overround-adjusted implied probability
- best available price
- opening price
- latest price
- closing price proxy

Compare each model against:

- market-implied Brier
- market-implied log loss
- model probability vs market probability
- edge by bucket
- closing-line value

### Paper Bet Rules

Upgrade the paper broker to require:

- active model is calibrated
- odds snapshot is fresh
- market edge exceeds threshold
- model confidence is acceptable
- data quality check passes
- no correlated exposure breach
- stake is capped by bankroll policy

Recommended starting thresholds:

- minimum edge: 3% to 5%
- minimum odds freshness: less than 15 minutes
- maximum stake: 0.25% to 1.0% of bankroll
- maximum daily exposure: 5% to 8% of bankroll
- no bet if model is outside validated market scope

### Closing-Line Value

Track for every paper bet:

- taken odds
- final available odds before start
- model probability at bet time
- model probability near close
- CLV percent
- result
- paper P&L

Useful CLV formula:

```text
CLV = taken_odds / closing_odds - 1
```

Positive CLV over time is more meaningful than short-term ROI.

### Agent Upgrades

Add or strengthen:

`Backtest Critic Agent`

- flags leakage risk
- flags unstable sample sizes
- flags suspiciously high performance
- checks whether the model was compared to market baseline

`Risk Agent`

- checks daily exposure
- checks correlated bets
- checks repeated exposure to same team/competition
- checks stake sizing

`Market Watch Agent`

- explains odds movement
- flags stale prices
- flags market disagreement
- recommends hold/cash-out in paper mode

`Daily Report Agent`

- reports model performance
- reports paper bets placed
- reports CLV
- reports data issues
- reports next research tasks

### Week 4 Exit Criteria

Week 4 is done when:

- odds snapshots are collected into SQLite
- the dashboard shows market-implied probability
- paper bets use real/current odds snapshots where available
- every bet logs edge, stake, model version, odds timestamp, and decision reason
- CLV is calculated for closed paper bets
- daily reports distinguish prediction quality from betting execution quality

## After Week 4: Make It Robust

The project becomes serious only after it can survive bad data, stale odds, model drift, and process failures. The next phases should harden the system before any real-money connector is considered.

### Week 5: Data Quality and Monitoring

Add:

- fixture mapping confidence checks
- team-name normalization table
- venue normalization table
- data freshness checks
- odds staleness alerts
- missing-result reconciliation
- duplicate fixture detection
- schema migration scripts

Acceptance criteria:

- no model run proceeds if critical data checks fail
- data issues are visible in the dashboard
- each issue has severity and owner/action

### Week 6: Backtesting and Experiment Management

Add:

- experiment registry
- saved feature set per model version
- repeatable backtest runner
- train/validation/test date windows
- strategy-level paper backtests
- flat stake vs fractional Kelly comparison
- drawdown and losing-streak analysis

Acceptance criteria:

- every model result is reproducible
- every model version has a feature list and training data range
- no strategy can be marked active without a backtest report

### Week 7: In-Play Paper Trading

Add only after pre-match paper trading is stable:

- live score state ingestion
- in-play win-probability model
- odds movement monitor
- simulated hedge/cash-out logic
- strict delay/staleness controls

Acceptance criteria:

- in-play model has separate validation
- no in-play decision uses stale score or stale odds
- cash-out logic is tested in paper mode only

### Week 8: Real-Money Readiness Review

This is a review phase, not a build phase.

Real-money execution should remain disabled unless all checks pass:

- at least several hundred paper bets
- positive CLV over a meaningful sample
- stable calibration
- no unresolved data-quality failures
- maximum drawdown understood
- kill switch implemented
- daily loss limits implemented
- real and paper brokers completely separated
- manual approval mode tested before automation

## Priority Order

If time is limited, do this order:

1. Pre-toss logistic model
2. Model calibration
3. Odds snapshot collection
4. Market-implied baseline
5. CLV tracker
6. Active model registry
7. Paper broker using real odds
8. Risk agent and backtest critic

That order gives the highest chance of learning whether the system has a real edge.
