# Task Queue

Status values: `todo`, `in_progress`, `done`. Claim a task by filling `owner` + `claimed_at` and setting status to `in_progress`. Only claim a task once every id in `depends_on` is `done`. Full rename table: `.agents/DECISIONS.md`.

## T1 — Remove the LLM entirely
- owner_recommendation: Claude
- owner: Claude
- claimed_at: 2026-07-12T00:00:00Z
- status: done
- depends_on: []
- files: cricket_edge/llm.py (delete), cricket_edge/agents.py, cricket_edge/config.py, .env.example
- goal: Delete llm.py and every Ollama/LLM call. BetDecisionAgent's `_llm_reason` method and `LocalLLMClient` import removed; `reason` comes only from `_fallback_reason(...)`. Remove `ollama_base_url`/`ollama_model` from Settings. Remove the two `OLLAMA_*` lines from `.env.example`.
- acceptance_criteria: No import of `llm.py` or `LocalLLMClient` remains anywhere in cricket_edge/. `grep -ri ollama cricket_edge .env.example` returns nothing.
- verification: `pytest tests/test_agents.py -k bet_decision`

## T2 — Rename agents.py -> pipeline.py + class renames
- owner_recommendation: Claude
- owner: Claude
- claimed_at: 2026-07-12T00:05:00Z
- status: done
- depends_on: [T1]
- files: cricket_edge/agents.py -> cricket_edge/pipeline.py, cricket_edge/orchestrator.py (imports only)
- goal: Rename the module and every class per DECISIONS.md (DataHealthCheck, BetEvaluator, RiskGate, PositionMonitor, BriefingWriter). Drop trading-firm role_title strings. Update orchestrator.py's import line and call sites to the new names.
- acceptance_criteria: `cricket_edge/agents.py` no longer exists; `cricket_edge/pipeline.py` exports the 5 renamed classes; orchestrator.py imports from `.pipeline`.
- verification: `python -c "import cricket_edge.pipeline"`

## T3 — Rename DB schema (agent_decisions/agent_name -> decision_log/source), delete local db
- owner_recommendation: Claude
- owner: Claude
- claimed_at: 2026-07-12T00:10:00Z
- status: done
- depends_on: [T2]
- files: cricket_edge/database.py, cricket_edge/pipeline.py, cricket_edge/orchestrator.py, cricket_edge/readiness.py, cricket_edge/advanced_models.py, data/cricket_edge.sqlite3 (delete)
- goal: Rename table `agent_decisions` -> `decision_log`, column `agent_name` -> `source`, table `autonomous_state` -> `scheduler_state` in the SCHEMA string, and every SQL statement referencing them across the listed files. Rename `MODEL_GOVERNANCE_AGENT_NAME` -> `MODEL_GOVERNANCE_NAME` (value `"model_governance"`) in advanced_models.py. Delete the untracked local sqlite3 file so init_schema() rebuilds clean.
- acceptance_criteria: `grep -rn "agent_decisions\|agent_name" cricket_edge/` returns nothing (except historical docs, which T3 does not touch).
- verification: `pytest tests/` (expect failures only in not-yet-updated test files — that's T6/T7's job)

## T4 — Rename autonomous_engine.py -> scheduler.py + settings/env renames
- owner_recommendation: Claude
- owner: Claude
- claimed_at: 2026-07-12T00:15:00Z
- status: done
- depends_on: [T3]
- files: cricket_edge/autonomous_engine.py -> cricket_edge/scheduler.py, cricket_edge/config.py, cricket_edge/server.py, cricket_edge/readiness.py, cricket_edge/orchestrator.py
- goal: Rename module, `AutonomousEngine` -> `BackgroundScheduler`, `start_background_engine` -> `start_scheduler`. Rename the 4 `autonomous_*` Settings fields + their env var names per DECISIONS.md. Update server.py's import. Update readiness.py's `_autonomous_engine_alive` -> `_scheduler_alive` reading `scheduler_state`. Update orchestrator.py's `_autonomous_state` -> `_scheduler_state`, and the `build_state()` dict key `"autonomous"` -> `"scheduler"`.
- acceptance_criteria: `cricket_edge/autonomous_engine.py` no longer exists; `grep -rn "autonomous" cricket_edge/*.py` returns nothing.
- verification: `python -m cricket_edge` boots, `/api/state` has a `scheduler` key (not `autonomous`)

## T5 — Update dashboard UI
- owner_recommendation: Claude
- owner: Claude
- claimed_at: 2026-07-12T00:20:00Z
- status: done
- depends_on: [T3, T4]
- files: cricket_edge/web/templates/index.html, cricket_edge/web/static/app.js
- goal: Apply the UI renames in DECISIONS.md — copy, element ids, `PIPELINE_STAGES`, `data.autonomous` -> `data.scheduler`, `decision.agent_name` -> `decision.source`, function name renames.
- acceptance_criteria: `grep -rniE "agent|autonomous" cricket_edge/web/` returns nothing.
- verification: manual — load the dashboard, confirm the Decision Pipeline panel and scheduler banner render.

## T6 — Rename/update tests
- owner_recommendation: Claude
- owner: Claude
- claimed_at: 2026-07-12T00:25:00Z
- status: done
- depends_on: [T2, T3, T4]
- files: tests/test_agents.py -> tests/test_pipeline.py, tests/test_autonomous_engine.py -> tests/test_scheduler.py, tests/test_model_governance.py, tests/test_backtesting_readiness.py
- goal: Update every reference per DECISIONS.md (imports, class names, table/column names, agent_name string literals -> new source names).
- acceptance_criteria: `pytest` passes with zero failures.
- verification: `pytest -q`

## T7 — Update docs (README, ARCHITECTURE, ROADMAP, BULLETPROOFING_CHECKLIST)
- owner_recommendation: Codex
- owner: Codex
- claimed_at: 2026-07-12T18:41:02+01:00
- status: done
- depends_on: []
- files: README.md, docs/ARCHITECTURE.md, docs/ROADMAP.md, docs/BULLETPROOFING_CHECKLIST.md
- goal: Apply the doc rewrites described in the "Docs scope (Codex / T7)" section of .agents/DECISIONS.md. Do not touch WEEK*_RESULTS.md, SESSION_2026-07-09_SUMMARY.md, or docs/superpowers/plans/* — those are historical and intentionally left alone.
- acceptance_criteria: `grep -rniE "agent|autonomous|ollama|llm" README.md docs/ARCHITECTURE.md docs/ROADMAP.md docs/BULLETPROOFING_CHECKLIST.md` returns nothing unintended (the doc prose itself should read with no AI-agent/LLM framing).
- verification: read the four files back and confirm they describe the renamed pipeline.py/scheduler.py world (per DECISIONS.md), not the old agents.py/autonomous_engine.py world.
- note: no file overlap with T1-T6, can start immediately, does not need to wait on Claude.

## T8 — Final sweep + full test run
- owner_recommendation: either (Claude will do this once T1-T7 all show done)
- owner: Claude
- claimed_at: 2026-07-12T00:30:00Z
- status: done
- depends_on: [T1, T2, T3, T4, T5, T6, T7]
- files: whole repo (read-only sweep)
- goal: `grep -rniE "agent|autonomous|ollama|llm" cricket_edge tests README.md docs/ARCHITECTURE.md docs/ROADMAP.md docs/BULLETPROOFING_CHECKLIST.md` and confirm only intentional leftovers remain (e.g. `User-Agent` HTTP headers). Run `pytest -q` for a clean pass. Report any gaps back in HANDOFFS.md.
- acceptance_criteria: pytest green; grep sweep clean.
- verification: as above.

## T9 — Model improvement plan
- owner_recommendation: Codex
- owner: Codex
- claimed_at: 2026-07-12T18:55:00+01:00
- status: done
- depends_on: [T8]
- files: docs/MODEL_IMPROVEMENT_PLAN.md, .agents/TASKS.md, .agents/HANDOFFS.md
- goal: Inspect the current prediction/modeling code and available performance artifacts, then write a Markdown plan for improving cricket betting model quality and evaluation.
- acceptance_criteria: New plan summarizes current model stack, known/measurable performance, gaps, and prioritized improvement roadmap.
- verification: Read back the plan and confirm it is grounded in current repo code and available test/evaluation outputs.

## T10 - Implement model evaluation foundation
- owner_recommendation: Codex
- owner: Codex
- claimed_at: 2026-07-12T19:15:00+01:00
- status: done
- depends_on: [T9]
- files: scripts/evaluate_models.py, cricket_edge/readiness.py, cricket_edge/backtesting.py, tests/test_backtesting_readiness.py, tests/test_model_evaluation_report.py, .agents/TASKS.md, .agents/HANDOFFS.md
- goal: Implement the first slice of docs/MODEL_IMPROVEMENT_PLAN.md: reproducible evaluation/report export, model-readiness warnings, and richer real-odds backtest reporting.
- acceptance_criteria: A script can emit JSON/Markdown model evaluation reports; readiness flags empty model state; backtests include sample-size/CLV/source/confidence breakdowns while remaining timestamp-safe.
- verification: Focused pytest for readiness/backtesting/evaluation report plus import smoke test for the script.
