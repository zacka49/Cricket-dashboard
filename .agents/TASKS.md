# Task Queue

Status values: `todo`, `in_progress`, `done`. Claim a task by filling `owner` + `claimed_at` and setting status to `in_progress`. Only claim a task once every id in `depends_on` is `done`. Full rename table: `.agents/DECISIONS.md`.

## T1 â€” Remove the LLM entirely
- owner_recommendation: Claude
- owner: Claude
- claimed_at: 2026-07-12T00:00:00Z
- status: done
- depends_on: []
- files: cricket_edge/llm.py (delete), cricket_edge/agents.py, cricket_edge/config.py, .env.example
- goal: Delete llm.py and every Ollama/LLM call. BetDecisionAgent's `_llm_reason` method and `LocalLLMClient` import removed; `reason` comes only from `_fallback_reason(...)`. Remove `ollama_base_url`/`ollama_model` from Settings. Remove the two `OLLAMA_*` lines from `.env.example`.
- acceptance_criteria: No import of `llm.py` or `LocalLLMClient` remains anywhere in cricket_edge/. `grep -ri ollama cricket_edge .env.example` returns nothing.
- verification: `pytest tests/test_agents.py -k bet_decision`

## T2 â€” Rename agents.py -> pipeline.py + class renames
- owner_recommendation: Claude
- owner: Claude
- claimed_at: 2026-07-12T00:05:00Z
- status: done
- depends_on: [T1]
- files: cricket_edge/agents.py -> cricket_edge/pipeline.py, cricket_edge/orchestrator.py (imports only)
- goal: Rename the module and every class per DECISIONS.md (DataHealthCheck, BetEvaluator, RiskGate, PositionMonitor, BriefingWriter). Drop trading-firm role_title strings. Update orchestrator.py's import line and call sites to the new names.
- acceptance_criteria: `cricket_edge/agents.py` no longer exists; `cricket_edge/pipeline.py` exports the 5 renamed classes; orchestrator.py imports from `.pipeline`.
- verification: `python -c "import cricket_edge.pipeline"`

## T3 â€” Rename DB schema (agent_decisions/agent_name -> decision_log/source), delete local db
- owner_recommendation: Claude
- owner: Claude
- claimed_at: 2026-07-12T00:10:00Z
- status: done
- depends_on: [T2]
- files: cricket_edge/database.py, cricket_edge/pipeline.py, cricket_edge/orchestrator.py, cricket_edge/readiness.py, cricket_edge/advanced_models.py, data/cricket_edge.sqlite3 (delete)
- goal: Rename table `agent_decisions` -> `decision_log`, column `agent_name` -> `source`, table `autonomous_state` -> `scheduler_state` in the SCHEMA string, and every SQL statement referencing them across the listed files. Rename `MODEL_GOVERNANCE_AGENT_NAME` -> `MODEL_GOVERNANCE_NAME` (value `"model_governance"`) in advanced_models.py. Delete the untracked local sqlite3 file so init_schema() rebuilds clean.
- acceptance_criteria: `grep -rn "agent_decisions\|agent_name" cricket_edge/` returns nothing (except historical docs, which T3 does not touch).
- verification: `pytest tests/` (expect failures only in not-yet-updated test files â€” that's T6/T7's job)

## T4 â€” Rename autonomous_engine.py -> scheduler.py + settings/env renames
- owner_recommendation: Claude
- owner: Claude
- claimed_at: 2026-07-12T00:15:00Z
- status: done
- depends_on: [T3]
- files: cricket_edge/autonomous_engine.py -> cricket_edge/scheduler.py, cricket_edge/config.py, cricket_edge/server.py, cricket_edge/readiness.py, cricket_edge/orchestrator.py
- goal: Rename module, `AutonomousEngine` -> `BackgroundScheduler`, `start_background_engine` -> `start_scheduler`. Rename the 4 `autonomous_*` Settings fields + their env var names per DECISIONS.md. Update server.py's import. Update readiness.py's `_autonomous_engine_alive` -> `_scheduler_alive` reading `scheduler_state`. Update orchestrator.py's `_autonomous_state` -> `_scheduler_state`, and the `build_state()` dict key `"autonomous"` -> `"scheduler"`.
- acceptance_criteria: `cricket_edge/autonomous_engine.py` no longer exists; `grep -rn "autonomous" cricket_edge/*.py` returns nothing.
- verification: `python -m cricket_edge` boots, `/api/state` has a `scheduler` key (not `autonomous`)

## T5 â€” Update dashboard UI
- owner_recommendation: Claude
- owner: Claude
- claimed_at: 2026-07-12T00:20:00Z
- status: done
- depends_on: [T3, T4]
- files: cricket_edge/web/templates/index.html, cricket_edge/web/static/app.js
- goal: Apply the UI renames in DECISIONS.md â€” copy, element ids, `PIPELINE_STAGES`, `data.autonomous` -> `data.scheduler`, `decision.agent_name` -> `decision.source`, function name renames.
- acceptance_criteria: `grep -rniE "agent|autonomous" cricket_edge/web/` returns nothing.
- verification: manual â€” load the dashboard, confirm the Decision Pipeline panel and scheduler banner render.

## T6 â€” Rename/update tests
- owner_recommendation: Claude
- owner: Claude
- claimed_at: 2026-07-12T00:25:00Z
- status: done
- depends_on: [T2, T3, T4]
- files: tests/test_agents.py -> tests/test_pipeline.py, tests/test_autonomous_engine.py -> tests/test_scheduler.py, tests/test_model_governance.py, tests/test_backtesting_readiness.py
- goal: Update every reference per DECISIONS.md (imports, class names, table/column names, agent_name string literals -> new source names).
- acceptance_criteria: `pytest` passes with zero failures.
- verification: `pytest -q`

## T7 â€” Update docs (README, ARCHITECTURE, ROADMAP, BULLETPROOFING_CHECKLIST)
- owner_recommendation: Codex
- owner: Codex
- claimed_at: 2026-07-12T18:41:02+01:00
- status: done
- depends_on: []
- files: README.md, docs/ARCHITECTURE.md, docs/ROADMAP.md, docs/BULLETPROOFING_CHECKLIST.md
- goal: Apply the doc rewrites described in the "Docs scope (Codex / T7)" section of .agents/DECISIONS.md. Do not touch WEEK*_RESULTS.md, SESSION_2026-07-09_SUMMARY.md, or docs/superpowers/plans/* â€” those are historical and intentionally left alone.
- acceptance_criteria: `grep -rniE "agent|autonomous|ollama|llm" README.md docs/ARCHITECTURE.md docs/ROADMAP.md docs/BULLETPROOFING_CHECKLIST.md` returns nothing unintended (the doc prose itself should read with no AI-agent/LLM framing).
- verification: read the four files back and confirm they describe the renamed pipeline.py/scheduler.py world (per DECISIONS.md), not the old agents.py/autonomous_engine.py world.
- note: no file overlap with T1-T6, can start immediately, does not need to wait on Claude.

## T8 â€” Final sweep + full test run
- owner_recommendation: either (Claude will do this once T1-T7 all show done)
- owner: Claude
- claimed_at: 2026-07-12T00:30:00Z
- status: done
- depends_on: [T1, T2, T3, T4, T5, T6, T7]
- files: whole repo (read-only sweep)
- goal: `grep -rniE "agent|autonomous|ollama|llm" cricket_edge tests README.md docs/ARCHITECTURE.md docs/ROADMAP.md docs/BULLETPROOFING_CHECKLIST.md` and confirm only intentional leftovers remain (e.g. `User-Agent` HTTP headers). Run `pytest -q` for a clean pass. Report any gaps back in HANDOFFS.md.
- acceptance_criteria: pytest green; grep sweep clean.
- verification: as above.

## T9 â€” Model improvement plan
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

## T11 - Webapp UI/UX upgrade plan
- owner_recommendation: Codex
- owner: Codex
- claimed_at: 2026-07-12T20:05:00+01:00
- status: done
- depends_on: [T10]
- files: docs/UI_UX_UPGRADE_PLAN.md, .agents/TASKS.md, .agents/HANDOFFS.md
- goal: Inspect the current dashboard UI and write a Markdown plan for improving webapp UX without changing code yet.
- acceptance_criteria: Plan summarizes current UI structure, core UX issues, target information architecture, prioritized implementation phases, and verification steps.
- verification: Read back the plan and confirm it is grounded in current web templates/static JS/CSS and dashboard API surfaces.
## T12 - Implement UI/UX phase 1
- owner_recommendation: Codex
- owner: Codex
- claimed_at: 2026-07-12T20:20:00+01:00
- status: done
- depends_on: [T11]
- files: cricket_edge/web/templates/index.html, cricket_edge/web/static/app.js, cricket_edge/web/static/styles.css, .agents/TASKS.md, .agents/HANDOFFS.md
- goal: Implement Phase 1 of docs/UI_UX_UPGRADE_PLAN.md with frontend-only changes: new information architecture, grouped readiness blockers, persistent action status, Research tabs, and basic table filters.
- acceptance_criteria: Dashboard uses Command/Opportunities/Research/Portfolio/Data Health pages; action feedback is persistent; existing actions/charts still work; no backend API change is required.
- verification: Run pytest, import/state smoke test, and local dashboard smoke check if possible.

## T13 - Industry-standard full-project audit and master plan
- owner_recommendation: Codex
- owner: Codex
- claimed_at: 2026-07-13T22:51:22+01:00
- status: done
- depends_on: [T12]
- files: docs/INDUSTRY_STANDARD_MASTER_PLAN.md, .agents/TASKS.md, .agents/HANDOFFS.md
- goal: Audit the complete Cricket Edge repository and existing future plans, then produce a deeply detailed, implementation-ready roadmap that raises the project to professional sports-betting research standards, with statistical modelling and data science as the primary focus.
- acceptance_criteria: The plan is grounded in current code and data artifacts; covers data, modelling, validation, odds/market intelligence, backtesting, staking/risk, paper execution, monitoring, software quality, security, operations, dashboard, documentation, and portfolio presentation; defines priorities, dependencies, deliverables, tests, quantitative gates, and a sequenced task backlog.
- verification: Read back the plan, cross-check every major subsystem against the repository inventory, verify internal links/headings, and run the existing test suite as a baseline health check.

## T14 - SAFE-01 fail-closed active-model gate
- owner_recommendation: Codex
- owner: Codex
- claimed_at: 2026-07-13T23:14:30+01:00
- status: done
- depends_on: [T13]
- files: cricket_edge/live_model.py, cricket_edge/prediction.py, cricket_edge/risk.py, tests/test_pipeline.py, tests/test_real_odds_gate.py, tests/test_workflow.py, .agents/TASKS.md, .agents/HANDOFFS.md
- goal: Prevent real fixtures from falling back to demo/baseline predictions when no valid active trained model exists, and make the betting workflow record an explicit non-bet reason instead.
- acceptance_criteria: A real fixture without an active governed model run cannot create a paper bet; its risk decision is skipped with `no_valid_active_model`; demo predictions are independently marked non-bettable; an active governed snapshot remains eligible for the normal live workflow.
- verification: Focused prediction/risk/workflow tests plus the full pytest suite.

## T15 - Root webapp launcher
- owner_recommendation: Codex
- owner: Codex
- claimed_at: 2026-07-13T23:32:47+01:00
- status: done
- depends_on: [T14]
- files: app.py, .agents/TASKS.md, .agents/HANDOFFS.md
- goal: Add a root-level `app.py` that launches the existing dashboard server and background scheduler through the supported server entrypoint.
- acceptance_criteria: `py -3.13 app.py --help` exposes the existing host/port options; running `py -3.13 app.py` delegates to `cricket_edge.server.main`, retaining paper-only and scheduler behavior.
- verification: CLI help and import smoke test.

## T16 - Full test-suite diagnosis
- owner_recommendation: Codex
- owner: Codex
- claimed_at: 2026-07-13T23:47:31+01:00
- status: done
- depends_on: [T15]
- files: .agents/TASKS.md, .agents/HANDOFFS.md
- goal: Run the complete automated suite and report whether its results explain the user-observed dashboard loading/errors.
- acceptance_criteria: Full pytest result and concise diagnosis are recorded; no application files change unless the user separately authorizes a fix.
- verification: `py -3.13 -m pytest -q`.

## T17 - In-dashboard user instructions
- owner_recommendation: Codex
- owner: Codex
- claimed_at: 2026-07-13T23:54:49+01:00
- status: done
- depends_on: [T16]
- files: cricket_edge/web/templates/index.html, cricket_edge/web/static/app.js, cricket_edge/web/static/styles.css, .agents/TASKS.md, .agents/HANDOFFS.md
- goal: Add a concise, accessible dashboard guide covering the paper-only workflow, workspace purpose, action buttons, readiness blocks, and next steps.
- acceptance_criteria: Users can open a dedicated guide from the dashboard, read a plain-language safe workflow and page/action explanations, and close it without affecting existing dashboard actions.
- verification: JavaScript syntax check, server/static smoke check, and pytest.

## T18 - End-to-end local system stabilization
- owner_recommendation: Codex
- owner: Codex
- claimed_at: 2026-07-15T12:00:00+01:00
- status: done
- depends_on: [T17]
- files: whole repo (targeted fixes and verification only)
- goal: Restore a runnable local Python environment, fix reproducible automated-test and safe dashboard/workflow defects, then verify the scheduler-enabled paper-only system end to end.
- acceptance_criteria: Full pytest suite is green; launcher and state route work; dashboard pages render without console errors; workflow gates fail closed when data/model requirements are unmet.
- verification: focused regression tests, full pytest, scheduler-enabled local server/API smoke, browser dashboard walkthrough, and local Cricsheet/model bootstrap.
