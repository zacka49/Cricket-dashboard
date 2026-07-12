# Decisions: De-AI-agent rename

Goal: strip the "AI agent" / autonomous-trading-firm framing from Cricket Edge. Keep every capability (predictions vs market odds, edge detection, risk rules, paper-trading simulation, cash-out/settlement, model governance/retraining, background scheduling, dashboard). Remove the local LLM (Ollama) dependency entirely. Rename the "agent" classes to plain engineering names, drop the trading-firm org-chart titles (no "Chief Risk Officer" / "COO" / "Head of Quant Research"). Keep the background scheduler, just renamed away from "autonomous engine".

Full plan: `C:\Users\Zacka\.claude\plans\quiet-coalescing-sunrise.md` (Claude's machine; Codex should treat this file as the source of truth instead).

## Rename table (old -> new)

### Modules
- `cricket_edge/agents.py` -> `cricket_edge/pipeline.py`
- `cricket_edge/autonomous_engine.py` -> `cricket_edge/scheduler.py`
- `cricket_edge/llm.py` -> deleted

### Classes / names (in `pipeline.py`)
- `DataStewardAgent` -> `DataHealthCheck` (name `"data_health_check"`, drop role_title "Chief Data Officer")
- `BetDecisionAgent` -> `BetEvaluator` (name `"bet_evaluator"`, role label "Bet Evaluation"); `_llm_reason`/`LocalLLMClient` removed, reason always from `_fallback_reason(...)`
- `PortfolioOversightAgent` -> `RiskGate` (name `"risk_gate"`, role label "Risk Gate")
- `MarketWatchAgent` -> `PositionMonitor` (name `"position_monitor"`, role label "Position Monitoring")
- `ReportWriterAgent` -> `BriefingWriter` (name `"briefing_writer"`, role label "Daily Briefing")

### advanced_models.py
- `MODEL_GOVERNANCE_AGENT_NAME = "model_governance_agent"` -> `MODEL_GOVERNANCE_NAME = "model_governance"`

### scheduler.py (was autonomous_engine.py)
- `AutonomousEngine` -> `BackgroundScheduler`
- `start_background_engine()` -> `start_scheduler()`

### Database schema (database.py SCHEMA)
- table `agent_decisions` -> `decision_log`
- column `agent_name` -> `source`
- table `autonomous_state` -> `scheduler_state`

### Settings (config.py) / env vars
- `ollama_base_url`, `ollama_model` -> removed entirely
- `autonomous_enabled` -> `scheduler_enabled` (env `CRICKET_EDGE_AUTONOMOUS_ENABLED` -> `CRICKET_EDGE_SCHEDULER_ENABLED`)
- `autonomous_tick_seconds` -> `scheduler_tick_seconds` (env `CRICKET_EDGE_AUTONOMOUS_TICK_SECONDS` -> `CRICKET_EDGE_SCHEDULER_TICK_SECONDS`)
- `autonomous_retrain_interval_hours` -> `scheduler_retrain_interval_hours` (env `CRICKET_EDGE_AUTONOMOUS_RETRAIN_INTERVAL_HOURS` -> `CRICKET_EDGE_SCHEDULER_RETRAIN_INTERVAL_HOURS`)
- `autonomous_retrain_new_match_threshold` -> `scheduler_retrain_new_match_threshold` (env `CRICKET_EDGE_AUTONOMOUS_RETRAIN_NEW_MATCH_THRESHOLD` -> `CRICKET_EDGE_SCHEDULER_RETRAIN_NEW_MATCH_THRESHOLD`)
- `.env.example`: `OLLAMA_*` lines deleted

### orchestrator.py
- imports switch `.agents` -> `.pipeline`, new class names
- `_autonomous_state()` -> `_scheduler_state()`; `build_state()` key `"autonomous"` -> `"scheduler"`

### readiness.py
- item key `"agent_audit_log"` -> `"decision_log"`, label "Agent audit trail" -> "Decision audit trail"
- item key `"autonomous_engine"` -> `"scheduler_heartbeat"`, label "Autonomous engine heartbeat" -> "Background scheduler heartbeat"
- `_autonomous_engine_alive()` -> `_scheduler_alive()`, reads `scheduler_state`

### server.py
- `from .autonomous_engine import start_background_engine` -> `from .scheduler import start_scheduler`

### Dashboard UI (web/templates/index.html, web/static/app.js)
- Copy: "Autonomous paper betting research" -> "Cricket betting research & paper trading"; "Agentic workflow" -> "Decision workflow"; "Agent Pipeline" -> "Decision Pipeline"; "Agent Notes" -> "Decision Notes"; "Recent Agent Decisions" -> "Recent Decisions"
- IDs: `agentPipeline` -> `decisionPipeline`; `autonomousBanner`/`autonomousDot`/`autonomousText` -> `schedulerBanner`/`schedulerDot`/`schedulerText`
- `app.js`: `PIPELINE_STAGES` keys/labels match new names above, drop "optionally asks a local LLM" phrase; `renderAgentPipeline` -> `renderDecisionPipeline`; `renderAutonomousBanner` -> `renderSchedulerBanner`; `latestByAgent` -> `latestBySource`; `decision.agent_name` -> `decision.source`; `data.autonomous` -> `data.scheduler`

### Tests
- `tests/test_agents.py` -> `tests/test_pipeline.py`
- `tests/test_autonomous_engine.py` -> `tests/test_scheduler.py`
- `tests/test_model_governance.py`, `tests/test_backtesting_readiness.py` updated in place for the renamed tables/columns/keys

### Local DB
- `data/cricket_edge.sqlite3` is NOT git-tracked. Delete it so `init_schema()` recreates it under the new schema (no migration needed).

## Docs scope (Codex / T7)

- **README.md**: rewrite intro paragraph (drop "autonomous... styled after how a small trading firm is organized" framing and the "local LLM agents interpret model output" bullet); rename "Autonomous Operation" section -> "Background Scheduler" with the new env var names above; delete "Local LLMs" section entirely; update "Project Layout" file comments (`agents.py`->`pipeline.py`, `autonomous_engine.py`->`scheduler.py`, drop `llm.py` line); reword "Dashboard Buttons" copy that says "lets agents review candidates" / "decision agent"
- **docs/ARCHITECTURE.md**: replace "Why LLMs Are Not The Prediction Model" section with a short "Why Predictions Are Rule-Based" note (no LLM exists anymore); rename "Agent Responsibilities" -> "Decision Pipeline Steps" with the renamed classes/responsibilities above and no LLM line; reword "Broker Boundary" paragraph to say "decision pipeline" instead of "agents"
- **docs/ROADMAP.md**: rename Phase 4 "Stronger Agents" -> "Stronger Decision Rules"; reword bullets ("Backtest Critic Agent" -> "Automated backtest critique checks", "Feature Engineer Agent" -> "Automated feature-engineering pipeline", "Risk Agent with correlated exposure checks" -> "Correlated-exposure risk checks"); drop "LLM prompt/version tracking" bullet
- **docs/BULLETPROOFING_CHECKLIST.md**: rename "Agent Safety" -> "Decision Pipeline Safety"; reword bullets ("Agents consume structured data only" -> "Each pipeline step consumes structured data only", etc.); drop "Agent prompts are versioned"; rename "Backtest Critic Agent"/"Risk Agent"/"Market Watch Agent" bullets to plain terms
- Do NOT touch `docs/WEEK1_RESULTS.md` ... `WEEK4_RESULTS.md`, `docs/SESSION_2026-07-09_SUMMARY.md`, `docs/superpowers/plans/*` — dated historical run logs, intentionally left alone.
- Note: the renamed module/file names above (`pipeline.py`, `scheduler.py`) will exist by the time you read this if Claude has finished T2/T4; if not yet, still write docs against the *target* names in this file, not the current `agents.py`/`autonomous_engine.py` names — Claude's code changes and your docs changes will land together.
