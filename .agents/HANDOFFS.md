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
