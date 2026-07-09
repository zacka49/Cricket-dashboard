# Week 4 Results

Generated on 2026-06-09.

## Objective

Week 4 implemented the market layer needed to start evaluating betting value.

Implemented:

- current odds normalization
- market odds snapshot table
- current market-implied baseline table
- synthetic historical market baseline for plumbing checks
- paper bet CLV evaluation table
- dashboard panels for odds, market baseline, and CLV
- optional manual odds CSV import path

## Current Odds Snapshot Layer

The current app/demo fixture odds were normalized into the new market tables.

- Market odds rows: 20
- Fixtures with odds: 5
- Current market baseline rows: 10

These rows come from the app's current fixture odds. Real odds can be imported later through `scripts/week4_build.py --csv`.

## Synthetic Market Baseline

Model: `market_implied_synthetic_v1`

This is not real market data. It is a temporary benchmark generated from Elo plus deterministic noise so that the dashboard, model comparison, and market-baseline plumbing can be tested before enough real odds snapshots exist.

Synthetic benchmark test results:

- Matches: 778
- Accuracy: 64.52%
- Brier: 0.2170
- Log loss: 0.6222

This is close to the Week 1 Elo baseline and below the Week 3 active model, which is useful for development testing. It must be replaced by real market-implied probabilities as odds snapshots accumulate.

## Paper CLV

Existing paper bets evaluated:

| Bet | Entry Odds | Latest/Closing Proxy | CLV |
|---:|---:|---:|---:|
| 1 | 2.551 | 2.538 | +0.51% |
| 2 | 2.034 | 2.082 | pending |

The second bet is still pending because the fixture date has not arrived, so no closing proxy was assigned.

## Manual Odds CSV Format

Optional import command:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" .\scripts\week4_build.py --csv .\data\raw\odds\manual_odds.csv
```

Expected columns:

```text
fixture_id,match_id,source,bookmaker,market,selection,decimal_odds,captured_at,is_closing_proxy,mapping_confidence
```

Only `selection` and `decimal_odds` are strictly required if the row can be matched later, but fixture/match ids are strongly preferred.

## Betting Caveat

The system can now store and normalize odds, but it still needs real odds history. Historical cricket odds are usually paid, so the most practical free route is to collect snapshots going forward.

The next priority is to connect a free odds source or manual import and run the system daily so it builds its own historical odds database.
