# Session Summary — 2026-07-09

## Context

Zackary is building out `cricket-edge` as his lead GitHub portfolio project ahead of his GSK contract ending end of August 2026, targeting AI engineer / quant roles. This session covered a project review, two backend fixes, and a full dashboard redesign.

## What happened this session

### 1. Initial project review
Read through the full codebase (docs, agents, models, market layer, tests). Findings:
- The modeling side (Cricsheet-trained walk-forward Elo, from-scratch NumPy logistic regression, calibration, CLV framing, fractional Kelly staking) was genuinely solid — above the level of a typical solo portfolio project.
- The *live* prediction loop was disconnected from that work: `features.py` generated team strength from a SHA-256 hash of the team name, not the trained models. The four agent classes (`DataStewardAgent`, `BetDecisionAgent`, `MarketWatchAgent`, `ReportWriterAgent`) had genuine separation of concerns but no real inter-agent coordination (no agent could override another's decision), and the LLM call only explained an already-fully-deterministic decision.
- 3 of 24 tests were failing. No git repo existed yet. Live-looking API keys sat in `.env` (correctly gitignored).

### 2. Fixed a real `.env` bug
`.env` had several `KEY=value` pairs crammed onto one line, so the parser (which splits only on the first `=`) silently appended garbage onto `ODDS_API_KEY`. This was very likely why live odds fetching wasn't reliable. Fixed by putting each variable on its own line. All 24 tests started passing immediately after (the 3 failures were the market layer being unable to authenticate).

### 3. Built a "pull all live data" feature
- New `cricket_edge/live_data.py` (`pull_all_live_data`) — fetches live odds (Bet365 via odds-api.io, The Odds API fallback) and refreshes the Cricsheet historical archive if it's more than 24h stale (previously downloaded once, never refreshed).
- Wired into a new `Pull All Live Data` dashboard button, `scripts/pull_live_data.py`, and `orchestrator.pull_live_data()`.
- Verified live against the real APIs: 25 events checked, 18 odds rows inserted, zero errors.
- Deliberately did **not** wire in weather: neither odds provider returns a real match venue, so there's no reliable way to map a live fixture to a location for Open-Meteo. Documented as an explicit gap in the README rather than faked.

### 4. Wired the trained model into the live prediction loop
This was the biggest fix. New `cricket_edge/live_model.py`:
- `current_team_elo_ratings()` (added to `elo.py`) and `current_team_stats()` (added to `logistic_model.py`) reconstruct each team's latest Elo rating and cumulative stats from historical data.
- `build_live_match_features()` computes the same feature set the trained pre-toss logistic model (`t20_logistic_pretoss_calibrated_v1`) was trained on, for real (non-demo) fixtures — using real Elo/stats instead of hashes.
- A small, verified team-name alias map (`Hong Kong, China` → `Hong Kong`, `Utd Arab Emirates` → `United Arab Emirates`, `USA` → `United States of America`) handles naming mismatches between the odds provider and Cricsheet.
- Teams with zero Cricsheet history (confirmed case: a Bengal Pro T20 League franchise fixture) fall back to a neutral 1500 Elo prior, and their prediction **confidence is scaled toward 0** — so the existing risk gate correctly skips betting on fixtures the model has no real basis for, instead of confidently betting on a coin flip.
- `prediction.py` now branches: demo fixtures keep the old placeholder (clearly labeled, never bettable anyway); real fixtures use the trained model.
- Verified end-to-end: ran a full `morning_run` — 180 predictions, 176 decisions evaluated, 2 paper bets placed off real edges. All 24 tests still pass.
- **Found in passing, not fixed**: the historical strategy backtest (`backtesting.py`) always returns 0 bets, because `market_baselines` is never populated with historical (`match_id`-keyed) rows — only live fixture-scoped rows exist. Pre-existing, unrelated to this session's changes.

### 5. Dashboard redesign
Rebuilt the whole frontend as a 4-page app instead of one long scroll, using Plotly (industry-standard, not hand-rolled) built server-side in Python:
- **New `cricket_edge/charts.py`** — Plotly figure builders: model comparison (all trained models' Brier/log-loss/accuracy), calibration reliability diagram, feature-importance / coefficient chart, Elo top-ratings, equity curve, backtest P&L, ROI-by-edge-bucket. Wired into `orchestrator.build_state()` under a new `charts` key.
- **`scripts/vendor_plotlyjs.py`** — vendors `plotly.js` locally (no CDN) so the dashboard stays fully offline. Added to `.gitignore` as a generated artifact.
- **Pages**: Overview (project summary, new agent-pipeline diagram, daily briefing, readiness checklist), Models (training data, all charts above, model registry, historical backtest), Paper Bets (live predictions with model-source transparency badges, equity curve, bet history, CLV), Data & Logs (odds feed health, event log).
- Full visual refresh of `styles.css` (refined palette/typography, tab navigation, chart containers, pipeline diagram styling).
- Verified: all 24 tests pass, `/api/state` returns valid chart specs, static assets and POST endpoints all confirmed working via direct HTTP checks. Visual rendering was confirmed by Zackary in-browser (I can't drive a browser myself).
- Noted separately: `Run Morning` hung for several minutes during verification — isolated (by calling the odds fetch directly, bypassing the whole web/dashboard stack) to the live odds API being slow/rate-limited from the day's heavy testing, not a redesign bug.

### 6. Housekeeping
- Scoped a Claude Code permission rule so file edits inside `cricket-edge/` auto-accept without a prompt (personal `settings.local.json`, not project-shared); everything else (Bash, edits elsewhere) still asks as normal.

## Further points of improvement (not yet done)

Roughly in priority order for the GitHub portfolio push:

1. **Give the agents real coordinating behavior.** Right now they're a well-separated pipeline, not yet agentic in the sense of one agent overriding another. Concrete option discussed: a Risk Agent that can veto a `BetDecisionAgent` bet, or a Backtest Critic Agent that gates model promotion. This is the single highest-value fix for the "multi-agent system" claim to hold up under scrutiny.
2. **Fix the historical backtest gap.** `market_baselines` needs historical (`match_id`-keyed) rows populated from real captured odds history (or the synthetic benchmark, if intentional) so `run_latest_strategy_backtest` can actually produce bets instead of always returning zero.
3. **Make cricket-edge a git repo and clean it for GitHub.** `git init`, confirm `.env`/`data/`/logs/`__pycache__`/`plotly.min.js` stay excluded (`.gitignore` already covers these), remove the stray empty file named `=` (flagged in the original review, not yet removed), and add a short "Known Limitations" section to the README naming the backtest gap and the weather gap explicitly — reviewers trust projects that admit this more than ones that hide it.
4. **Add a real out-of-sample backtest result with CLV**, once #2 is fixed — a small but real "beat the market" result is a stronger portfolio signal than more scaffolding.
5. **Expand test coverage for `agents.py` decision logic** specifically — currently the four agent classes have no dedicated tests, only integration-style coverage via `test_workflow.py`/`test_real_odds_gate.py`.
6. **Expand the team-name alias map** as more live fixtures surface naming mismatches (currently only 3 known aliases, verified against Cricsheet — easy to extend the same way).
7. **Resilience for live odds fetching**: `Run Morning`/`Pull All Live Data` currently have no overall timeout across the ~25+ sequential per-event odds calls, so a slow/rate-limited API can make the whole action hang for minutes. Worth adding an overall time budget or concurrency to `fetch_bet365_cricket_odds`.
8. **Visual QA pass on the new dashboard** — Zackary confirmed it "looks good" in-browser, but worth a deliberate pass through all 4 pages checking chart interactivity (hover/zoom), responsive behavior at narrower widths, and the empty-state messaging on a fresh database.
