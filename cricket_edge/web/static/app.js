const state = {
  data: null,
  busy: false,
  currentPage: "command",
  researchTab: "models",
  action: null,
  filters: {
    opportunities: { source: "all", status: "all" },
    portfolio: { status: "all" },
    events: { type: "all" },
  },
};

const gbp = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" });
const pct = new Intl.NumberFormat("en-GB", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });

const ACTION_BUTTON_IDS = [
  "runMorning", "monitorTick", "trainElo", "trainLogistic", "trainWeek3", "runWeek4",
  "fetchBet365Odds", "pullLiveData", "settleBets", "resetDemo",
];

const ACTION_LABELS = {
  runMorning: "Run Morning",
  monitorTick: "Monitor Tick",
  trainElo: "Train Elo",
  trainLogistic: "Train Logistic",
  trainWeek3: "Force Retrain Now",
  runWeek4: "Rebuild Market Data",
  fetchBet365Odds: "Fetch Live Odds",
  pullLiveData: "Pull All Live Data",
  settleBets: "Settle Paper",
  resetDemo: "Reset Demo",
};

const PIPELINE_STAGES = [
  { key: "data_health_check", label: "Data Health", role: "Checks fixtures, odds, and predictions exist before anything else runs." },
  { key: "bet_evaluator", label: "Bet Evaluation", role: "Reads predictions, applies hard risk rules, then proposes paper bets." },
  { key: "risk_gate", label: "Risk Gate", role: "Reviews proposed bets and vetoes them if data health or portfolio rules fail." },
  { key: "position_monitor", label: "Position Monitoring", role: "Watches open paper bets and simulates cash-out when odds move far enough." },
  { key: "briefing_writer", label: "Daily Briefing", role: "Writes the daily briefing from account state and top model edges." },
  { key: "model_governance", label: "Model Governance", role: "Retrains candidates and only promotes one that beats the incumbent." },
];

const PAGE_TITLES = {
  command: "Today status, blockers, and next actions",
  opportunities: "Fixture opportunities, odds freshness, and model edge",
  research: "Model evidence, calibration, and historical backtests",
  portfolio: "Paper positions, exposure, settlement, and CLV",
  data: "Feed health, data coverage, and diagnostics",
};

PAGE_TITLES.guide = 'How to use the paper-trading research dashboard';

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json();
  if (!response.ok || body.ok === false) throw new Error(body.error || "Request failed");
  return body;
}

async function loadState(options = {}) {
  if (!options.silent) setBusy(true);
  try {
    state.data = await api("/api/state");
    render();
  } catch (error) {
    setActionStatus({ status: "error", label: "Refresh state", message: error.message });
  } finally {
    if (!options.silent) setBusy(false);
  }
}

async function postAction(path, label) {
  const startedAt = performance.now();
  setBusy(true);
  setActionStatus({ status: "running", label, message: "Running..." });
  try {
    const body = await api(path, { method: "POST" });
    state.data = body.state || state.data;
    if (body.reload_state) state.data = await api("/api/state");
    const duration = Math.max(0.1, (performance.now() - startedAt) / 1000);
    setActionStatus({ status: "success", label, message: summarizeActionResult(body.result), duration });
    render();
  } catch (error) {
    const duration = Math.max(0.1, (performance.now() - startedAt) / 1000);
    setActionStatus({ status: "error", label, message: error.message, duration });
  } finally {
    setBusy(false);
  }
}

function setBusy(value) {
  state.busy = value;
  for (const id of ACTION_BUTTON_IDS) {
    const el = document.getElementById(id);
    if (el) el.disabled = value;
  }
}

function setActionStatus(action) {
  state.action = { ...action, updatedAt: new Date().toISOString() };
  renderActionStatus();
}

function switchPage(page) {
  state.currentPage = page;
  for (const section of document.querySelectorAll(".page")) section.classList.toggle("active", section.dataset.page === page);
  for (const link of document.querySelectorAll(".nav-link")) link.classList.toggle("active", link.dataset.page === page);
  document.getElementById("pageTitle").textContent = PAGE_TITLES[page] || "";
  window.location.hash = page;
  renderChartsForPage(page);
}

function switchResearchTab(tab) {
  state.researchTab = tab;
  for (const button of document.querySelectorAll("#researchTabs .tab")) button.classList.toggle("active", button.dataset.tab === tab);
  for (const page of document.querySelectorAll(".tab-page")) page.classList.toggle("active", page.dataset.tabPage === tab);
  renderChartsForPage("research");
}

function render() {
  const data = state.data;
  if (!data) return;
  document.getElementById("lastUpdated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  renderSchedulerBanner(data.scheduler || {});
  renderActionStatus();
  renderCommandCenter(data);
  renderOpportunities(data);
  renderResearch(data);
  renderPortfolio(data);
  renderDataHealth(data);
  renderChartsForPage(state.currentPage);
}

function renderChartsForPage(page) {
  const charts = (state.data || {}).charts || {};
  const chartKeys = { research: researchChartKeys(), portfolio: ["equity_curve"] }[page] || [];
  for (const key of chartKeys) {
    const spec = charts[key];
    const el = document.getElementById(`chart-${key}`);
    if (!spec || !el || typeof Plotly === "undefined") continue;
    Plotly.react(el, spec.data, spec.layout, { displaylogo: false, responsive: true });
  }
}

function researchChartKeys() {
  if (state.researchTab === "models") return ["model_comparison"];
  if (state.researchTab === "calibration") return ["calibration"];
  if (state.researchTab === "backtest") return ["backtest_pnl", "edge_bucket"];
  if (state.researchTab === "features") return ["feature_importance", "elo_ratings"];
  return [];
}

function renderCommandCenter(data) {
  renderCommandStatusStrip(data);
  renderMetrics(data.account || {}, data.backtesting || {});
  renderReadiness(data.readiness || {});
  renderWorkflowResult();
  renderDecisionPipeline(data.decisions || []);
  renderBriefing(data.decisions || []);
}

function renderCommandStatusStrip(data) {
  const odds = ((data.week4 || {}).bet365_status || {});
  const active = ((data.week3 || {}).registry || []).find((row) => Number(row.active));
  const backtest = (data.backtesting || {}).payload || {};
  const items = [
    statusStripItem("Paper mode", "No live-money connector", "good"),
    statusStripItem("Scheduler", (data.scheduler || {}).alive ? "Running" : "Not alive", (data.scheduler || {}).alive ? "good" : "warn"),
    statusStripItem("Odds", odds.is_fresh ? "Fresh real odds" : (odds.freshness_status || "No fresh odds"), odds.is_fresh ? "good" : "warn"),
    statusStripItem("Active model", active ? active.model_name : "None", active ? "good" : "bad"),
    statusStripItem("Backtest", backtest.bets ? `${backtest.bets} bets` : "No sample", backtest.bets ? "warn" : "bad"),
  ];
  setHTML("commandStatusStrip", items.join(""));
}

function statusStripItem(label, value, tone) {
  return `<article class="status-chip ${tone}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`;
}

function renderMetrics(account, backtesting) {
  const payload = backtesting.payload || {};
  const avgClv = payload.avg_clv == null ? null : Number(payload.avg_clv);
  const metrics = [
    ["Bankroll", gbp.format(Number(account.bankroll || 0)), `${gbp.format(Number(account.settled_pnl || 0))} settled P&L`],
    ["Available", gbp.format(Number(account.available || 0)), "After open paper exposure"],
    ["Open Exposure", gbp.format(Number(account.open_exposure || 0)), `${Number(account.open_bets || 0)} open bets`],
    ["Backtest CLV", avgClv == null ? "-" : pct.format(avgClv), payload.sample_warning || "Entry vs closing proxy"],
  ];
  setHTML("overview", metrics.map(([label, value, sub]) => metricCard(label, value, sub)).join(""));
}

function renderSchedulerBanner(scheduler) {
  const dot = document.getElementById("schedulerDot");
  const text = document.getElementById("schedulerText");
  if (!dot || !text) return;
  if (!scheduler.enabled) {
    dot.className = "dot bad";
    text.textContent = "Scheduler: disabled";
    return;
  }
  if (!scheduler.alive) {
    dot.className = "dot warn";
    text.textContent = "Scheduler: starting";
    return;
  }
  dot.className = "dot";
  const lastTick = scheduler.last_tick_at ? new Date(scheduler.last_tick_at).toLocaleTimeString() : "-";
  const lastRetrain = scheduler.last_retrain_at ? new Date(scheduler.last_retrain_at).toLocaleTimeString() : "never";
  text.textContent = `Scheduler: running (${lastTick}, retrain ${lastRetrain})`;
}

function renderActionStatus() {
  const el = document.getElementById("actionStatus");
  if (!el) return;
  if (!state.action) {
    el.innerHTML = `<div class="action-card idle"><strong>Ready</strong><span>Run a workflow from the sidebar when the gate is clear.</span></div>`;
    renderWorkflowResult();
    return;
  }
  const duration = state.action.duration ? ` in ${state.action.duration.toFixed(1)}s` : "";
  el.innerHTML = `
    <div class="action-card ${state.action.status}">
      <strong>${escapeHtml(state.action.label)} - ${escapeHtml(state.action.status)}${duration}</strong>
      <span>${escapeHtml(state.action.message || "")}</span>
    </div>
  `;
  renderWorkflowResult();
}

function renderWorkflowResult() {
  const action = state.action;
  if (!document.getElementById("workflowResult")) return;
  if (!action) {
    setHTML("workflowResult", `<div class="empty-state">No manual workflow has run in this browser session.</div>`);
    return;
  }
  const rows = `
    <tr><td>Action</td><td>${escapeHtml(action.label)}</td></tr>
    <tr><td>Status</td><td><span class="badge ${badgeForAction(action.status)}">${escapeHtml(action.status)}</span></td></tr>
    <tr><td>Updated</td><td>${escapeHtml(new Date(action.updatedAt).toLocaleTimeString())}</td></tr>
    <tr><td>Result</td><td>${escapeHtml(action.message || "-")}</td></tr>
  `;
  setHTML("workflowResult", table(["Field", "Value"], rows));
}

function summarizeActionResult(result) {
  if (!result || typeof result !== "object") return "Completed.";
  const parts = [];
  if (result.predictions != null) parts.push(`${result.predictions} predictions`);
  if (result.decisions != null) parts.push(`${result.decisions} decisions`);
  if (result.bets_placed != null) parts.push(`${result.bets_placed} bets placed`);
  if (result.odds_rows_inserted != null) parts.push(`${result.odds_rows_inserted} odds rows`);
  if (result.rows_inserted != null) parts.push(`${result.rows_inserted} rows inserted`);
  if (result.reset) parts.push("demo reset");
  if (result.settlement && result.settlement.settled != null) parts.push(`${result.settlement.settled} settled`);
  if (result.account) parts.push(`bankroll ${gbp.format(Number(result.account.bankroll || 0))}`);
  return parts.length ? parts.join("; ") : "Completed and reloaded state.";
}

function renderReadiness(readiness) {
  const items = readiness.items || [];
  if (!items.length) {
    setHTML("readinessPanel", `<div class="empty-state">No readiness report available.</div>`);
    setText("gateSummary", "No report");
    return;
  }
  const criticalKeys = new Set(["active_model", "model_runs", "model_predictions", "real_odds_captured", "fresh_odds_gate", "model_training_data", "historical_backtesting", "backtest_sample_size"]);
  const gaps = items.filter((item) => item.status === "gap" && criticalKeys.has(item.key));
  const watch = items.filter((item) => item.status === "watch" || (item.status === "gap" && !criticalKeys.has(item.key)));
  const pass = items.filter((item) => item.status === "pass");
  setText("gateSummary", gaps.length ? `${gaps.length} blocker${gaps.length === 1 ? "" : "s"}` : watch.length ? "Watch" : "Clear");
  document.getElementById("gateSummary").className = `pill ${gaps.length ? "bad" : watch.length ? "warn" : "good"}`;
  setHTML("readinessPanel", `${readinessGroup("Critical blockers", gaps, "bad")}${readinessGroup("Watch items", watch, "warn")}${readinessGroup("Passing controls", pass, "good", true)}`);
  renderDataCoverage(items);
}

function readinessGroup(title, items, tone, collapsed = false) {
  if (!items.length) return `<section class="readiness-group ${tone}"><h4>${escapeHtml(title)}</h4><div class="empty-state compact">None</div></section>`;
  const rows = items.map((item) => `
    <article class="readiness-item">
      <span class="badge ${badgeForReadiness(item.status)}">${escapeHtml(item.status)}</span>
      <div><strong>${escapeHtml(item.label)}</strong><p>${escapeHtml(item.detail)}</p></div>
    </article>
  `).join("");
  if (collapsed) return `<details class="readiness-group ${tone}"><summary>${escapeHtml(title)} (${items.length})</summary>${rows}</details>`;
  return `<section class="readiness-group ${tone}"><h4>${escapeHtml(title)}</h4>${rows}</section>`;
}

function renderDecisionPipeline(decisions) {
  const latestBySource = {};
  for (const decision of decisions) if (!latestBySource[decision.source]) latestBySource[decision.source] = decision;
  const cards = PIPELINE_STAGES.map((stage, index) => {
    const last = latestBySource[stage.key];
    const status = last ? `<span class="badge ${badgeForDecision(last.decision)}">${escapeHtml(last.decision)}</span><span>${escapeHtml(shortDateTime(last.generated_at))}</span>` : `<span class="muted">No runs yet</span>`;
    const reason = last ? escapeHtml(last.reason || "") : escapeHtml(stage.role);
    return `
      <article class="pipeline-stage">
        <div class="step-index">${index + 1}</div>
        <div><div class="pipeline-label">${escapeHtml(stage.label)}</div><div class="pipeline-status">${status}</div><div class="pipeline-reason muted">${reason}</div></div>
      </article>
    `;
  }).join("");
  const broker = `<article class="pipeline-stage broker"><div class="step-index">B</div><div><div class="pipeline-label">Paper Broker</div><div class="pipeline-reason muted">Executes, monitors, and settles simulated bets. No real-money connector exists.</div></div></article>`;
  setHTML("decisionPipeline", cards + broker);
}

function renderBriefing(decisions) {
  const briefing = decisions.find((d) => d.source === "briefing_writer");
  let lines = [];
  if (briefing) {
    try { lines = (JSON.parse(briefing.payload_json || "{}").briefing || []); } catch { lines = []; }
  }
  if (!lines.length) lines = ["Run Morning to generate the first paper-trading briefing."];
  setHTML("briefing", lines.map((line) => `<p>${tagBriefing(line)}${escapeHtml(line)}</p>`).join(""));
}

function tagBriefing(line) {
  const lower = String(line).toLowerCase();
  const tag = lower.includes("odds") ? "odds" : lower.includes("risk") ? "risk" : lower.includes("model") ? "model" : "portfolio";
  return `<span class="mini-tag">${tag}</span>`;
}

function renderOpportunities(data) {
  renderOpportunityFilters();
  const rows = buildOpportunityRows(data);
  const filtered = rows.filter((row) => {
    const f = state.filters.opportunities;
    return (f.source === "all" || row.sourceGroup === f.source) && (f.status === "all" || row.statusGroup === f.status);
  });
  const grouped = [
    ["Actionable paper candidates", filtered.filter((row) => row.statusGroup === "actionable")],
    ["Blocked by data or risk", filtered.filter((row) => row.statusGroup === "blocked")],
    ["Demo/context only", filtered.filter((row) => row.statusGroup === "demo")],
    ["Needs model run", filtered.filter((row) => row.statusGroup === "unscored")],
  ];
  const html = grouped.map(([title, items]) => opportunityGroup(title, items)).join("");
  setHTML("matchesTable", html || `<div class="empty-state">No fixtures match the selected filters.</div>`);
}

function renderOpportunityFilters() {
  setHTML("opportunityFilters", `
    ${selectControl("oppSource", "Source", state.filters.opportunities.source, [["all", "All sources"], ["real", "Real odds"], ["demo", "Demo/context"], ["none", "No odds"]])}
    ${selectControl("oppStatus", "Status", state.filters.opportunities.status, [["all", "All statuses"], ["actionable", "Actionable"], ["blocked", "Blocked"], ["demo", "Demo only"], ["unscored", "Needs model"]])}
  `);
}

function buildOpportunityRows(data) {
  const predictionsByFixture = groupBy(data.predictions || [], "fixture_id");
  const decisionsByFixture = latestDecisionByFixture(data.decisions || []);
  return (data.fixtures || []).map((fixture) => {
    const preds = (predictionsByFixture[fixture.id] || []).sort((a, b) => Number(b.edge) - Number(a.edge));
    const best = preds[0];
    const features = best ? parseJson(best.features_json) : {};
    const latestDecision = decisionsByFixture[fixture.id];
    const realOdds = ["bet365", "the_odds_api"].includes(features.market_source);
    const fresh = Boolean(features.market_is_fresh);
    const demo = fixture.source === "demo" || features.feature_source === "deterministic_demo_features";
    const statusGroup = !best ? "unscored" : demo ? "demo" : realOdds && fresh && Number(best.edge) >= 0.03 ? "actionable" : "blocked";
    const sourceGroup = realOdds ? "real" : demo ? "demo" : "none";
    return { fixture, best, features, latestDecision, statusGroup, sourceGroup };
  });
}

function opportunityGroup(title, items) {
  if (!items.length) return "";
  const rows = items.map(({ fixture, best, features, latestDecision, statusGroup }) => {
    const edge = best ? Number(best.edge) : 0;
    const badge = statusGroup === "actionable" ? "good" : statusGroup === "blocked" ? "warn" : statusGroup === "demo" ? "bad" : "warn";
    const statusText = statusGroup === "actionable" ? "candidate" : statusGroup === "blocked" ? "blocked" : statusGroup === "demo" ? "demo only" : "needs model";
    const reason = latestDecision ? latestDecision.reason : marketStatusText(features, best);
    return `
      <tr>
        <td><div class="match-title">${escapeHtml(fixture.team_a)} vs ${escapeHtml(fixture.team_b)}</div><div class="muted">${escapeHtml(fixture.competition)} - ${escapeHtml(fixture.match_date)} ${escapeHtml(fixture.start_time)}</div></td>
        <td>${sourceBadge(features, fixture)}</td>
        <td>${best ? escapeHtml(best.selection) : "-"}</td>
        <td class="number">${best ? pct.format(Number(best.probability)) : "-"}</td>
        <td class="number">${best ? Number(best.market_odds).toFixed(2) : "-"}</td>
        <td><span class="badge ${badge}">${best ? pct.format(edge) : statusText}</span></td>
        <td class="number">${best ? pct.format(Number(best.confidence)) : "-"}</td>
        <td><div class="muted reason-cell">${escapeHtml(reason)}</div></td>
      </tr>
    `;
  }).join("");
  return `<h4 class="section-title">${escapeHtml(title)} (${items.length})</h4>${table(["Match", "Source", "Side", "Prob", "Market", "Edge", "Confidence", "Reason"], rows)}`;
}

function marketStatusText(features, prediction) {
  if (!prediction) return "Run model to score this fixture.";
  if (features.market_status) return features.market_status;
  return "No recent decision yet.";
}

function sourceBadge(features, fixture) {
  const source = features.market_source || fixture.source || "unknown";
  const fresh = Boolean(features.market_is_fresh);
  const real = ["bet365", "the_odds_api"].includes(source);
  const cls = real && fresh ? "good" : real ? "warn" : "bad";
  const label = real ? `${source}${fresh ? " fresh" : " stale"}` : fixture.source === "demo" ? "demo" : "no odds";
  return `<span class="badge ${cls}">${escapeHtml(label)}</span>`;
}

function latestDecisionByFixture(decisions) {
  const output = {};
  for (const decision of decisions) if (decision.fixture_id && !output[decision.fixture_id]) output[decision.fixture_id] = decision;
  return output;
}

function renderResearch(data) {
  renderResearchSummary(data);
  renderModelRegistry(data.week3 || {});
  renderBacktestSummary(data.backtesting || {});
  renderCalibrationNotes();
}

function renderResearchSummary(data) {
  const registry = (data.week3 || {}).registry || [];
  const active = registry.find((row) => Number(row.active));
  const payload = (data.backtesting || {}).payload || {};
  const week1 = data.week1 || {};
  const cards = [
    ["Active Model", active ? active.model_name : "None", active ? active.timing : "Run governed training"],
    ["Training Rows", Number((week1.cricsheet || {}).matches || 0).toLocaleString("en-GB"), "Cricsheet matches"],
    ["Backtest Bets", Number(payload.bets || 0).toLocaleString("en-GB"), payload.sample_warning || "Timestamp-safe candidates"],
    ["Avg CLV", payload.avg_clv == null ? "-" : pct.format(Number(payload.avg_clv)), "Backtest closing proxy"],
  ];
  setHTML("researchSummary", cards.map(([label, value, sub]) => metricCard(label, value, sub)).join(""));
}

function renderModelRegistry(week3) {
  const registry = week3.registry || [];
  if (!registry.length) {
    setHTML("modelGovernancePanel", `<div class="empty-state">No model registry yet. Run governed training from Research commands.</div>`);
    return;
  }
  const rows = registry.map((item) => {
    const badge = Number(item.active) ? "good" : "warn";
    return `<tr><td><span class="badge ${badge}">${Number(item.active) ? "active" : escapeHtml(item.status)}</span></td><td><div class="match-title">${escapeHtml(item.model_name)}</div><div class="muted">${escapeHtml(item.timing)} - calibrated: ${Number(item.calibrated) ? "yes" : "no"}</div></td></tr>`;
  }).join("");
  setHTML("modelGovernancePanel", table(["Status", "Model"], rows));
}

function renderCalibrationNotes() {
  setHTML("calibrationNotes", `<p><strong>How to read this:</strong> points above the diagonal mean the model was underconfident; points below the diagonal mean it was overconfident. Bucket size affects trust.</p>`);
}

function renderBacktestSummary(backtesting) {
  const payload = backtesting.payload || {};
  if (!payload.bets && payload.message) {
    setHTML("backtestSummary", `<div class="empty-state">${escapeHtml(payload.message)}</div>`);
    setHTML("backtestBreakdowns", "");
    return;
  }
  const rows = `
    <tr><td>Model</td><td>${escapeHtml(payload.model_name || "-")}</td></tr>
    <tr><td>Candidates / bets</td><td class="number">${Number(payload.n_candidates || 0).toLocaleString("en-GB")} / ${Number(payload.bets || 0).toLocaleString("en-GB")}</td></tr>
    <tr><td>Win rate</td><td class="number">${pct.format(Number(payload.win_rate || 0))}</td></tr>
    <tr><td>Staked / P&amp;L</td><td class="number">${gbp.format(Number(payload.staked || 0))} / ${gbp.format(Number(payload.pnl || 0))}</td></tr>
    <tr><td>ROI / Yield</td><td class="number">${pct.format(Number(payload.roi || 0))}</td></tr>
    <tr><td>Avg CLV</td><td class="number">${payload.avg_clv == null ? "-" : pct.format(Number(payload.avg_clv))}</td></tr>
    <tr><td>Positive CLV rate</td><td class="number">${payload.positive_clv_rate == null ? "-" : pct.format(Number(payload.positive_clv_rate))}</td></tr>
    <tr><td>Max drawdown</td><td class="number">${gbp.format(Number(payload.max_drawdown || 0))}</td></tr>
  `;
  const warning = payload.sample_warning ? `<div class="inline-warning">${escapeHtml(payload.sample_warning)}</div>` : "";
  setHTML("backtestSummary", warning + table(["Metric", "Value"], rows));
  setHTML("backtestBreakdowns", `
    ${breakdownTable("By Source", "source", payload.by_source || [])}
    ${breakdownTable("By Confidence", "confidence_bucket", payload.by_confidence_bucket || [])}
    ${breakdownTable("By Closing Line", "closing_line_result", payload.by_closing_line_result || [])}
    ${breakdownTable("By Competition", "competition", (payload.by_competition || []).slice(0, 8))}
  `);
}

function breakdownTable(title, key, items) {
  if (!items.length) return "";
  const rows = items.map((item) => `
    <tr>
      <td>${escapeHtml(item[key] || "unknown")}</td>
      <td class="number">${Number(item.bets || 0).toLocaleString("en-GB")}</td>
      <td class="number">${gbp.format(Number(item.pnl || 0))}</td>
      <td class="number">${pct.format(Number(item.roi || 0))}</td>
      <td class="number">${item.avg_clv == null ? "-" : pct.format(Number(item.avg_clv))}</td>
    </tr>
  `).join("");
  return `<h4 class="section-title">${escapeHtml(title)}</h4>${table(["Bucket", "Bets", "P&L", "ROI", "Avg CLV"], rows)}`;
}

function renderPortfolio(data) {
  renderBetsStats(data.paper_bets || [], ((data.week4 || {}).paper_clv || {}), (data.account || {}));
  renderPortfolioFilters();
  renderBets(data.paper_bets || []);
  renderClv((data.week4 || {}).paper_bet_evaluations || []);
}

function renderBetsStats(bets, clv, account) {
  const closed = bets.filter((b) => ["settled", "cashed_out", "voided"].includes(b.status));
  const wins = closed.filter((b) => Number(b.pnl) > 0).length;
  const winRate = closed.length ? wins / closed.length : 0;
  const avgClv = clv.avg_clv == null ? null : Number(clv.avg_clv);
  const cards = [
    ["Bankroll", gbp.format(Number(account.bankroll || 0)), `${gbp.format(Number(account.open_exposure || 0))} open exposure`],
    ["Closed Bets", closed.length.toLocaleString("en-GB"), `${bets.filter((b) => b.status === "open").length} still open`],
    ["Hit Rate", closed.length ? pct.format(winRate) : "-", `${wins} of ${closed.length} won`],
    ["Avg CLV", avgClv == null ? "-" : pct.format(avgClv), "Entry vs closing-price proxy"],
  ];
  setHTML("betsStats", cards.map(([label, value, sub]) => metricCard(label, value, sub)).join(""));
}

function renderPortfolioFilters() {
  setHTML("portfolioFilters", selectControl("portfolioStatus", "Status", state.filters.portfolio.status, [["all", "All"], ["open", "Open"], ["settled", "Settled"], ["cashed_out", "Cashed out"], ["voided", "Voided"]]));
}

function renderBets(bets) {
  const status = state.filters.portfolio.status;
  const filtered = bets.filter((bet) => status === "all" || bet.status === status);
  if (!filtered.length) {
    setHTML("betsTable", `<div class="empty-state">No paper bets match the selected filter.</div>`);
    return;
  }
  const rows = filtered.map((bet) => {
    const badge = bet.status === "open" ? "warn" : Number(bet.pnl) >= 0 ? "good" : "bad";
    const result = bet.status === "open" ? "pending" : bet.status === "voided" ? "void" : Number(bet.pnl) > 0 ? "won" : Number(bet.pnl) < 0 ? "lost" : "void";
    return `
      <tr>
        <td><div class="match-title">${escapeHtml(bet.selection)}</div><div class="muted">${escapeHtml(bet.team_a)} vs ${escapeHtml(bet.team_b)}</div></td>
        <td>${escapeHtml(bet.market)}</td><td class="number">${gbp.format(Number(bet.stake))}</td><td class="number">${Number(bet.odds).toFixed(2)}</td>
        <td><span class="badge ${badge}">${escapeHtml(bet.status)}</span></td><td><span class="badge ${badge}">${result}</span></td><td class="number">${gbp.format(Number(bet.pnl))}</td><td>${escapeHtml(bet.notes || "")}</td>
      </tr>
    `;
  }).join("");
  setHTML("betsTable", table(["Selection", "Market", "Stake", "Odds", "Status", "Result", "P&L", "Notes"], rows));
}

function renderClv(evaluations) {
  const rows = evaluations.map((item) => `
    <tr><td>${escapeHtml(item.selection)}</td><td>${escapeHtml(item.team_a)} vs ${escapeHtml(item.team_b)}</td><td class="number">${Number(item.entry_odds || 0).toFixed(2)}</td><td class="number">${item.closing_odds ? Number(item.closing_odds).toFixed(2) : "-"}</td><td class="number">${item.clv == null ? "-" : pct.format(Number(item.clv))}</td></tr>
  `).join("");
  setHTML("clvPanel", rows ? table(["Selection", "Match", "Entry", "Close", "CLV"], rows) : `<div class="empty-state">No paper CLV evaluations yet. Run Rebuild Market Data after paper bets and odds snapshots exist.</div>`);
}

function renderDataHealth(data) {
  renderDataLogs(data.week4 || {});
  renderEvents(data.events || []);
  renderDataCoverage((data.readiness || {}).items || []);
}

function renderDataCoverage(items) {
  const wanted = new Set(["model_training_data", "model_runs", "model_predictions", "active_model", "historical_backtesting", "backtest_sample_size", "real_odds_captured", "clv_tracking"]);
  const rows = items.filter((item) => wanted.has(item.key)).map((item) => `
    <tr><td><span class="badge ${badgeForReadiness(item.status)}">${escapeHtml(item.status)}</span></td><td><div class="match-title">${escapeHtml(item.label)}</div><div class="muted">${escapeHtml(item.detail)}</div></td></tr>
  `).join("");
  setHTML("dataCoveragePanel", rows ? table(["Status", "Check"], rows) : `<div class="empty-state">No data coverage report available.</div>`);
}

function renderDataLogs(week4) {
  const counts = week4.market_counts || {};
  const bet365 = week4.bet365_status || {};
  const sourceCounts = week4.source_counts || [];
  const bet365Recent = week4.bet365_recent_odds || [];
  const liveOddsBadge = bet365.configured ? `<span class="badge good">configured</span>` : `<span class="badge bad">missing key</span>`;
  const bet365ErrorText = (bet365.latest_errors || []).map((item) => `${item.stage || "fetch"}: ${item.error || "error"}`).join(" | ");
  const freshness = bet365.freshness || {};
  const panelRows = `
    <tr><td>Live odds feed</td><td>${liveOddsBadge} ${escapeHtml(bet365.latest_capture || "No captured odds yet")}</td></tr>
    <tr><td>Provider</td><td>${escapeHtml(bet365.provider || "Live odds aggregator")}</td></tr>
    <tr><td>Fallback used</td><td>${bet365.fallback_used ? "yes" : "no"}</td></tr>
    <tr><td>Feed freshness</td><td><span class="badge ${bet365.is_fresh ? "good" : "warn"}">${escapeHtml(bet365.freshness_status || "unknown")}</span> ${freshness.minutes_old == null ? "" : `${Number(freshness.minutes_old).toFixed(1)} min old`}</td></tr>
    <tr><td>Latest fetch</td><td>${escapeHtml(bet365.latest_fetch_at || "-")}</td></tr>
    <tr><td>Events checked</td><td class="number">${Number(bet365.events_checked || 0).toLocaleString("en-GB")}</td></tr>
    <tr><td>Rows inserted last fetch</td><td class="number">${Number(bet365.odds_rows_inserted || 0).toLocaleString("en-GB")}</td></tr>
    <tr><td>Latest odds status</td><td>${escapeHtml(bet365.latest_message || "No fetch attempted yet")}</td></tr>
    <tr><td>Latest odds error</td><td class="wrap-cell">${escapeHtml(bet365ErrorText || "-")}</td></tr>
    <tr><td>Market odds rows</td><td class="number">${Number(counts.odds_rows || 0).toLocaleString("en-GB")}</td></tr>
    <tr><td>Fixtures with odds</td><td class="number">${Number(counts.fixtures || 0).toLocaleString("en-GB")}</td></tr>
  `;
  const sourceRows = sourceCounts.map((item) => `<tr><td>${escapeHtml(item.source)}</td><td class="number">${Number(item.odds_rows || 0).toLocaleString("en-GB")}</td><td class="number">${Number(item.fixtures || 0).toLocaleString("en-GB")}</td><td>${escapeHtml(item.latest_capture || "-")}</td></tr>`).join("");
  const recentRows = bet365Recent.slice(0, 10).map((item) => `
    <tr><td><div class="match-title">${escapeHtml(item.selection)}</div><div class="muted">${escapeHtml(item.team_a || "-")} vs ${escapeHtml(item.team_b || "-")}</div></td><td>${escapeHtml(item.competition || "-")}</td><td class="number">${Number(item.decimal_odds || 0).toFixed(2)}</td><td class="number">${item.normalized_probability == null ? "-" : pct.format(Number(item.normalized_probability))}</td><td>${escapeHtml(item.captured_at || "-")}</td></tr>
  `).join("");
  setHTML("marketDataPanel", `
    ${table(["Metric", "Value"], panelRows)}
    <h4 class="section-title">Odds Sources</h4>
    ${sourceRows ? table(["Source", "Rows", "Fixtures", "Latest"], sourceRows) : `<div class="empty-state">No market odds captured yet.</div>`}
    <h4 class="section-title">Recent Live Odds</h4>
    ${recentRows ? table(["Selection", "Competition", "Odds", "No-vig prob", "Captured"], recentRows) : `<div class="empty-state">No live odds captured yet. Click Fetch Live Odds.</div>`}
  `);
}

function renderEvents(events) {
  renderEventFilters(events);
  const type = state.filters.events.type;
  const filtered = events.filter((event) => type === "all" || event.type === type);
  const items = filtered.map((event) => `<article class="event"><strong>${escapeHtml(event.type)} - ${escapeHtml(shortDateTime(event.timestamp))}</strong><div>${escapeHtml(event.message)}</div></article>`).join("");
  setHTML("eventLog", items || `<div class="empty-state">No events match the selected filter.</div>`);
}

function renderEventFilters(events) {
  const types = Array.from(new Set(events.map((event) => event.type))).sort();
  setHTML("eventFilters", selectControl("eventType", "Type", state.filters.events.type, [["all", "All"], ...types.map((type) => [type, type])]));
}

function metricCard(label, value, sub) {
  return `<article class="metric"><div class="metric-label">${escapeHtml(label)}</div><div class="metric-value">${escapeHtml(value)}</div><div class="metric-sub">${escapeHtml(sub)}</div></article>`;
}

function table(headers, rows) {
  return `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function selectControl(id, label, value, options) {
  return `<label class="select-control" for="${escapeHtml(id)}"><span>${escapeHtml(label)}</span><select id="${escapeHtml(id)}">${options.map(([optionValue, optionLabel]) => `<option value="${escapeHtml(optionValue)}" ${optionValue === value ? "selected" : ""}>${escapeHtml(optionLabel)}</option>`).join("")}</select></label>`;
}

function groupBy(items, key) {
  return items.reduce((acc, item) => {
    const group = item[key];
    acc[group] = acc[group] || [];
    acc[group].push(item);
    return acc;
  }, {});
}

function parseJson(raw) {
  try {
    const parsed = JSON.parse(raw || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function shortDateTime(raw) {
  if (!raw) return "-";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return String(raw);
  return date.toLocaleString();
}

function badgeForDecision(decision) {
  if (decision === "paper_bet" || decision === "healthy" || decision === "cash_out" || decision === "promoted") return "good";
  if (decision === "skip" || decision === "hold" || decision === "retained_incumbent") return "warn";
  if (decision === "needs_attention") return "bad";
  return "warn";
}

function badgeForReadiness(status) {
  if (status === "pass") return "good";
  if (status === "watch") return "warn";
  return "bad";
}

function badgeForAction(status) {
  if (status === "success") return "good";
  if (status === "running") return "warn";
  if (status === "error") return "bad";
  return "warn";
}

function setHTML(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

for (const link of document.querySelectorAll(".nav-link")) link.addEventListener("click", () => switchPage(link.dataset.page));
for (const tab of document.querySelectorAll("#researchTabs .tab")) tab.addEventListener("click", () => switchResearchTab(tab.dataset.tab));

document.addEventListener("change", (event) => {
  if (event.target.id === "oppSource") {
    state.filters.opportunities.source = event.target.value;
    renderOpportunities(state.data || {});
  }
  if (event.target.id === "oppStatus") {
    state.filters.opportunities.status = event.target.value;
    renderOpportunities(state.data || {});
  }
  if (event.target.id === "portfolioStatus") {
    state.filters.portfolio.status = event.target.value;
    renderPortfolio(state.data || {});
  }
  if (event.target.id === "eventType") {
    state.filters.events.type = event.target.value;
    renderEvents((state.data || {}).events || []);
  }
});

document.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-trigger]");
  if (trigger) {
    const target = document.getElementById(trigger.dataset.trigger);
    if (target) target.click();
  }
});

const actionRoutes = {
  runMorning: "/api/morning-run",
  monitorTick: "/api/monitor-tick",
  trainElo: "/api/train-elo",
  trainLogistic: "/api/train-logistic",
  trainWeek3: "/api/train-week3",
  runWeek4: "/api/run-week4",
  fetchBet365Odds: "/api/fetch-live-odds",
  pullLiveData: "/api/pull-live-data",
  settleBets: "/api/settle",
};

for (const [id, route] of Object.entries(actionRoutes)) {
  const button = document.getElementById(id);
  if (button) button.addEventListener("click", () => postAction(route, ACTION_LABELS[id] || id));
}

const reset = document.getElementById("resetDemo");
if (reset) {
  reset.addEventListener("click", () => {
    if (confirm("Reset demo fixtures, paper bets, predictions, and logs?")) postAction("/api/reset-demo", ACTION_LABELS.resetDemo);
  });
}

const initialPage = window.location.hash.replace("#", "");
if (PAGE_TITLES[initialPage]) {
  state.currentPage = initialPage;
  switchPage(initialPage);
}

loadState();
setInterval(() => loadState({ silent: true }), 30000);
