# Live Odds Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add The Odds API as a second real bookmaker odds source and use it when the current Bet365/odds-api.io feed cannot provide fresh odds.

**Architecture:** Keep provider clients separate from market ingestion. The market layer will try odds-api.io Bet365 first, then call The Odds API when the primary feed returns no fresh insertions or reports provider errors. The risk gate will accept only approved fresh real sources: `bet365` and `the_odds_api`.

**Tech Stack:** Python 3.13, `httpx`, `pydantic`, `tenacity`, SQLite, stdlib dashboard server, pytest.

---

### Task 1: The Odds API Parser And Client

**Files:**
- Create: `cricket_edge/the_odds_api.py`
- Test: `tests/test_the_odds_api.py`

- [ ] Write tests for parsing cricket h2h odds into normalized match-winner outcomes.
- [ ] Verify tests fail because `cricket_edge.the_odds_api` does not exist.
- [ ] Implement typed schemas, HTTP client, raw-response archival, and parser helpers.
- [ ] Verify parser tests pass.

### Task 2: Fallback Market Ingestion

**Files:**
- Modify: `cricket_edge/config.py`
- Modify: `cricket_edge/data_sources.py`
- Modify: `cricket_edge/market.py`
- Test: `tests/test_market_odds_api_io.py`

- [ ] Write tests proving stale/empty primary odds can fall back to The Odds API cricket odds.
- [ ] Verify tests fail because fallback ingestion is absent.
- [ ] Add `THE_ODDS_API_KEY`, regions, markets, and sport keys to config.
- [ ] Add `FreeDataSources` methods for sports and odds endpoints.
- [ ] Insert The Odds API rows into `odds_snapshots` and `market_odds_snapshots` with source `the_odds_api`.
- [ ] Normalize no-vig probabilities and update market baselines after fallback.
- [ ] Verify fallback tests pass.

### Task 3: Risk Gate And Dashboard

**Files:**
- Modify: `cricket_edge/prediction.py`
- Modify: `cricket_edge/risk.py`
- Modify: `cricket_edge/orchestrator.py`
- Modify: `cricket_edge/server.py`
- Modify: `cricket_edge/web/templates/index.html`
- Modify: `cricket_edge/web/static/app.js`
- Test: `tests/test_real_odds_gate.py`

- [ ] Write tests proving fresh `the_odds_api` odds are bettable context and demo odds remain blocked.
- [ ] Verify tests fail while only `bet365` is accepted.
- [ ] Update accepted real source handling to include `the_odds_api`.
- [ ] Rename dashboard action copy to `Fetch Live Odds` while keeping the API route stable.
- [ ] Surface provider/fallback status in Week 4.
- [ ] Verify risk and workflow tests pass.

### Task 4: Docs, Sync, And Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] Document The Odds API setup and fallback behavior.
- [ ] Run full pytest suite in workspace.
- [ ] Sync source/docs/scripts/tests to `D:\SportsBettingProjects\cricket-edge` without copying `.env` or data.
- [ ] Run full pytest suite in D-drive project.
- [ ] Start or query the app and run the live odds fetch route.
