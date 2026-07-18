# Model Evaluation Report

Generated: 2026-07-15T11:05:40+00:00

## Summary

- Active model: t20_logistic_pretoss_calibrated_v1
- Model runs: 4
- Historical predictions: 16089
- Backtest runs: 1
- Pipeline actions: data_build, model_training

## Warnings

- None

## Latest Model Runs

| Model | Generated | Matches | Brier | Log loss | Accuracy |
|---|---:|---:|---:|---:|---:|
| t20_gradient_boosting_posttoss_calibrated_v1 | 2026-07-15T11:05:39+00:00 | 5363 | 0.2054 | 0.5955 | 67.45% |
| t20_logistic_posttoss_calibrated_v1 | 2026-07-15T11:05:31+00:00 | 5363 | 0.2033 | 0.5903 | 67.70% |
| t20_logistic_pretoss_calibrated_v1 | 2026-07-15T11:05:27+00:00 | 5363 | 0.2032 | 0.5901 | 67.95% |
| t20_team_elo_v1 | 2026-07-15T11:05:14+00:00 | 5363 | 0.2229 | 0.6359 | 62.86% |

## Backtest

- Candidates: 0
- Bets: 0
- ROI: 0.00%
- Max drawdown: 0.00

## Readiness

- pass: Real-money connector disabled - The app exposes only a paper broker and has no live-money execution path.
- pass: Paper broker state - Paper account exists and bankroll/exposure can be audited.
- pass: Bet365 odds feed configured - ODDS_API_KEY is loaded from environment/.env; the key itself is never displayed.
- pass: Real bookmaker odds captured - At least one Bet365 market snapshot has been stored.
- watch: Fresh-odds betting gate - Risk decisions explicitly block missing or stale Bet365 odds.
- pass: Model training data - Cricsheet matches and chronological Elo rows must exist before supervised evaluation can be reproduced.
- pass: Model evaluation runs - At least one model run should be stored with Brier score, log loss, accuracy, and payload metrics.
- pass: Historical model predictions - Historical predictions are needed for calibration review and strategy backtests.
- pass: Active model registry - One active model should be selected for paper execution.
- gap: Historical strategy backtesting - Run the market data build/backtest after historical market odds exist.
- watch: Backtest sample size - A research-grade read needs at least 30 bets from timestamp-valid real market baselines.
- pass: Paper CLV tracking - Paper bet evaluations compare entry odds against the latest closing proxy.
- pass: Decision audit trail - Pipeline decisions are persisted with reasons and payloads.
- pass: Background scheduler heartbeat - Background scheduler ticks monitor/settle continuously and retrains on a schedule, without manual button presses.
- pass: Regression tests - Pytest coverage exists for odds parsing, risk gates, workflows, server routes, and backtesting.
