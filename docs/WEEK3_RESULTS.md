# Week 3 Results

Generated on 2026-06-09.

## Objective

Week 3 implemented model governance and stronger calibrated model variants.

Implemented:

- true pre-toss logistic model
- post-toss logistic model
- lightweight in-repo gradient boosting model
- Platt-style validation calibration
- model registry table
- active model flag
- dashboard panels for model registry and candidate comparison

## Models Trained

| Model | Timing | Status | Calibrated |
|---|---|---|---|
| `t20_logistic_pretoss_calibrated_v1` | pre-toss | active | yes |
| `t20_logistic_posttoss_calibrated_v1` | post-toss | candidate | yes |
| `t20_gradient_boosting_posttoss_calibrated_v1` | post-toss | candidate | yes |

The active model is `t20_logistic_pretoss_calibrated_v1` because morning automation must not depend on toss information.

## Test Results

All models use the same 5,186 decisive Cricsheet T20 rows and the same chronological split.

| Model | Timing | Accuracy | Brier | Log Loss | ECE |
|---|---|---:|---:|---:|---:|
| `t20_logistic_pretoss_calibrated_v1` | pre-toss | 67.87% | 0.2030 | 0.5900 | 0.0438 |
| `t20_logistic_posttoss_calibrated_v1` | post-toss | 67.74% | 0.2027 | 0.5893 | 0.0483 |
| `t20_gradient_boosting_posttoss_calibrated_v1` | post-toss | 69.41% | 0.2043 | 0.5936 | 0.0514 |

## Interpretation

The post-toss logistic model has a marginally better Brier/log-loss than the pre-toss model, but the difference is small. The boosted-stump model has better raw accuracy, but worse Brier/log-loss and calibration error. For betting, Brier/log-loss/calibration matter more than accuracy, so the logistic models are preferred.

The pre-toss model remains active because it is the correct model for a morning autonomous workflow.

## Current Active Model

`t20_logistic_pretoss_calibrated_v1`

Reason:

- usable before toss
- calibrated
- close to post-toss performance
- better governance fit for morning automation

## Next Model Work

1. Add competition-strength segmentation.
2. Add men/women model split.
3. Add XI/player-strength features.
4. Add calibration drift monitoring.
5. Promote/demote active model only through registry decisions.
