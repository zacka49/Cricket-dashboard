# UI/UX Upgrade Plan

Generated: 2026-07-12

## Goal

Upgrade Cricket Edge from a functional local dashboard into a clearer operational research workstation. The UI should help a user answer four questions quickly:

1. Is the system safe to run right now?
2. Do we have fresh real odds, usable model predictions, and enough data quality?
3. Which model edges are actionable, blocked, or only demo context?
4. How are paper bets, CLV, backtests, and model health trending?

The app must remain paper-only, local-first, and fail-closed. The UX should make uncertainty, missing data, stale odds, and demo-only states more visible rather than more polished-looking.

## Current UI Snapshot

Current frontend files:

- `cricket_edge/web/templates/index.html`: static four-page dashboard shell.
- `cricket_edge/web/static/app.js`: client-side rendering, page switching, workflow actions, tables, Plotly rendering.
- `cricket_edge/web/static/styles.css`: custom CSS with sidebar layout, cards, tables, pipeline, badges, and responsive rules.
- `cricket_edge/server.py`: standard-library HTTP server exposing `/`, `/api/state`, static assets, and POST action endpoints.

Current pages:

| Page | Current purpose | Main components |
|---|---|---|
| Trading Floor | Overview and operating state | Bankroll metrics, system description, decision pipeline, briefing, readiness checklist |
| Quant Research | Model training and validation | Training buttons, training data summary, model comparison, calibration, registry, feature importance, Elo ratings, backtest |
| Positions | Paper execution track record | Match/prediction table, paper bets, decisions, equity curve, CLV |
| Ops & Compliance | Data and audit trail | Odds feed status, odds source counts, recent odds, event log |

Current strengths:

- Clear paper-only framing.
- Useful separation between overview, model research, positions, and data operations.
- Good core data already reaches `/api/state`: account, fixtures, predictions, decisions, paper bets, events, week reports, backtesting, readiness, scheduler, charts.
- Plotly charts are vendored locally and rendered only on relevant pages.
- Actions are already grouped between global workflow actions and model-training actions.

Current UX problems:

- The sidebar action stack is powerful but risky: all destructive/expensive/long-running actions look similar except `Reset Demo`.
- Action feedback is shallow: a failed/successful POST mostly reloads state or alerts, with no persistent status, duration, output summary, or next step.
- Empty states are explanatory but scattered; there is no single top-level "what blocks paper betting today" surface.
- Readiness is useful but buried in a table with equal visual weight for critical and low-priority items.
- The dashboard is table-heavy; key risks and opportunities require scanning several panels.
- The match table mixes model output, market context, data quality, and bet actionability without clear row-level priority.
- Quant Research contains both dangerous commands and interpretive evidence; retraining controls should be separated from model evaluation views.
- Ops & Compliance is a catch-all and should become a data-quality command center.
- Mobile layout works structurally, but the sidebar becomes a large action block before the user reaches content.
- No keyboard/accessibility pass is documented: focus states, ARIA labels, status regions, reduced motion, and color contrast should be verified.

## Product Principles

1. Safety before action: show blockers and stale data before buttons.
2. Explain status with evidence: every "pass/watch/gap" should link mentally to the row, chart, or event causing it.
3. Separate command from evidence: buttons that mutate state should live in command bars, not compete with analytical panels.
4. Optimize for repeated operations: dense, scannable, predictable layouts beat marketing-style hero sections.
5. Make demo vs real unmistakable: demo fixtures and demo odds must be visibly non-bettable.
6. Keep paper-only visible: real-money capability should not be implied anywhere.
7. Use progressive disclosure: top-level pages show what matters now; details live in drawers/tabs/tables.

## Target Information Architecture

Replace the current four pages with five clearer workspaces, while reusing most existing data and routes.

| Target workspace | Purpose | Current source |
|---|---|---|
| Command Center | Today status, blockers, recommended next action, latest workflow result | Trading Floor + readiness + scheduler + events |
| Opportunities | Fixtures, predictions, odds freshness, edge, confidence, decision outcome | Positions match table + decisions |
| Research Lab | Model comparison, calibration, feature importance, backtest, model registry | Quant Research |
| Portfolio | Paper bets, exposure, equity curve, CLV, settlement status | Positions |
| Data Health | Odds feed, Cricsheet/model data coverage, event log, diagnostics | Ops & Compliance + readiness |

Navigation labels should be short and operational:

- `Command`
- `Opportunities`
- `Research`
- `Portfolio`
- `Data Health`

## Page-Level Plan

### 1. Command Center

Purpose: one screen that tells the user what is safe, blocked, and worth doing next.

Layout:

- Top status strip: paper mode, scheduler status, odds freshness, active model, last update.
- Primary KPI row: bankroll, open exposure, open bets, latest backtest sample size/CLV if available.
- "Can we place paper bets?" gate panel with grouped blockers:
  - no active model
  - no fresh real odds
  - model predictions missing/stale
  - risk exposure cap
  - demo-only fixture context
- Latest workflow result panel: last action run, duration, ok/error, rows affected, next suggested action.
- Decision pipeline as a compact vertical checklist, not a long horizontal scroller.
- Daily briefing below blockers, with each line tagged as `model`, `odds`, `risk`, or `portfolio` where possible.

Needed frontend changes:

- Add a `renderCommandCenter` function.
- Rework readiness rendering into severity groups: `critical gaps`, `watch`, `passes`.
- Add an action-result toast/status region instead of `alert()` only.

Optional backend support:

- Include `last_action` in `/api/state` or persist action summaries in `events` with structured payloads.

### 2. Opportunities

Purpose: make the bet candidate review faster and safer.

Layout:

- Filter bar: market source, odds freshness, model source, edge bucket, confidence bucket, competition, status.
- Candidate table with sticky header and row density controls.
- Row grouping:
  - `Actionable paper candidates`
  - `Blocked by data/risk`
  - `Demo/context only`
- Row columns:
  - match/start/competition
  - source/freshness
  - model selection/probability/fair odds
  - market odds/edge
  - confidence/data coverage
  - latest decision/reason
- Expandable row detail for feature source, market captured time, raw skip reasons, and matching diagnostics.

Needed frontend changes:

- Replace `renderMatches` with a row model that joins fixture, prediction, latest decision, and market status.
- Add lightweight client-side filters and sort state.
- Add badges for `fresh real odds`, `stale`, `no odds`, `demo`, `trained model`, `thin history`.

Optional backend support:

- Add a candidate summary endpoint or enrich `/api/state` with denormalized candidate rows to reduce client joining.

### 3. Research Lab

Purpose: separate model evidence from model commands.

Layout:

- Header summary: active model, last trained, training rows, test Brier/log loss, ECE, backtest sample warning.
- Tabs inside Research:
  - `Models`: comparison and registry.
  - `Calibration`: reliability chart and bucket table.
  - `Backtest`: P&L, edge buckets, source/confidence/CLV breakdowns.
  - `Features`: coefficients/stump features and missingness warnings.
- Command drawer or secondary toolbar for retrain actions:
  - Train Elo
  - Train Logistic
  - Force Retrain Now
  - Rebuild Market Data
- Each command should show estimated cost/risk and latest run status.

Needed frontend changes:

- Add local tab state for Research content.
- Render new backtest fields from T10: `avg_clv`, `positive_clv_rate`, `sample_warning`, `by_source`, `by_confidence_bucket`, `by_closing_line_result`.
- Move retraining buttons into a visually separate command area.

Optional backend support:

- Expose `reports/model_evaluation_latest.json` or add `/api/model-evaluation` if the generated report becomes a first-class UI surface.

### 4. Portfolio

Purpose: show paper account health, exposure, settlement, CLV, and execution quality.

Layout:

- KPI row: bankroll, available, open exposure, settled P&L, average CLV.
- Paper bets table with filters for open/settled/cashed out/lost/won.
- CLV panel upgraded from table to:
  - average CLV card
  - positive CLV rate card
  - CLV table
  - optional CLV distribution chart later
- Equity curve stays but should sit next to a drawdown summary.
- Recent decisions should move to row detail or Command Center unless they are execution-specific.

Needed frontend changes:

- Split `renderBetsStats`, `renderBets`, and `renderClv` into portfolio subsections.
- Add status filters and clearer settlement labels.
- Surface unmatched/unsettled reason if available.

Optional backend support:

- Add settlement reason/status fields in paper bet state if not already available through notes/events.

### 5. Data Health

Purpose: make data coverage and feed reliability auditable.

Layout:

- Odds feed status at the top: configured, latest capture, stale window, rows inserted, latest errors.
- Source table: Bet365, The Odds API, manual CSV, app fixture odds; show rows, fixtures, latest capture, freshness.
- Model data coverage: Cricsheet rows, Elo rows, model runs, model predictions, active model, backtest runs.
- Diagnostics stream: unmatched teams, API failures, scheduler errors, data gaps.
- Event log with filters by type and text search.

Needed frontend changes:

- Move readiness model/data checks from Overview into this page as grouped status cards.
- Add event filtering and compact log rows.
- Keep raw error text readable without expanding table width.

Optional backend support:

- Add event type counts and latest diagnostics summary to `/api/state`.

## Visual Design Direction

Keep the product quiet, dense, and operational. Avoid marketing-style hero layouts.

Recommended style changes:

- Reduce the one-note green/cream feeling by introducing a more balanced neutral system:
  - background: near-white/cool grey
  - primary action: green
  - research/data accent: blue
  - warning: amber
  - danger: red
  - neutral panel borders/shadows less prominent
- Reduce card radius from `10px` to `8px` to align with a sharper dashboard feel.
- Use clearer density rules:
  - KPI cards compact and equal-height
  - tables with sticky headers
  - smaller panel headings in dense tool surfaces
- Add focus states and keyboard-visible outlines.
- Make badges consistent in width/weight for scanability.
- Keep charts full-width within their panels and avoid nested panel-in-panel layouts.

## Interaction Improvements

### Action Safety

Current action buttons all disable during busy state, but results are easy to miss. Upgrade to:

- Command buttons grouped by impact:
  - routine: Monitor Tick, Fetch Live Odds
  - workflow: Run Morning, Pull All Live Data
  - research: Train/Rebuild commands
  - destructive: Reset Demo
- Persistent action status area:
  - running action name
  - start time/duration
  - success/error
  - key result counts
- Confirmation only for destructive actions and expensive retrains.
- Replace `alert(error.message)` with an inline error banner that remains after reload.

### Empty States

Create consistent empty-state components:

- `No trained models`: show exact command/button to run and why it matters.
- `No fresh odds`: show provider config status and stale-window info.
- `No backtest candidates`: explain the real-odds plus Cricsheet-link requirement.
- `Demo only`: explain that demo context cannot place paper bets.

### Tables

Upgrade high-value tables with:

- sticky headers
- compact row height
- column alignment rules
- client-side sort for numeric columns
- filters for status/source/freshness
- row details via expandable sections
- visible horizontal scroll hint on mobile

### Charts

Add chart-level helper text for interpretation:

- Brier/log loss: lower is better.
- Calibration: points above diagonal mean underconfident, below means overconfident.
- Backtest P&L: based only on timestamp-valid historical baselines.
- Edge bucket: sample size matters.

## Implementation Phases

### Phase 1: UX Restructure Without Backend Changes

Files likely changed:

- `cricket_edge/web/templates/index.html`
- `cricket_edge/web/static/app.js`
- `cricket_edge/web/static/styles.css`

Tasks:

- Rename pages to Command, Opportunities, Research, Portfolio, Data Health.
- Reorganize existing panels into the target IA.
- Add severity-grouped readiness rendering.
- Add persistent action status/error banner.
- Add Research tabs using current chart/data objects.
- Add basic filters for Opportunities and Portfolio.

Acceptance criteria:

- No backend API change required.
- All existing buttons still work.
- All existing charts still render.
- Mobile layout reaches key status before the full action stack.

### Phase 2: Candidate Review Upgrade

Files likely changed:

- `cricket_edge/orchestrator.py` or new frontend-only joining logic in `app.js`
- `cricket_edge/web/static/app.js`
- `cricket_edge/web/static/styles.css`
- tests for state shape if backend changes

Tasks:

- Create a denormalized candidate row model.
- Show actionability groups and explicit skip/block reasons.
- Add table sorting/filtering.
- Add expandable row details.

Acceptance criteria:

- A user can see why every fixture is actionable, blocked, or demo-only.
- Fresh/stale/no-odds status is visible per row.
- Model source and confidence are visible per row.

### Phase 3: Research Evidence Upgrade

Files likely changed:

- `cricket_edge/charts.py`
- `cricket_edge/web/static/app.js`
- `cricket_edge/web/static/styles.css`
- maybe `cricket_edge/orchestrator.py`

Tasks:

- Render T10 backtest fields: source, confidence bucket, closing-line result, CLV.
- Add calibration bucket table under chart.
- Add model run summary cards.
- Add small-sample warnings near backtest charts.

Acceptance criteria:

- Model promotion evidence is visible without reading logs.
- Backtest sample-size warnings are not hidden below charts.
- Synthetic market baselines are clearly marked as non-real if shown.

### Phase 4: Data Health and Diagnostics

Files likely changed:

- `cricket_edge/orchestrator.py`
- `cricket_edge/readiness.py`
- `cricket_edge/web/static/app.js`
- `cricket_edge/web/static/styles.css`

Tasks:

- Add event filters and diagnostic summaries.
- Add data coverage cards from readiness/model counts.
- Add unmatched-team and API-error panels.
- Add latest raw provider snapshot metadata if available.

Acceptance criteria:

- User can diagnose missing bets without opening SQLite.
- API and data freshness problems are visible on one page.

### Phase 5: Accessibility and Polish

Tasks:

- Add keyboard focus styles.
- Add ARIA labels for nav, status banners, and chart containers.
- Add `aria-live` region for action status.
- Check color contrast for badge text and sidebar nav.
- Verify desktop and mobile screenshots.
- Reduce layout shifts by defining stable dimensions for metrics, charts, and toolbars.

Acceptance criteria:

- Keyboard-only navigation can reach all actions and pages.
- Action success/error is announced to assistive tech.
- No overlapping text or table controls at mobile widths.

## Verification Plan

Run after each implementation phase:

```powershell
py -3.13 -m pytest -q
```

Manual browser checks:

- Desktop: 1440x900 and 1280x720.
- Tablet/mobile: 768x1024 and 390x844.
- Empty DB/demo state.
- State after `Run Morning`.
- State with no fresh real odds.
- State after model training/backtest data exists.

UI checks:

- No text overlap in sidebar, tables, cards, or buttons.
- All buttons disable during action and show persistent result.
- Reset Demo remains clearly destructive.
- Demo-only rows cannot be mistaken for bettable rows.
- Backtest warnings are visible above charts.
- Tables remain usable on narrow screens.

If using Browser/Playwright later, capture screenshots for each page and compare key panels against expected selectors.

## Recommended First UI PR

Start with Phase 1 only. It has the best payoff and lowest backend risk.

Deliverables:

- New page labels and panel order.
- Command Center status-first layout.
- Grouped readiness blockers.
- Persistent action status banner.
- Research tabs using existing charts.
- Opportunities and Portfolio page split using current data.

Do not add a new frontend framework yet. The current app is small enough that careful HTML/CSS/JS refactoring is faster and less risky than introducing React/Vite. Consider a framework only after the UI needs reusable complex table components, route state, or richer interaction patterns that become painful in plain JS.
