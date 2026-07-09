# Cricket Edge

Cricket Edge is a local-first cricket betting research dashboard. It runs in paper mode only: it can create simulated bets, monitor them, cash out in simulation, and settle them against demo outcomes.

The important design choice is separation of duties:

- statistical models estimate probability, fair odds, edge, and uncertainty
- hard risk rules decide whether execution is allowed
- local LLM agents interpret the model output, explain decisions, and monitor workflow quality
- the broker is paper-only until the model proves calibration and closing-line value

## Current MVP

This first build is dependency-light and works offline with the Python standard library:

- local web dashboard
- SQLite data store
- demo fixtures and odds
- transparent baseline T20 prediction model
- paper bankroll
- paper bet placement
- simulated market monitoring
- simulated cash-out rules
- agent decisions and daily briefing
- event log and audit trail
- compact dashboard action responses so long workflows reload state cleanly
- stubs/free-source adapters for Cricsheet and Open-Meteo
- typed Bet365 cricket odds ingestion through odds-api.io when `ODDS_API_KEY` is configured
- The Odds API cricket odds fallback when `THE_ODDS_API_KEY` is configured
- real-odds betting gate: demo/stale odds are prediction context only and cannot trigger paper bets
- historical strategy backtest reporting from stored market baselines
- portfolio readiness checklist for model, odds, CLV, scheduler, and paper-safety gaps
- a 4-page dashboard (Overview / Models / Paper Bets / Data & Logs) with an agent-pipeline diagram and interactive Plotly charts (model comparison, calibration reliability, feature importance, equity curve, backtest P&L)

## Run It

From the project folder:

```powershell
.\scripts\run_windows.ps1
```

Or directly:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m cricket_edge
```

Then open:

```text
http://127.0.0.1:8765
```

The dashboard is a 4-page app: **Overview** (project summary, agent pipeline diagram, daily briefing, readiness checklist), **Models** (training data, model comparison/calibration/feature-importance charts, registry, historical backtest), **Paper Bets** (live fixtures/predictions, equity curve, bet history, CLV), and **Data & Logs** (odds feed health, event log).

### One-time setup: vendor Plotly locally

Charts are built server-side with `plotly.graph_objects` and rendered client-side with `plotly.js`, vendored locally so nothing is fetched from a CDN:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m pip install -r requirements.txt
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" .\scripts\vendor_plotlyjs.py
```

Re-run `vendor_plotlyjs.py` after upgrading the `plotly` package.

## Week 1 Data Build

To download Cricsheet T20 history, parse match/innings tables, and train the first Elo baseline:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" .\scripts\week1_build.py
```

The results appear in the dashboard under `Cricsheet + T20 Elo Model`.

## Week 2 Supervised Build

To train the first chronological logistic-regression model and compare it against Elo:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" .\scripts\week2_build.py
```

The results appear in the dashboard under `Logistic Regression vs Elo`.

## Next Plans

Detailed next-step plans:

- [Week 3 and Week 4 Plan](docs/WEEK3_WEEK4_PLAN.md)
- [Bulletproofing Checklist](docs/BULLETPROOFING_CHECKLIST.md)

## Week 3 Model Governance Build

To train calibrated pre-toss/post-toss models, a lightweight gradient-boosting benchmark, and update the model registry:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" .\scripts\week3_build.py
```

The results appear in the dashboard under `Model Registry and Calibration`.

## Week 4 Market Layer Build

To normalize current odds snapshots, update market-implied baselines, build the temporary synthetic market benchmark, and update paper CLV:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" .\scripts\week4_build.py
```

Optional manual odds import:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" .\scripts\week4_build.py --csv .\data\raw\odds\manual_odds.csv
```

Week 4 also attempts a strategy backtest for the active/latest model when historical market baselines are available. The backtest uses only odds timestamps on or before the simulated match date.

## Paper Scheduler

To run one morning workflow followed by repeated paper monitor cycles:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" .\scripts\run_paper_scheduler.py --monitor-cycles 6 --interval-seconds 300
```

For a quick local smoke test:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" .\scripts\run_paper_scheduler.py --monitor-cycles 1 --interval-seconds 0
```

This remains paper-only. It does not place real bets.

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
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" .\scripts\fetch_bet365_odds.py
```

Or click `Fetch Live Odds` in the dashboard. `Run Morning` and `Monitor Tick` also attempt a live odds refresh before prediction and paper-monitoring work. Generated odds are only used for demo fixtures and are not bettable. Paper bets require fresh `bet365` or `the_odds_api` odds inside `CRICKET_EDGE_ODDS_STALE_MINUTES`.

The odds layer uses `httpx` for API calls, `tenacity` for retries, `pydantic` for response schemas, and tested utility functions for implied probability, overround, and no-vig probabilities.

Each variable in `.env` must be on its own line (`KEY=value`, one per line). A single line with multiple space-separated `KEY=value` pairs will silently corrupt whichever key comes first, since only the text after the first `=` is read as its value.

## Pull All Live Data

To fetch everything free this project currently supports in one go — live cricket odds (Bet365 via odds-api.io, falling back to The Odds API) and a freshness-checked Cricsheet historical archive — and persist all of it (raw JSON snapshots under `data/raw/`, plus structured rows in `market_odds_snapshots`/`odds_snapshots` for later backtesting or CLV analysis):

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" .\scripts\pull_live_data.py
```

Or click `Pull All Live Data` in the dashboard. This does not touch weather: Open-Meteo integration exists in `data_sources.py`, but neither odds provider returns a real match venue, so there is currently no reliable way to map live fixtures to a location for weather. Treat that as a documented gap, not a silent one.

## Dashboard Buttons

Global workflow actions live in the sidebar on every page:

- `Run Morning`: seeds/refreshes data, runs predictions, lets agents review candidates, and places paper bets if rules allow.
- `Monitor Tick`: simulates a live odds refresh, reruns predictions, and lets the Market Watch Agent hold or cash out paper bets.
- `Fetch Live Odds`: imports current cricket match-winner prices into the prediction and market layers, using The Odds API as a fallback when the primary Bet365 feed is stale or empty.
- `Pull All Live Data`: runs `Fetch Live Odds` plus a freshness-checked Cricsheet historical archive refresh in one action.
- `Settle Paper`: settles a paper bet only once its fixture is linked to a real, confirmed Cricsheet result; bets on fixtures Cricsheet hasn't caught up with yet stay `open` rather than being given a guessed outcome. See Known Limitations.
- `Reset Demo`: clears fixtures, predictions, paper bets, agent decisions, and logs, then rebuilds demo data.

Model-retraining actions live contextually at the top of the **Models** page:

- `Train Elo`, `Train Logistic`, `Train Week 3`: retrain the corresponding models.
- `Run Week 4`: normalizes odds snapshots, updates market baselines, updates paper CLV, and runs the latest available strategy backtest.

## Project Layout

```text
cricket-edge/
  cricket_edge/
    agents.py          # LLM-compatible decision agents
    backtesting.py     # timestamp-safe paper strategy backtests
    charts.py           # Plotly figure builders for the dashboard
    config.py          # environment/runtime settings
    data_sources.py    # free-source adapters
    database.py        # SQLite schema and helpers
    features.py        # transparent demo features
    live_data.py        # single entry point to pull every free live/historical source
    live_model.py        # wires the trained model into live (non-demo) predictions
    llm.py             # Ollama HTTP client
    orchestrator.py    # morning run / monitor / settle workflows
    paper_broker.py    # paper-only execution and cash-out simulation
    prediction.py      # prediction engine (demo placeholder + trained-model paths)
    readiness.py       # portfolio and safety checklist reporting
    scheduler.py       # paper-only morning/monitor cycle runner
    seed.py            # demo fixtures, weather, and odds
    server.py          # local web server
    web/
      templates/        # index.html (4-page dashboard shell)
      static/            # app.js, styles.css, plotly.min.js (vendored, not checked in)
  data/
  docs/
  scripts/              # includes vendor_plotlyjs.py, pull_live_data.py
  tests/
```

## Local LLMs

The app can call a local Ollama-compatible endpoint if it is running:

```powershell
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:OLLAMA_MODEL = "gemma4-daytrader:latest"
```

If Ollama is not running, the agents use deterministic fallback reasoning. This keeps the app usable while still being ready for your local Gemma/Qwen/Phi models later.

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
- **Real settlement and the historical backtest both lag behind real matches.** A paper bet only settles once Cricsheet's archive actually contains that match's result (matched by team names and date); until then it stays `open` rather than being settled with a guessed outcome. Likewise, the historical strategy backtest only has as many rows as fixtures with both a captured real odds snapshot and a resolved Cricsheet result. Cricsheet ingestion (`scripts/week1_build.py`) is a manual step, not run automatically by `Pull All Live Data`, so both can take real time to catch up — that's expected, not a bug.
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
