const state = {
  data: null,
  busy: false,
  currentPage: "overview",
};

const gbp = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" });
const pct = new Intl.NumberFormat("en-GB", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });

const ACTION_BUTTON_IDS = [
  "runMorning", "monitorTick", "trainElo", "trainLogistic", "trainWeek3", "runWeek4",
  "fetchBet365Odds", "pullLiveData", "settleBets", "resetDemo",
];

const PIPELINE_STAGES = [
  { key: "data_steward", label: "Chief Data Officer", role: "Checks fixtures, odds, and predictions exist before anything else runs." },
  { key: "bet_decision_agent", label: "Trading Desk", role: "Reads predictions, applies hard risk rules, optionally asks a local LLM to explain, then proposes paper bets." },
  { key: "portfolio_oversight_agent", label: "Chief Risk Officer", role: "Reviews every proposed bet, and vetoes it if data health is flagged or a portfolio-level stake cap is exceeded." },
  { key: "market_watch_agent", label: "Trading Desk — Position Monitoring", role: "Watches open paper bets and simulates cash-out when odds move far enough." },
  { key: "report_writer_agent", label: "Chief Operating Officer", role: "Writes the daily briefing from account state and top model edges." },
  { key: "model_governance_agent", label: "Head of Quant Research", role: "Retrains candidate models on a schedule and only promotes one that actually beats the incumbent." },
];

const PAGE_TITLES = {
  overview: "Cricket model decisions, paper execution, and live monitoring",
  models: "Statistical models: training, calibration, and validation",
  bets: "Agent-placed paper bets and track record",
  data: "Live data feeds, ingestion, and the system event log",
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok || body.ok === false) {
    throw new Error(body.error || "Request failed");
  }
  return body;
}

async function loadState() {
  setBusy(true);
  try {
    state.data = await api("/api/state");
    render();
  } catch (error) {
    alert(error.message);
  } finally {
    setBusy(false);
  }
}

async function postAction(path) {
  setBusy(true);
  try {
    const body = await api(path, { method: "POST" });
    state.data = body.state || state.data;
    if (body.reload_state) {
      state.data = await api("/api/state");
    }
    render();
  } catch (error) {
    alert(error.message);
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

function switchPage(page) {
  state.currentPage = page;
  for (const section of document.querySelectorAll(".page")) {
    section.classList.toggle("active", section.dataset.page === page);
  }
  for (const link of document.querySelectorAll(".nav-link")) {
    link.classList.toggle("active", link.dataset.page === page);
  }
  document.getElementById("pageTitle").textContent = PAGE_TITLES[page] || "";
  window.location.hash = page;
  renderChartsForPage(page);
}

function render() {
  const data = state.data;
  if (!data) return;
  document.getElementById("lastUpdated").textContent = `Updated ${new Date().toLocaleTimeString()}`;

  renderMetrics(data.account);
  renderAutonomousBanner(data.autonomous || {});
  renderAgentPipeline(data.decisions);
  renderBriefing(data.decisions);
  renderReadiness(data.readiness || {});

  renderTrainingData(data.week1 || {}, data.week2 || {});
  renderModelRegistry(data.week3 || {});
  renderBacktestSummary(data.backtesting || {});

  renderMatches(data);
  renderBetsStats(data.paper_bets, (data.week4 || {}).paper_clv || {});
  renderBets(data.paper_bets);
  renderDecisions(data.decisions);
  renderClv((data.week4 || {}).paper_bet_evaluations || []);

  renderDataLogs(data.week4 || {});
  renderEvents(data.events);

  renderChartsForPage(state.currentPage);
}

function renderChartsForPage(page) {
  const charts = (state.data || {}).charts || {};
  const pageCharts = {
    models: ["model_comparison", "calibration", "feature_importance", "elo_ratings", "backtest_pnl", "edge_bucket"],
    bets: ["equity_curve"],
  }[page];
  if (!pageCharts) return;
  for (const key of pageCharts) {
    const spec = charts[key];
    const el = document.getElementById(`chart-${key}`);
    if (!spec || !el || typeof Plotly === "undefined") continue;
    Plotly.react(el, spec.data, spec.layout, { displaylogo: false, responsive: true });
  }
}

function renderMetrics(account) {
  const metrics = [
    ["Bankroll", gbp.format(account.bankroll), `${gbp.format(account.settled_pnl)} settled P&L`],
    ["Available", gbp.format(account.available), "After open paper exposure"],
    ["Open Exposure", gbp.format(account.open_exposure), `${account.open_bets} open bets`],
    ["Mode", "Paper", "Real-money connector disabled"],
  ];
  document.getElementById("overview").innerHTML = metrics.map(([label, value, sub]) => `
    <article class="metric">
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-value">${escapeHtml(value)}</div>
      <div class="metric-sub">${escapeHtml(sub)}</div>
    </article>
  `).join("");
}

function renderAutonomousBanner(autonomous) {
  const dot = document.getElementById("autonomousDot");
  const text = document.getElementById("autonomousText");
  if (!autonomous.enabled) {
    dot.className = "dot bad";
    text.textContent = "Autonomous mode: disabled";
    return;
  }
  if (!autonomous.alive) {
    dot.className = "dot warn";
    text.textContent = "Autonomous mode: starting…";
    return;
  }
  dot.className = "dot";
  const lastTick = autonomous.last_tick_at ? new Date(autonomous.last_tick_at).toLocaleTimeString() : "-";
  const lastRetrain = autonomous.last_retrain_at ? new Date(autonomous.last_retrain_at).toLocaleTimeString() : "never yet";
  text.textContent = `Autonomous mode: running (last tick ${lastTick}, last retrain ${lastRetrain})`;
}

function renderAgentPipeline(decisions) {
  const latestByAgent = {};
  for (const decision of decisions) {
    if (!latestByAgent[decision.agent_name]) latestByAgent[decision.agent_name] = decision;
  }
  const cards = PIPELINE_STAGES.map((stage, index) => {
    const last = latestByAgent[stage.key];
    const status = last
      ? `<div class="pipeline-status"><span class="badge ${badgeForDecision(last.decision)}">${escapeHtml(last.decision)}</span> ${escapeHtml(last.generated_at || "")}</div>
         <div class="pipeline-reason muted">${escapeHtml(last.reason || "")}</div>`
      : `<div class="pipeline-status muted">No runs yet</div>`;
    const arrow = index < PIPELINE_STAGES.length - 1 ? `<div class="pipeline-arrow">&rarr;</div>` : "";
    return `
      <div class="pipeline-stage">
        <div class="pipeline-label">${escapeHtml(stage.label)}</div>
        <div class="pipeline-role muted">${escapeHtml(stage.role)}</div>
        ${status}
      </div>
      ${arrow}
    `;
  }).join("");
  const brokerArrow = `<div class="pipeline-arrow">&rarr;</div>`;
  const broker = `
    <div class="pipeline-stage broker">
      <div class="pipeline-label">Paper Broker</div>
      <div class="pipeline-role muted">Executes, monitors, and settles simulated bets. No real-money connector exists.</div>
    </div>
  `;
  document.getElementById("agentPipeline").innerHTML = cards + brokerArrow + broker;
}

function badgeForDecision(decision) {
  if (decision === "paper_bet" || decision === "healthy" || decision === "cash_out") return "good";
  if (decision === "skip" || decision === "hold") return "warn";
  if (decision === "needs_attention") return "bad";
  return "warn";
}

function renderBriefing(decisions) {
  const briefing = decisions.find((d) => d.agent_name === "report_writer_agent");
  let lines = [];
  if (briefing) {
    try {
      const payload = JSON.parse(briefing.payload_json || "{}");
      lines = payload.briefing || [];
    } catch {
      lines = [];
    }
  }
  if (!lines.length) {
    lines = ["Run Morning to generate the first paper-trading briefing."];
  }
  document.getElementById("briefing").innerHTML = lines.map((line) => `<p>${escapeHtml(line)}</p>`).join("");
}

function renderReadiness(readiness) {
  const summary = readiness.summary || {};
  const items = readiness.items || [];
  if (!items.length) {
    document.getElementById("readinessPanel").innerHTML = `<div class="loading">No readiness report available.</div>`;
    return;
  }
  const summaryRows = `
    <tr><td>Mode</td><td>${escapeHtml(summary.mode || "paper_only")}</td></tr>
    <tr><td>Passes</td><td class="number">${Number(summary.complete || 0)} / ${Number(summary.total || 0)}</td></tr>
    <tr><td>Gaps</td><td class="number">${Number(summary.gaps || 0)}</td></tr>
    <tr><td>Watch</td><td class="number">${Number(summary.watch || 0)}</td></tr>
  `;
  const itemRows = items.map((item) => {
    const badge = item.status === "pass" ? "good" : item.status === "watch" ? "warn" : "bad";
    return `
      <tr>
        <td><span class="badge ${badge}">${escapeHtml(item.status)}</span></td>
        <td>
          <div class="match-title">${escapeHtml(item.label)}</div>
          <div class="muted">${escapeHtml(item.detail)}</div>
        </td>
      </tr>
    `;
  }).join("");
  document.getElementById("readinessPanel").innerHTML = `
    ${table(["Metric", "Value"], summaryRows)}
    ${table(["Status", "Check"], itemRows)}
  `;
}

function renderTrainingData(week1, week2) {
  const cricsheet = week1.cricsheet || {};
  const elo = week1.elo || {};
  const eloPayload = elo.payload || {};
  const logistic = (week2.logistic || {}).payload || {};
  if (!cricsheet.matches) {
    document.getElementById("trainingDataPanel").innerHTML = `<div class="loading">No Cricsheet data ingested yet. Run <code>scripts\\build_data_and_elo.py</code>.</div>`;
    return;
  }
  const rows = `
    <tr><td>Cricsheet matches</td><td class="number">${Number(cricsheet.matches || 0).toLocaleString("en-GB")}</td></tr>
    <tr><td>Date range</td><td>${escapeHtml(cricsheet.first_match || "-")} to ${escapeHtml(cricsheet.latest_match || "-")}</td></tr>
    <tr><td>Teams rated (Elo)</td><td class="number">${Number(eloPayload.teams || 0).toLocaleString("en-GB")}</td></tr>
    <tr><td>Elo last trained</td><td>${escapeHtml((elo.latest_run || {}).generated_at || "-")}</td></tr>
    <tr><td>Logistic feature rows</td><td class="number">${Number(logistic.n_matches || 0).toLocaleString("en-GB")}</td></tr>
  `;
  document.getElementById("trainingDataPanel").innerHTML = table(["Training data", "Value"], rows);
}

function renderModelRegistry(week3) {
  const registry = week3.registry || [];
  if (!registry.length) {
    document.getElementById("modelGovernancePanel").innerHTML = `
      <div class="loading">No model registry yet. Run <code>scripts\\train_and_govern_models.py</code> or click Force Retrain Now.</div>
    `;
    return;
  }
  const rows = registry.map((item) => {
    const badge = Number(item.active) ? "good" : "warn";
    return `
      <tr>
        <td><span class="badge ${badge}">${Number(item.active) ? "active" : escapeHtml(item.status)}</span></td>
        <td>
          <div class="match-title">${escapeHtml(item.model_name)}</div>
          <div class="muted">${escapeHtml(item.timing)} &middot; calibrated: ${Number(item.calibrated) ? "yes" : "no"}</div>
        </td>
      </tr>
    `;
  }).join("");
  document.getElementById("modelGovernancePanel").innerHTML = table(["Status", "Model"], rows);
}

function renderBacktestSummary(backtesting) {
  const payload = backtesting.payload || {};
  if (!payload.bets && payload.message) {
    document.getElementById("backtestSummary").innerHTML = `<div class="loading">${escapeHtml(payload.message)}</div>`;
    document.getElementById("backtestCompetitionPanel").innerHTML = "";
    return;
  }
  const rows = `
    <tr><td>Model</td><td>${escapeHtml(payload.model_name || "-")}</td></tr>
    <tr><td>Candidates / bets</td><td class="number">${Number(payload.n_candidates || 0).toLocaleString("en-GB")} / ${Number(payload.bets || 0).toLocaleString("en-GB")}</td></tr>
    <tr><td>Win rate</td><td class="number">${pct.format(Number(payload.win_rate || 0))}</td></tr>
    <tr><td>Staked / P&amp;L</td><td class="number">${gbp.format(Number(payload.staked || 0))} / ${gbp.format(Number(payload.pnl || 0))}</td></tr>
    <tr><td>ROI / Yield</td><td class="number">${pct.format(Number(payload.roi || 0))}</td></tr>
    <tr><td>Max drawdown</td><td class="number">${gbp.format(Number(payload.max_drawdown || 0))}</td></tr>
  `;
  document.getElementById("backtestSummary").innerHTML = table(["Metric", "Value"], rows);

  const competitionRows = (payload.by_competition || []).slice(0, 8).map((item) => `
    <tr>
      <td>${escapeHtml(item.competition)}</td>
      <td class="number">${Number(item.bets || 0).toLocaleString("en-GB")}</td>
      <td class="number">${gbp.format(Number(item.pnl || 0))}</td>
      <td class="number">${pct.format(Number(item.roi || 0))}</td>
    </tr>
  `).join("");
  document.getElementById("backtestCompetitionPanel").innerHTML = competitionRows
    ? table(["Competition", "Bets", "P&L", "ROI"], competitionRows)
    : `<div class="loading">No backtest bets met the edge threshold.</div>`;
}

function renderMatches(data) {
  const predictionsByFixture = groupBy(data.predictions, "fixture_id");
  const rows = data.fixtures.map((fixture) => {
    const preds = (predictionsByFixture[fixture.id] || []).sort((a, b) => b.edge - a.edge);
    const best = preds[0];
    const edge = best ? Number(best.edge) : 0;
    const badge = edge >= 0.05 ? "good" : edge >= 0.02 ? "warn" : "bad";
    return `
      <tr>
        <td>
          <div class="match-title">${escapeHtml(fixture.team_a)} vs ${escapeHtml(fixture.team_b)}</div>
          <div class="muted">${escapeHtml(fixture.competition)} - ${escapeHtml(fixture.venue)}</div>
          ${best ? modelSourceBadge(best) : ""}
        </td>
        <td class="number">${escapeHtml(fixture.match_date)} ${escapeHtml(fixture.start_time)}</td>
        <td>${best ? escapeHtml(best.selection) : "<span class='muted'>Run model</span>"}</td>
        <td class="number">${best ? pct.format(Number(best.probability)) : "-"}</td>
        <td class="number">${best ? Number(best.fair_odds).toFixed(2) : "-"}</td>
        <td class="number">${best ? Number(best.market_odds).toFixed(2) : "-"}</td>
        <td><span class="badge ${badge}">${best ? pct.format(edge) : "No model"}</span></td>
        <td class="number">${best ? pct.format(Number(best.confidence)) : "-"}</td>
      </tr>
    `;
  }).join("");
  document.getElementById("matchesTable").innerHTML = table([
    "Match", "Start", "Model side", "Prob", "Fair", "Market", "Edge", "Confidence"
  ], rows);
}

function modelSourceBadge(prediction) {
  let source = "";
  try {
    source = (JSON.parse(prediction.features_json || "{}") || {}).feature_source || "";
  } catch {
    source = "";
  }
  if (source === "trained_pretoss_logistic") {
    return `<div class="source-tag good">Trained model (${escapeHtml(prediction.model_name)})</div>`;
  }
  if (source === "deterministic_demo_features") {
    return `<div class="source-tag muted">Demo placeholder &mdash; not bettable</div>`;
  }
  return "";
}

function renderBetsStats(bets, clv) {
  const closed = bets.filter((b) => b.status === "settled" || b.status === "cashed_out");
  const wins = closed.filter((b) => Number(b.pnl) > 0).length;
  const totalPnl = closed.reduce((sum, b) => sum + Number(b.pnl), 0);
  const winRate = closed.length ? wins / closed.length : 0;
  const avgClv = clv.avg_clv == null ? null : Number(clv.avg_clv);
  const cards = [
    ["Settled Bets", closed.length.toLocaleString("en-GB"), `${bets.filter((b) => b.status === "open").length} still open`],
    ["Hit Rate", closed.length ? pct.format(winRate) : "-", `${wins} of ${closed.length} won`],
    ["Realized P&L", gbp.format(totalPnl), totalPnl >= 0 ? "Net positive so far" : "Net negative so far"],
    ["Avg CLV", avgClv == null ? "-" : pct.format(avgClv), "Entry vs closing-price proxy"],
  ];
  document.getElementById("betsStats").innerHTML = cards.map(([label, value, sub]) => `
    <article class="metric">
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-value">${escapeHtml(value)}</div>
      <div class="metric-sub">${escapeHtml(sub)}</div>
    </article>
  `).join("");
}

function renderBets(bets) {
  if (!bets.length) {
    document.getElementById("betsTable").innerHTML = `<div class="loading">No paper bets yet. Run Morning to let the decision agent review model edges.</div>`;
    return;
  }
  const rows = bets.map((bet) => {
    const badge = bet.status === "open" ? "warn" : Number(bet.pnl) >= 0 ? "good" : "bad";
    return `
      <tr>
        <td>
          <div class="match-title">${escapeHtml(bet.selection)}</div>
          <div class="muted">${escapeHtml(bet.team_a)} vs ${escapeHtml(bet.team_b)}</div>
        </td>
        <td>${escapeHtml(bet.market)}</td>
        <td class="number">${gbp.format(Number(bet.stake))}</td>
        <td class="number">${Number(bet.odds).toFixed(2)}</td>
        <td><span class="badge ${badge}">${escapeHtml(bet.status)}</span></td>
        <td class="number">${gbp.format(Number(bet.pnl))}</td>
        <td>${escapeHtml(bet.notes || "")}</td>
      </tr>
    `;
  }).join("");
  document.getElementById("betsTable").innerHTML = table(["Selection", "Market", "Stake", "Odds", "Status", "P&L", "Notes"], rows);
}

function renderDecisions(decisions) {
  const items = decisions.slice(0, 12).map((decision) => {
    const match = decision.team_a ? `${decision.team_a} vs ${decision.team_b}` : "System";
    return `
      <article class="decision">
        <strong>${escapeHtml(decision.agent_name)} - ${escapeHtml(decision.decision)}</strong>
        <div class="muted">${escapeHtml(match)} - ${escapeHtml(decision.generated_at)}</div>
        <div>${escapeHtml(decision.reason)}</div>
      </article>
    `;
  }).join("");
  document.getElementById("decisionsList").innerHTML = items || `<div class="loading">No agent decisions yet.</div>`;
}

function renderClv(evaluations) {
  const rows = evaluations.map((item) => `
    <tr>
      <td>${escapeHtml(item.selection)}</td>
      <td>${escapeHtml(item.team_a)} vs ${escapeHtml(item.team_b)}</td>
      <td class="number">${Number(item.entry_odds || 0).toFixed(2)}</td>
      <td class="number">${item.closing_odds ? Number(item.closing_odds).toFixed(2) : "-"}</td>
      <td class="number">${item.clv == null ? "-" : pct.format(Number(item.clv))}</td>
    </tr>
  `).join("");
  document.getElementById("clvPanel").innerHTML = rows
    ? table(["Selection", "Match", "Entry", "Close", "CLV"], rows)
    : `<div class="loading">No paper CLV evaluations yet. Run Rebuild Market Data after paper bets and odds snapshots exist.</div>`;
}

function renderDataLogs(week4) {
  const counts = week4.market_counts || {};
  const bet365 = week4.bet365_status || {};
  const sourceCounts = week4.source_counts || [];
  const bet365Recent = week4.bet365_recent_odds || [];
  const liveOddsBadge = bet365.configured
    ? `<span class="badge good">configured</span>`
    : `<span class="badge bad">missing key</span>`;
  const bet365ErrorText = (bet365.latest_errors || [])
    .map((item) => `${item.stage || "fetch"}: ${item.error || "error"}`)
    .join(" | ");
  const freshness = bet365.freshness || {};
  const panelRows = `
    <tr><td>Live odds feed</td><td>${liveOddsBadge} ${escapeHtml(bet365.latest_capture || "No captured odds yet")}</td></tr>
    <tr><td>Provider</td><td>${escapeHtml(bet365.provider || "Live odds aggregator")}</td></tr>
    <tr><td>Fallback used</td><td>${bet365.fallback_used ? "<span class='badge good'>yes</span>" : "<span class='badge warn'>no</span>"}</td></tr>
    <tr><td>Feed freshness</td><td><span class="badge ${bet365.is_fresh ? "good" : "warn"}">${escapeHtml(bet365.freshness_status || "unknown")}</span> ${freshness.minutes_old == null ? "" : `${Number(freshness.minutes_old).toFixed(1)} min old`}</td></tr>
    <tr><td>Latest fetch</td><td>${escapeHtml(bet365.latest_fetch_at || "-")}</td></tr>
    <tr><td>Events checked</td><td class="number">${Number(bet365.events_checked || 0).toLocaleString("en-GB")}</td></tr>
    <tr><td>Rows inserted last fetch</td><td class="number">${Number(bet365.odds_rows_inserted || 0).toLocaleString("en-GB")}</td></tr>
    <tr><td>Latest odds status</td><td>${escapeHtml(bet365.latest_message || "No fetch attempted yet")}</td></tr>
    <tr><td>Latest odds error</td><td>${escapeHtml(bet365ErrorText || "-")}</td></tr>
    <tr><td>Market odds rows</td><td class="number">${Number(counts.odds_rows || 0).toLocaleString("en-GB")}</td></tr>
    <tr><td>Fixtures with odds</td><td class="number">${Number(counts.fixtures || 0).toLocaleString("en-GB")}</td></tr>
  `;
  const sourceRows = sourceCounts.map((item) => `
    <tr>
      <td>${escapeHtml(item.source)}</td>
      <td class="number">${Number(item.odds_rows || 0).toLocaleString("en-GB")}</td>
      <td class="number">${Number(item.fixtures || 0).toLocaleString("en-GB")}</td>
      <td>${escapeHtml(item.latest_capture || "-")}</td>
    </tr>
  `).join("");
  const recentRows = bet365Recent.slice(0, 10).map((item) => `
    <tr>
      <td>
        <div class="match-title">${escapeHtml(item.selection)}</div>
        <div class="muted">${escapeHtml(item.team_a || "-")} vs ${escapeHtml(item.team_b || "-")}</div>
      </td>
      <td>${escapeHtml(item.competition || "-")}</td>
      <td class="number">${Number(item.decimal_odds || 0).toFixed(2)}</td>
      <td class="number">${item.normalized_probability == null ? "-" : pct.format(Number(item.normalized_probability))}</td>
      <td>${escapeHtml(item.captured_at || "-")}</td>
    </tr>
  `).join("");
  document.getElementById("marketDataPanel").innerHTML = `
    ${table(["Metric", "Value"], panelRows)}
    <h4 class="section-title">Odds Sources</h4>
    ${sourceRows ? table(["Source", "Rows", "Fixtures", "Latest"], sourceRows) : `<div class="loading">No market odds captured yet.</div>`}
    <h4 class="section-title">Recent Live Odds</h4>
    ${recentRows ? table(["Selection", "Competition", "Odds", "No-vig prob", "Captured"], recentRows) : `<div class="loading">No live odds captured yet. Click Fetch Live Odds.</div>`}
    <p class="small-inline-note">Generated odds are only used for demo fixtures. Bet365 and The Odds API snapshots are treated as real bookmaker context when fresh.</p>
  `;
}

function renderEvents(events) {
  const items = events.map((event) => `
    <article class="event">
      <strong>${escapeHtml(event.type)} - ${escapeHtml(event.timestamp)}</strong>
      <div>${escapeHtml(event.message)}</div>
    </article>
  `).join("");
  document.getElementById("eventLog").innerHTML = items || `<div class="loading">No events yet.</div>`;
}

function table(headers, rows) {
  return `
    <div class="table-wrap">
      <table>
        <thead><tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function groupBy(items, key) {
  return items.reduce((acc, item) => {
    const group = item[key];
    acc[group] = acc[group] || [];
    acc[group].push(item);
    return acc;
  }, {});
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

for (const link of document.querySelectorAll(".nav-link")) {
  link.addEventListener("click", () => switchPage(link.dataset.page));
}

document.getElementById("runMorning").addEventListener("click", () => postAction("/api/morning-run"));
document.getElementById("monitorTick").addEventListener("click", () => postAction("/api/monitor-tick"));
document.getElementById("trainElo").addEventListener("click", () => postAction("/api/train-elo"));
document.getElementById("trainLogistic").addEventListener("click", () => postAction("/api/train-logistic"));
document.getElementById("trainWeek3").addEventListener("click", () => postAction("/api/train-week3"));
document.getElementById("runWeek4").addEventListener("click", () => postAction("/api/run-week4"));
document.getElementById("fetchBet365Odds").addEventListener("click", () => postAction("/api/fetch-live-odds"));
document.getElementById("pullLiveData").addEventListener("click", () => postAction("/api/pull-live-data"));
document.getElementById("settleBets").addEventListener("click", () => postAction("/api/settle"));
document.getElementById("resetDemo").addEventListener("click", () => {
  if (confirm("Reset demo fixtures, paper bets, predictions, and logs?")) {
    postAction("/api/reset-demo");
  }
});

const initialPage = window.location.hash.replace("#", "");
if (PAGE_TITLES[initialPage]) {
  switchPage(initialPage);
}

loadState();
setInterval(loadState, 30000);
