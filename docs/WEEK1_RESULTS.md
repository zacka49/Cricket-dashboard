# Week 1 Results

Generated on 2026-06-09.

## Data Ingest

Source: Cricsheet T20 JSON archive.

- Files parsed: 5,341
- Matches inserted: 5,341
- Innings inserted: 10,694
- Skipped files: 0
- Match date range: 2005-02-17 to 2026-06-02
- Venues: 447
- Archive size: 16.1 MB
- SQLite database size after ingest: 3.11 MB

Gender split:

- Male: 3,366 matches
- Female: 1,975 matches

Largest competitions in the ingested set:

- ICC Men's T20 World Cup: 173
- ICC Men's T20 World Cup Sub Regional Africa Qualifier: 115
- ICC World Twenty20: 104
- ICC Women's T20 World Cup: 89
- ICC Men's T20 World Cup Sub Regional Europe Qualifier: 88
- Kwibuka Women's Twenty20 Tournament: 82
- ICC Women's T20 World Cup Asia Region Qualifier: 71
- ICC Men's T20 World Cup Qualifier: 70
- Unknown: 66
- ICC Women's T20 World Cup Qualifier: 59

## Elo Baseline

Model: `t20_team_elo_v1`

Configuration:

- Starting rating: 1500
- K factor: 24
- Home/venue adjustment: 18 Elo points
- Evaluation style: chronological walk-forward

Overall decisive-match evaluation:

- Evaluated matches: 5,186
- Teams rated: 108
- Accuracy: 62.94%
- Brier score: 0.2230
- Log loss: 0.6362

Recent 365-day evaluation:

- Matches: 1,088
- Accuracy: 66.54%
- Brier score: 0.2117
- Log loss: 0.6119

Recent 180-day evaluation:

- Matches: 514
- Accuracy: 67.32%
- Brier score: 0.2122
- Log loss: 0.6133

Top Elo ratings after the latest ingested match:

| Rank | Team | Rating |
|---:|---|---:|
| 1 | England | 1883.6 |
| 2 | India | 1878.7 |
| 3 | Australia | 1861.9 |
| 4 | South Africa | 1800.5 |
| 5 | New Zealand | 1767.0 |
| 6 | Pakistan | 1735.8 |
| 7 | Ireland | 1716.9 |
| 8 | Sri Lanka | 1685.7 |
| 9 | Uganda | 1682.5 |
| 10 | Netherlands | 1680.0 |
| 11 | United Arab Emirates | 1676.6 |
| 12 | Scotland | 1669.6 |

## Interpretation

This is a useful baseline, not yet a betting edge.

The model is deliberately simple: team strength only, chronological updates, and a small venue/home adjustment. The recent evaluation is stronger than the all-time evaluation, which is a good sign, but the next benchmark must be market-implied probability from captured odds. A model is not actionable until it is calibrated and can beat the closing price.

## Next Optimisation Targets

1. Split ratings by men/women and international/domestic competition.
2. Add separate batting and bowling strength features from innings/delivery data.
3. Add recency decay so old results matter less.
4. Add opponent-strength-adjusted margin or run-rate features.
5. Add market-implied probability as the benchmark once enough odds snapshots are collected.
