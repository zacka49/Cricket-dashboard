# Architecture

## Runtime Flow

```text
fixtures / odds / weather
  -> feature builder
  -> prediction engine
  -> hard risk policy
  -> LLM-compatible decision agents
  -> paper broker
  -> market monitor
  -> settlement and reporting
```

## Why LLMs Are Not The Prediction Model

LLMs are useful for interpretation, workflow monitoring, and research management. They are not reliable enough to be the probability engine.

In this system:

- prediction models output probabilities and fair odds
- agents read structured model output
- agents explain, rank, and challenge decisions
- hard risk rules control execution

## Agent Responsibilities

`DataStewardAgent`

- checks whether fixtures, odds, and predictions exist
- writes data-health decisions to the audit log

`BetDecisionAgent`

- reads prediction rows
- applies hard risk rules
- optionally asks a local LLM for a concise reason
- places paper bets through the paper broker

`MarketWatchAgent`

- reads open paper bets
- compares entry odds with latest odds
- simulates cash-out when odds move far enough

`ReportWriterAgent`

- produces a daily briefing from account state and top model edges

## Broker Boundary

`PaperBroker` is intentionally separate from agents and prediction code. A future real-money connector should implement the same style of interface but live in a different module with explicit safety gates.

No real-money connector exists in this repository.
