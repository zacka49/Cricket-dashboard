# Architecture

## Runtime Flow

```text
fixtures / odds / weather
  -> feature builder
  -> prediction engine
  -> decision pipeline
  -> hard risk policy
  -> paper broker
  -> market monitor
  -> settlement and reporting
```

## Why Predictions Are Rule-Based

Cricket Edge keeps probability estimation deterministic and auditable. Prediction models output probabilities, fair odds, edge, and uncertainty; pipeline steps consume that structured output, apply risk rules, and write reviewable decisions.

Hard risk policy controls paper execution. Missing, stale, malformed, or demo odds block betting decisions rather than being patched over with narrative reasoning.

## Decision Pipeline Steps

`DataHealthCheck`

- checks whether fixtures, odds, and predictions exist
- writes data-health decisions to the audit log

`BetEvaluator`

- reads prediction rows
- applies hard risk rules
- places paper bets through the paper broker when rules allow
- records deterministic bet/skip reasons

`RiskGate`

- checks bankroll, exposure, confidence, and edge limits
- blocks paper execution when any required control fails

`PositionMonitor`

- reads open paper bets
- compares entry odds with latest odds
- simulates cash-out when odds move far enough

`BriefingWriter`

- produces a daily briefing from account state and top model edges

## Broker Boundary

`PaperBroker` is intentionally separate from the decision pipeline and prediction code. A future real-money connector should implement the same style of interface but live in a different module with explicit safety gates.

No real-money connector exists in this repository.
