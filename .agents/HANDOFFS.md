# Handoffs

Append one entry per finished task, newest at the bottom.

<!--
## T<id> - <short title>
- From: Claude | Codex
- Task: T<id>
- Files changed: ...
- Verification run: ...
- Result: pass | fail (details)
- Notes for next task / other agent: ...
-->

## T1 - Remove the LLM entirely
- From: Claude
- Task: T1
- Files changed: cricket_edge/llm.py (deleted), cricket_edge/agents.py, cricket_edge/config.py, .env.example
- Verification run: `grep -rni "ollama\|LocalLLMClient" cricket_edge .env.example` (clean); `python -m pytest tests/ -q` using the Python 3.13 interpreter at `/c/Users/Zacka/AppData/Local/Programs/Python/Python313/python.exe` (the `python` on PATH is a Python 3.7 store stub that can't even collect this codebase's modules)
- Result: pass — 75 passed
- Notes for next task / other agent: use the Python 3.13 interpreter path above for any verification command, not bare `python`/`pytest`. Moving on to T2 (agents.py -> pipeline.py rename).

## T7 - Update docs for decision pipeline and scheduler rename
- From: Codex
- Task: T7
- Files changed: README.md, docs/ARCHITECTURE.md, docs/ROADMAP.md, docs/BULLETPROOFING_CHECKLIST.md, .agents/TASKS.md, .agents/HANDOFFS.md
- Verification run: `rg -n -i "agent|autonomous|ollama|llm" README.md docs\ARCHITECTURE.md docs\ROADMAP.md docs\BULLETPROOFING_CHECKLIST.md` (clean); `rg -n "pipeline\.py|scheduler\.py|BackgroundScheduler|CRICKET_EDGE_SCHEDULER|decision pipeline|Decision Pipeline|scheduler" README.md docs\ARCHITECTURE.md docs\ROADMAP.md docs\BULLETPROOFING_CHECKLIST.md`
- Result: pass
- Notes for next task / other agent: Docs now describe the target `pipeline.py` / `scheduler.py` world and avoid AI-agent/LLM/autonomous framing. Historical dated docs were not touched.

## T2-T6 - Code/schema/UI/test renames
- From: Claude
- Task: T2, T3, T4, T5, T6
- Files changed: cricket_edge/agents.py (deleted) -> cricket_edge/pipeline.py; cricket_edge/autonomous_engine.py (deleted) -> cricket_edge/scheduler.py; cricket_edge/orchestrator.py; cricket_edge/database.py; cricket_edge/readiness.py; cricket_edge/advanced_models.py; cricket_edge/config.py; cricket_edge/server.py; cricket_edge/__init__.py; cricket_edge/web/templates/index.html; cricket_edge/web/static/app.js; tests/test_agents.py (deleted) -> tests/test_pipeline.py; tests/test_autonomous_engine.py (deleted) -> tests/test_scheduler.py; tests/test_model_governance.py; tests/test_backtesting_readiness.py; data/cricket_edge.sqlite3 (deleted, untracked demo db, rebuilt clean)
- Verification run: `pytest -q` after each task (75 passed throughout); manual boot check via `CricketEdgeOrchestrator().state()` confirming `scheduler` key present / `autonomous` key gone, readiness items renamed to `decision_log`/`scheduler_heartbeat`; ran `morning_run()` end-to-end and confirmed `decision_log.source` values are `bet_evaluator`/`risk_gate`/`briefing_writer`/`data_health_check`
- Result: pass
- Notes for next task / other agent: all renames from DECISIONS.md applied. Ready for T8.

## T8 - Final sweep + full test run
- From: Claude
- Task: T8
- Files changed: none (read-only verification)
- Verification run: `grep -rniE "agent|autonomous|ollama|llm" cricket_edge tests README.md docs/ARCHITECTURE.md docs/ROADMAP.md docs/BULLETPROOFING_CHECKLIST.md .env.example` (excluding vendored plotly.min.js) -> only 3 unrelated `User-Agent` HTTP headers remain; `pytest -q` -> 75 passed; manual `morning_run()` smoke test confirmed new pipeline/scheduler naming end-to-end
- Result: pass
- Notes for next task / other agent: all 8 tasks done. De-AI-agent rename complete.

## T9 - Model improvement plan
- From: Codex
- Task: T9
- Files changed: docs/MODEL_IMPROVEMENT_PLAN.md, .agents/TASKS.md, .agents/HANDOFFS.md
- Verification run: Read back `docs/MODEL_IMPROVEMENT_PLAN.md`; queried local SQLite model/backtest tables; reviewed `prediction.py`, `live_model.py`, `logistic_model.py`, `advanced_models.py`, `elo.py`, `backtesting.py`, `market.py`, and historical Week 2/3/4 result docs.
- Result: pass
- Notes for next task / other agent: Local `data/cricket_edge.sqlite3` currently has no Cricsheet rows, model runs, model predictions, backtest runs, or paper bets, so the plan treats reproducible evaluation and real-odds backtest coverage as the first priorities.

## T10 - Implement model evaluation foundation
- From: Codex
- Task: T10
- Files changed: scripts/evaluate_models.py, cricket_edge/readiness.py, cricket_edge/backtesting.py, tests/test_backtesting_readiness.py, tests/test_model_evaluation_report.py, .agents/TASKS.md, .agents/HANDOFFS.md
- Verification run: `py -3.13 -m pytest tests/test_backtesting_readiness.py tests/test_model_evaluation_report.py tests/test_market_backfill.py -q` -> 10 passed; `py -3.13 scripts/evaluate_models.py --help` -> CLI exposes report/build/train/market/backtest flags; current-DB `run_evaluation_pipeline(Database())` smoke -> no actions, 0 model runs, 4 warnings; `py -3.13 -m pytest -q` -> 79 passed.
- Result: pass
- Notes for next task / other agent: This implements the foundation slice and the optional single-command orchestration flags. The next logical slice is richer chronological feature ablations and stronger model candidates once the data/training pipeline is run against a populated Cricsheet archive.
## T11 - Webapp UI/UX upgrade plan
- From: Codex
- Task: T11
- Files changed: docs/UI_UX_UPGRADE_PLAN.md, .agents/TASKS.md, .agents/HANDOFFS.md
- Verification run: Read back `docs/UI_UX_UPGRADE_PLAN.md`; reviewed `cricket_edge/web/templates/index.html`, `cricket_edge/web/static/app.js`, `cricket_edge/web/static/styles.css`, `cricket_edge/server.py`, `cricket_edge/orchestrator.py`, `cricket_edge/charts.py`, and README dashboard docs.
- Result: pass
- Notes for next task / other agent: Recommended first implementation slice is frontend-only Phase 1: new Command/Opportunities/Research/Portfolio/Data Health IA, grouped readiness blockers, persistent action status banner, Research tabs, and basic table filters.

## T12 - Implement UI/UX phase 1
- From: Codex
- Task: T12
- Files changed: cricket_edge/web/templates/index.html, cricket_edge/web/static/app.js, cricket_edge/web/static/styles.css, .agents/TASKS.md, .agents/HANDOFFS.md
- Verification run: `node --check cricket_edge\web\static\app.js`; `rg -n "agentPipeline|autonomousBanner|autonomousDot|autonomousText|data\.autonomous|agent_name" cricket_edge\web`; `py -3.13 -m pytest -q`; `py -3.13 -c "from cricket_edge.orchestrator import CricketEdgeOrchestrator; s=CricketEdgeOrchestrator().state(); print(sorted(s.keys()))"`; temporary local server smoke for `/`, `/static/app.js`, `/static/styles.css`, and `/api/state` on `127.0.0.1:8765`.
- Result: pass - JS parsed cleanly; old frontend identifiers clean; 79 tests passed; state smoke returned scheduler/charts/readiness data; local HTTP smoke returned 200s for page, static assets, and API. Browser visual inspection was attempted but no in-app browser target was available in this session.
- Notes for next task / other agent: Phase 1 is frontend-only. The dashboard now uses Command, Opportunities, Research, Portfolio, and Data Health workspaces with grouped readiness blockers, persistent action status, Research tabs, and table filters. Next UI slice should add richer visual QA screenshots once a browser target is available.

## T13 - Industry-standard full-project audit and master plan
- From: Codex
- Task: T13
- Files changed: docs/INDUSTRY_STANDARD_MASTER_PLAN.md, .agents/TASKS.md, .agents/HANDOFFS.md
- Verification run: full source/schema/test/data-artifact/existing-plan audit; immutable read-only SQLite evidence query; `py -3.13 -m pytest -q` -> 79 passed; plan structure/coverage checks; `git diff --check` after removing the T13 trailing whitespace issue.
- Result: pass - created a 25-section, implementation-ready master plan covering immediate safety, canonical data, statistical modelling, rolling validation, calibration/uncertainty, odds and CLV, event-driven backtesting, staking/risk, paper execution, operations, software quality, dashboard, security, documentation, quantitative gates, phases, and task dependencies.
- Notes for next task / other agent: Start with SAFE-01, not a new model. Real fixtures currently fall back to `baseline_t20_elo_market_v1` when no trained artifact exists; the local DB has zero model runs but two open paper bets from that fallback, including an ODI stored as T20. Preserve those rows as invalid research evidence and make no-valid-active-model/unsupported-format fail closed before M1 or feature work.

## T14 - SAFE-01 fail-closed active-model gate
- From: Codex
- Task: T14
- Files changed: cricket_edge/live_model.py, cricket_edge/prediction.py, cricket_edge/risk.py, tests/test_pipeline.py, tests/test_real_odds_gate.py, .agents/TASKS.md, .agents/HANDOFFS.md
- Verification run: `py -3.13 -m pytest tests/test_real_odds_gate.py tests/test_pipeline.py tests/test_workflow.py -q` -> 21 passed; `py -3.13 -m pytest -q` -> 81 passed; `git diff --check`.
- Result: pass - real Bet365/The Odds API fixtures now require an active, calibrated, governed pre-toss model registry entry and valid coefficient run. Without one they generate blocked audit rows, stale fallback predictions are removed, and the risk gate records `no_valid_active_model` and prevents paper bets. Demo predictions are independently marked non-bettable.
- Notes for next task / other agent: SAFE-02 should enforce the T20-only model scope before model scoring or paper-bet evaluation. Existing local paper-bet rows are preserved as invalid historical evidence; do not reset the database without explicit user approval.

## T15 - Root webapp launcher
- From: Codex
- Task: T15
- Files changed: app.py, .agents/TASKS.md, .agents/HANDOFFS.md
- Verification run: `py -3.13 app.py --help`; import delegation smoke test; `git diff --check`.
- Result: pass - root `app.py` delegates to the established `cricket_edge.server.main` entrypoint, which starts the existing dashboard and configured background scheduler while retaining paper-only operation.
- Notes for next task / other agent: Run `py -3.13 app.py` from the project root; use `--host` and `--port` as needed. SAFE-02 remains the next safety work package.

## T16 - Full test-suite diagnosis
- From: Codex
- Task: T16
- Files changed: .agents/TASKS.md, .agents/HANDOFFS.md
- Verification run: `py -3.13 -m pytest -q` -> 81 passed; local checks for dashboard, state API, JavaScript, and CSS on port 8765; local listener/process inspection.
- Result: pass - full automated suite is green. No local server was reachable on port 8765 and no Python server process/listener was visible in this execution environment, so the reported browser errors could not be reproduced here.
- Notes for next task / other agent: Obtain the browser console error, network failure details, or a screenshot from the user before changing application code. SAFE-02 remains the next implementation package.

## T17 - In-dashboard user instructions
- From: Codex
- Task: T17
- Files changed: cricket_edge/web/templates/index.html, cricket_edge/web/static/app.js, cricket_edge/web/static/styles.css, .agents/TASKS.md, .agents/HANDOFFS.md
- Verification run: `node --check cricket_edge/web/static/app.js`; `py -3.13 -m pytest -q` -> 81 passed; `git diff --check`.
- Result: pass - added a Guide workspace with a safe daily workflow, paper-only safety rules, page reference, sidebar action explanations, and troubleshooting guidance. It uses the existing page navigation and responsive styles.
- Notes for next task / other agent: Browser visual inspection remains unavailable in this environment. The user needs a hard refresh after updating static files. SAFE-02 remains the next implementation package.

## T18 - End-to-end local system stabilization
- From: Codex
- Task: T18
- Files changed: requirements.txt, cricket_edge/orchestrator.py, tests/test_workflow.py, .agents/TASKS.md, .agents/HANDOFFS.md; generated local model evaluation reports under reports/.
- Verification run: installed Python 3.13 runtime and project virtual environment; `python scripts/evaluate_models.py --build-data --skip-download --train-models --run-backtest` -> imported 5,524 Cricsheet matches, trained and promoted `t20_logistic_pretoss_calibrated_v1`, no evaluation warnings; scheduler-enabled `app.py` dashboard and `/`, `/api/state`, JS, and CSS HTTP checks -> 200; in-app browser walkthrough of dashboard workspaces -> no console errors; `python -m pytest -q` -> 83 passed; `git diff --check` -> clean.
- Result: pass - added the Windows `tzdata` runtime dependency so ZoneInfo works locally; automatic scheduler odds refreshes now reuse fresh approved odds and honour the provider's HTTP 429 reset time, preventing repeated quota exhaustion. One clean local dashboard/scheduler instance is running at http://127.0.0.1:8765 in paper-only mode.
- Notes for next task / other agent: The readiness screen retains one intentional gap: no timestamp-valid historical market odds exist for a defensible strategy backtest. Do not invent or backfill synthetic odds merely to clear it. Current live provider rate-limit cooldown is handled safely by the scheduler; a deliberate manual "Fetch Live Odds" can still be used after the provider reset.

### T18 follow-up - paper recommendation ledger safety
- From: Codex
- Files changed: cricket_edge/model_scope.py, cricket_edge/market.py, cricket_edge/prediction.py, cricket_edge/risk.py, cricket_edge/paper_broker.py, cricket_edge/orchestrator.py, cricket_edge/web/static/app.js, tests/test_pipeline.py, tests/test_real_odds_gate.py.
- Verification run: fresh paper-only cycle; full `python -m pytest -q` -> 85 passed; JavaScript syntax check; local API state and settlement checks -> 200; in-app Portfolio view shows pending/open, voided, and result columns with no console errors.
- Result: pass - The T20 model now blocks ODI/Test/unknown-format fixtures, provider ingestion records the declared cricket format, and logically identical cross-provider fixtures cannot create duplicate open paper bets. Four out-of-scope ODI paper records were retained but automatically marked `voided` with GBP 0 P&L. Settlement waits for a real Cricsheet result before marking any remaining paper bet won/lost.
