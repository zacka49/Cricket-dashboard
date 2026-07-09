# Bulletproofing Checklist

This checklist defines what "robust enough" means for Cricket Edge.

The standard is not "the model looks good." The standard is that the whole system can explain every decision, survive bad inputs, and prove whether it is beating the market.

## Data Safety

- Raw data is stored before parsing.
- Parsed data is reproducible from raw files.
- Every fixture has a stable source id.
- Team names are normalized through a mapping table.
- Venue names are normalized through a mapping table.
- Duplicate fixtures are detected.
- Missing results are flagged.
- Odds snapshots have timestamps.
- Odds snapshots have source labels.
- Odds staleness is measured.
- Data quality checks run before every model run.

## Leakage Protection

- No future match data enters training features.
- Rolling stats use prior matches only.
- Train/validation/test splits are chronological.
- Toss features are excluded from pre-toss models.
- Post-toss models are labelled separately.
- In-play models are labelled separately.
- Calibration is fitted on validation data only.
- Test data is not used for feature tuning.

## Model Governance

- Every model has a version name.
- Every model stores its feature list.
- Every model stores its training date range.
- Every model stores its validation/test date range.
- Every model stores Brier score and log loss.
- Every model stores calibration buckets.
- Only one active model is used for paper execution.
- Model promotion requires a written reason.
- Model rollback is possible.

## Betting Decision Safety

- No bet without a fresh odds snapshot.
- No bet without an active model version.
- No bet if data quality checks fail.
- No bet if market is outside validated scope.
- No bet if edge is below threshold.
- No bet if confidence is too low.
- No bet if daily exposure limit is reached.
- No bet if correlated exposure limit is breached.
- Stake sizing is deterministic and logged.
- Every decision logs bet/skip/watchlist reason.

## Paper Broker Safety

- Paper broker is separate from any future real broker.
- Real-money connector is not implemented by default.
- Paper orders have timestamps.
- Paper orders record model version.
- Paper orders record odds source and odds timestamp.
- Cash-out actions are logged.
- Settlement logic is reproducible.
- P&L is separated from CLV.

## Market Evaluation

- Market-implied probability is calculated.
- Overround-adjusted market probability is calculated.
- Model is compared to market baseline.
- Closing price is stored or approximated.
- Closing-line value is calculated.
- CLV is reviewed weekly.
- ROI is never trusted without CLV context.

## Agent Safety

- Agents consume structured data only.
- Agents do not invent probabilities.
- Agents cannot bypass hard risk rules.
- Agent prompts are versioned.
- Agent outputs are stored as JSON where possible.
- Backtest Critic Agent reviews model changes.
- Risk Agent reviews exposure before execution.
- Market Watch Agent flags stale/moving prices.

## Operations

- The app can restart without losing data.
- Logs are written to SQLite or files.
- Long-running jobs report status.
- Failed jobs report an actionable error.
- Database backups are possible.
- Schema migrations are explicit.
- Secrets are kept out of code.
- API keys are loaded from environment variables.

## Real-Money Gate

Do not add a live broker until all of these are true:

- 500+ paper bets or a statistically meaningful sample.
- Positive CLV after costs/commission assumptions.
- Stable calibration on recent data.
- No unresolved high-severity data-quality issues.
- Drawdown profile is understood.
- Kill switch exists.
- Daily loss limit exists.
- Manual approval mode works.
- Live broker has a dry-run mode.
- Paper and live credentials/configs are impossible to confuse.
