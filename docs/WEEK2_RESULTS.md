# Week 2 Results

Generated on 2026-06-09.

## Objective

Week 2 added the first supervised model on top of the Week 1 Cricsheet/Elo foundation.

Implemented:

- chronological rolling feature builder
- dependency-light logistic regression using NumPy
- train/validation/test split by date order
- comparison against the Week 1 Elo baseline on the same rows
- test-set calibration buckets
- dashboard panel for supervised-model results

## Dataset

Source rows: decisive Cricsheet T20 matches with Elo history.

- Total feature rows: 5,186
- Train: 3,630 matches, 2005-02-17 to 2024-10-19
- Validation: 778 matches, 2024-10-19 to 2025-08-24
- Test: 778 matches, 2025-08-26 to 2026-06-02

## Features

The model uses chronological, pre-result features:

- Elo difference
- experience difference
- rolling win-rate difference
- rolling average runs-for difference
- rolling average runs-against difference
- rolling wickets-taken difference
- venue-experience difference
- toss winner side
- toss bat/field side
- female match flag
- World Cup match flag

Note: toss features make this closer to a post-toss model. For a pure morning/pre-toss model, train a second variant without toss features.

## Logistic Regression Results

| Split | Matches | Accuracy | Brier | Log Loss |
|---|---:|---:|---:|---:|
| Train | 3,630 | 67.77% | 0.2037 | 0.5925 |
| Validation | 778 | 71.08% | 0.1925 | 0.5672 |
| Test | 778 | 67.99% | 0.2022 | 0.5879 |
| Recent 365d | 1,088 | 69.39% | 0.1973 | 0.5774 |

## Elo Comparison

Same rows, same date splits:

| Split | Matches | Elo Accuracy | Elo Brier | Elo Log Loss |
|---|---:|---:|---:|---:|
| Train | 3,630 | 61.24% | 0.2274 | 0.6453 |
| Validation | 778 | 69.28% | 0.2081 | 0.6056 |
| Test | 778 | 64.52% | 0.2176 | 0.6243 |
| Recent 365d | 1,088 | 66.54% | 0.2117 | 0.6119 |

On the test split, logistic regression improved over Elo by:

- Accuracy: +3.47 percentage points
- Brier score: -0.0153
- Log loss: -0.0364

## Strongest Coefficients

The largest standardized coefficients were:

| Feature | Weight |
|---|---:|
| experience_diff | 0.6448 |
| elo_diff | 0.4217 |
| avg_runs_for_diff | 0.2127 |
| avg_runs_against_diff | -0.1045 |
| venue_experience_diff | 0.0974 |
| avg_wickets_taken_diff | 0.0655 |

Interpretation:

- Elo still matters strongly.
- Experience/sample depth is very influential, which may partly reflect mismatch quality in international T20 datasets.
- Rolling scoring strength adds signal beyond Elo.
- Runs conceded has the expected negative sign.

## Calibration Notes

The test-set logistic buckets are broadly sensible, especially at the extremes:

- 0.0-0.1 bucket: predicted 5.5%, actual 5.9%
- 0.8-0.9 bucket: predicted 84.3%, actual 88.5%
- 0.9-1.0 bucket: predicted 93.1%, actual 95.2%

There is some underconfidence/overconfidence in the middle buckets:

- 0.3-0.4 bucket: predicted 35.3%, actual 46.7%
- 0.6-0.7 bucket: predicted 65.0%, actual 71.0%

That suggests calibration work is useful before this model drives staking.

## Betting Caveat

This is a better sports prediction model than the Week 1 Elo baseline, but it is not yet a proven betting model.

The missing benchmark is market-implied probability and closing-line value. Free historical cricket odds are limited, so the app needs to keep collecting odds snapshots from now onward.

## Next Optimisation Targets

1. Train a pure pre-toss version with toss features removed.
2. Split models by male/female and competition strength.
3. Add player/XI strength once lineup data is available.
4. Add calibrated probabilities with Platt/isotonic-style calibration.
5. Start collecting current odds snapshots and compare against market-implied probability.
