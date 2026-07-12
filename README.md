# Cricket Edge

Cricket Edge is a local-first cricket betting research and paper-trading system. Once running, a background scheduler monitors positions, settles paper bets against real results, and retrains/evaluates models on its own schedule. It runs in paper mode only: it can create simulated bets, monitor them, cash out in simulation, and settle them against real match outcomes as they become available.

The important design choice is separation between prediction, risk control, and execution:

- statistical models estimate probability, fair odds, edge, and uncertainty
- deterministic pipeline steps check data health, evaluate bets, apply risk rules, monitor positions, and write daily briefings
- hard risk rules decide whether paper execution is allowed
- a model-promotion gate retrains candidate models on a schedule and only promotes one that beats the incumbent
- the broker is paper-only until the models prove calibration and closing-line value

## Current MVP

This first build is dependency-light and works offline with the Python standard library:

- local web dashboard
- SQLite data store
- demo fixtures and odds
- transparent baseline T20 prediction model
- paper bankroll
- paper bet placement
- a background scheduler that runs the daily cycle, continuous monitoring/settlement, and scheduled model retraining without manual intervention
- a real model-promotion gate: a retrained model only goes live if it actually beats the incumbent on held-out data
- simulated market monitoring
- simulated cash-out rules
- decision log and daily briefing
- event log and audit trail
- compact dashboard action responses so long workflows reload state cleanly
- stubs/free-source adapters for Cricsheet and Open-Meteo
- typed Bet365 cricket odds ingestion through odds-api.io when `ODDS_API_KEY` is configured
- The Odds API cricket odds fallback when `THE_ODDS_API_KEY` is configured
- real-odds betting gate: demo/stale odds are prediction context only and cannot trigger paper bets
- historical strategy backtest reporting from stored market baselines
- portfolio readiness checklist for model, odds, CLV, scheduling, and paper-safety gaps
- a 4-page dashboard (Trading Floor / Quant Research / Positions / Ops & Compliance) with a decision-pipeline diagram and interactive Plotly charts (model comparison, calibration reliability, feature importance, equity curve, backtest P&L)

## Run It

Simplest: open `run.py` at the repo root and press Run/F5 in VS Code, or from a terminal:

```powershell
python run.py
```

From the project folder, auto-detecting a suitable Python interpreter:

```powershell
.\scripts\run_windows.ps1
```

Or directly:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m cricket_edge
```

Then open:

```text
http://127.0.0.1:8765
```

The dashboard is a 4-page app: **Trading Floor** (project summary, decision pipeline diagram, daily briefing, readiness checklist, scheduler status), **Quant Research** (training data, model comparison/calibration/feature-importance charts, registry, historical backtest), **Positions** (live fixtures/predictions, equity curve, bet history, CLV), and **Ops & Compliance** (odds feed health, event log). Starting the server also starts the background scheduler (see "Background Scheduler" below). The manual buttons on every page stay available as overrides, but nothing requires them.

### One-time setup: vendor Plotly locally

Charts are built server-side with `plotly.graph_objects` and rendered client-side with `plotly.js`, vendored locally so nothing is fetched from a CDN:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m pip install -r requirements.txt
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" .\scripts\vendor_plotlyjs.py
```

Re-run `vendor_plotlyjs.py` after upgrading the `plotly` package.

## Data Pipeline: Cricsheet Ingestion & Elo Baseline

To download Cricsheet T20 history, parse match/innings tables, and train the first Elo baseline:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" .\scripts\build_data_and_elo.py
```

The results appear in the dashboard under `Cricsheet + T20 Elo Model`.

## Research: Logistic Regression Model

To train the first chronological logistic-regression model and compare it against Elo:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" .\scripts\train_logistic_model.py
```

The results appear in the dashboard under `Logistic Regression vs Elo`.

## Next Plans

Detailed next-step plans:

- [Bulletproofing Checklist](docs/BULLETPROOFING_CHECKLIST.md)

## Quant Research: Model Training & Governance

To train calibrated pre-toss/post-toss models and a lightweight gradient-boosting benchmark, and to run the promotion gate that decides whether the new pre-toss model actually replaces the active one:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" .\scripts\train_and_govern_models.py
```

A candidate only gets promoted if its held-out test Brier score beats the current active model's. Otherwise the incumbent stays active. Either verdict is logged to the decision trail as `model_governance`. The results appear in the dashboard under `Model Registry and Calibration`.

## Trading Desk: Market Data & CLV Layer

To normalize current odds snapshots, update market-implied baselines, build the temporary synthetic market benchmark, backfill real historical baselines, and update paper CLV:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" .\scripts\build_market_layer.py
```

Optional manual odds import:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" .\scripts\build_market_layer.py --csv .\data\raw\odds\manual_odds.csv
```

This also attempts a strategy backtest for the active/latest model when historical market baselines are available. The backtest uses only odds timestamps on or before the simulated match date.

## Background Scheduler

Starting the app (`run.py`, `python -m cricket_edge`, or `run_windows.ps1`) also starts `BackgroundScheduler` on a background thread. There is no separate process or script to launch. On a configurable tick (`CRICKET_EDGE_SCHEDULER_TICK_SECONDS`, default 300s), it:

- always runs a monitor tick and settlement pass (both cheap/idempotent when nothing's due)
- runs the full morning cycle once per calendar day
- retrains and re-evaluates models whenever `CRICKET_EDGE_SCHEDULER_RETRAIN_INTERVAL_HOURS` (default 24) have passed, or `CRICKET_EDGE_SCHEDULER_RETRAIN_NEW_MATCH_THRESHOLD` (default 20) new Cricsheet matches have landed since the last retrain, whichever comes first
- catches and logs any single tick's failure rather than letting it kill the loop

Set `CRICKET_EDGE_SCHEDULER_ENABLED=false` to disable it (for manual-only operation). The Trading Floor page shows a live scheduler banner (running/starting/disabled, last tick, last retrain) sourced from `/api/state`'s `scheduler` key.

## Live Odds Feed

The dashboard first tries Bet365 cricket odds through odds-api.io:

```powershell
ODDS_API_KEY=your_key_here
ODDS_API_IO_BASE_URL=https://api.odds-api.io/v3
ODDS_API_IO_SPORT=cricket
ODDS_API_BOOKMAKERS=Bet365
ODDS_API_MAX_EVENTS=25
```

If that feed is exhausted, stale, or returns no fresh prices, Cricket Edge can fall back to The Odds API:

```powershell
THE_ODDS_API_KEY=your_key_here
THE_ODDS_API_BASE_URL=https://api.the-odds-api.com
THE_ODDS_API_REGIONS=uk,eu,au
THE_ODDS_API_MARKETS=h2h
THE_ODDS_API_SPORT_KEYS=cricket_international_t20,cricket_t20_blast,cricket_ipl,cricket_odi,cricket_test_match
THE_ODDS_API_MAX_SPORTS=5
```

Put those values in `.env` in the project folder. `.env` is ignored by git.

Manual refresh:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" .\scripts\fetch_bet365_odds.py
```

Or click `Fetch Live Odds` in the dashboard. `Run Morning` and `Monitor Tick` also attempt a live odds refresh before prediction and paper-monitoring work. Generated odds are only used for demo fixtures and are not bettable. Paper bets require fresh `bet365` or `the_odds_api` odds inside `CRICKET_EDGE_ODDS_STALE_MINUTES`.

The odds layer uses `httpx` for API calls, `tenacity` for retries, `pydantic` for response schemas, and tested utility functions for implied probability, overround, and no-vig probabilities.

Each variable in `.env` must be on its own line (`KEY=value`, one per line). A single line with multiple space-separated `KEY=value` pairs will silently corrupt whichever key comes first, since only the text after the first `=` is read as its value.

## Pull All Live Data

To fetch everything free this project currently supports in one go - live cricket odds (Bet365 via odds-api.io, falling back to The Odds API) and a freshness-checked Cricsheet historical archive - and persist all of it (raw JSON snapshots under `data/raw/`, plus structured rows in `market_odds_snapshots`/`odds_snapshots` for later backtesting or CLV analysis):

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" .\scripts\pull_live_data.py
```

Or click `Pull All Live Data` in the dashboard. This does not touch weather: Open-Meteo integration exists in `data_sources.py`, but neither odds provider returns a real match venue, so there is currently no reliable way to map live fixtures to a location for weather. Treat that as a documented gap, not a silent one.

## Dashboard Buttons

Global workflow actions live in the sidebar on every page:

- `Run Morning`: seeds/refreshes data, runs predictions, evaluates candidates through the decision pipeline, and places paper bets if rules allow.
- `Monitor Tick`: refreshes market context, reruns predictions, and lets the position monitor hold or cash out paper bets.
- `Fetch Live Odds`: imports current cricket match-winner prices into the prediction and market layers, using The Odds API as a fallback when the primary Bet365 feed is stale or empty.
- `Pull All Live Data`: runs `Fetch Live Odds` plus a freshness-checked Cricsheet historical archive refresh in one action.
- `Settle Paper`: settles a paper bet only once its fixture is linked to a real, confirmed Cricsheet result; bets on fixtures Cricsheet hasn't caught up with yet stay `open` rather than being given a guessed outcome. See Known Limitations.
- `Reset Demo`: clears fixtures, predictions, paper bets, decision logs, and events, then rebuilds demo data.

Model-retraining actions live contextually at the top of the **Quant Research** page:

- `Train Elo`, `Train Logistic`: retrain the corresponding models.
- `Force Retrain Now`: manually triggers the same governed training/promotion cycle the background scheduler runs on its own schedule.
- `Rebuild Market Data`: normalizes odds snapshots, updates market baselines, updates paper CLV, and runs the latest available strategy backtest.

## Project Layout

```text
cricket-edge/
  run.py                # root-level launcher (VS Code Run/F5, or `python run.py`)
  cricket_edge/
    advanced_models.py  # calibrated/gradient-boosting model training + promotion gate
    pipeline.py         # deterministic decision pipeline steps
    scheduler.py        # background scheduler: daily cycle, monitoring, scheduled retraining
    backtesting.py      # timestamp-safe paper strategy backtests
    charts.py           # Plotly figure builders for the dashboard
    config.py           # environment/runtime settings
    data_sources.py     # free-source adapters
    database.py         # SQLite schema and helpers
    features.py         # transparent demo features
    live_data.py        # single entry point to pull every free live/historical source
    live_model.py       # wires the trained model into live (non-demo) predictions
    orchestrator.py     # morning run / monitor / settle workflows
    paper_broker.py     # paper-only execution and cash-out simulation
    prediction.py       # prediction engine (demo placeholder + trained-model paths)
    readiness.py        # portfolio and safety checklist reporting
    seed.py             # demo fixtures, weather, and odds
    server.py           # local web server + scheduler startup
    web/
      templates/        # index.html (4-page dashboard shell)
      static/           # app.js, styles.css, plotly.min.js (vendored, not checked in)
  data/
  docs/
  scripts/              # includes vendor_plotlyjs.py, pull_live_data.py, build_data_and_elo.py
  tests/
```

## Free Data Plan

The intended free-source stack is:

- Cricsheet JSON/CSV downloads for historical cricket ball-by-ball data
- Open-Meteo for weather forecast and historical weather
- The Odds API free tier for limited current odds snapshots
- locally captured odds snapshots for your own historical odds database

Historical betting odds are the main free-data weakness. The system should begin storing odds snapshots as early as possible because that private database becomes a core asset.

## Known Limitations

This project favors admitting a gap over faking data to fill it. Current known gaps:

- **No weather-to-fixture mapping.** Neither odds provider returns a real match venue, so live fixtures can't be reliably mapped to a location for Open-Meteo. See `Pull All Live Data` above.
- **Real settlement and the historical backtest both lag behind real matches.** A paper bet only settles once Cricsheet's archive actually contains that match's result (matched by team names and date); until then it stays `open` rather than being settled with a guessed outcome. Likewise, the historical strategy backtest only has as many rows as fixtures with both a captured real odds snapshot and a resolved Cricsheet result. Cricsheet ingestion (`scripts/build_data_and_elo.py`) is a manual step, not run automatically by `Pull All Live Data` or the background scheduler, so both can take real time to catch up. That's expected, not a bug.
- **`market_implied_historical_v1` is a real (if currently sparse) benchmark; `SYNTHETIC_MARKET_MODEL` is not.** `market.py::build_synthetic_market_baseline` generates an Elo-plus-noise benchmark purely to exercise the model-comparison charts. It's explicitly tagged `not_real_market_odds: True` in its stored predictions and should never be read as a real edge.

## Real-Money Safety

There is no real-money betting connector in this build. Keep it that way until paper mode proves:

- strong calibration
- positive closing-line value
- stable performance over a meaningful sample
- no data leakage
- sensible drawdown behavior
- clean data-quality monitoring

The correct upgrade path is to implement a broker interface and keep paper/live brokers completely separate.
