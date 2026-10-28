const state = { loads: [], summary: {}, filtered: [], deploymentMode: "server", recordedRunLoadId: null };
const DECISIONS_KEY = "haulage-brain-demo-decisions";
const analysisUI = { seen: 0, pollTimer: null, replayTimers: [], market: null, tools: null, specialists: 0 };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const money = (value) => {
  const amount = Number(value || 0);
  const formatted = Math.abs(amount).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${amount < 0 ? "-" : ""}£${formatted}`;
};
const signedMoney = (value) => `${Number(value) >= 0 ? "+" : ""}${money(value)}`;
const cssClass = (value) => String(value).toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
const fallback = (value) => value === null || value === undefined || value === "" ? "Not supplied" : value;

function dateTime(value) {
  if (!value) return "Not supplied";
  const date = new Date(value);
  return date.toLocaleString("en-GB", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function pickupLabel(pickup = {}) {
  if (pickup.type === "window") {
    const start = dateTime(pickup.start);
    const end = new Date(pickup.end).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    return `${start}–${end}`;
  }
  const prefix = pickup.type === "before" ? "Before " : "";
  return prefix + dateTime(pickup.time);
}

function deliveryLabel(deliver) {
  if (typeof deliver === "string") return deliver;
  if (!deliver) return "Not supplied";
  return `${deliver.type === "by" ? "By " : ""}${dateTime(deliver.time || deliver.start)}`;
}

function locationBlock(location = {}) {
  return `<div><div class="company">${escapeHtml(fallback(location.name))}</div>
    <div class="address">${escapeHtml(fallback(location.address))}<br><span class="place">${escapeHtml(fallback(location.town))}, ${escapeHtml(fallback(location.postcode))}</span></div></div>`;
}

function notes(load) {
  const values = load.load_notes || [];
  return values.length ? values.map(escapeHtml).join(" · ") : "No special instructions";
}

function tracking(load) {
  const item = load.tracking;
  if (!item) return "";
  return `<div class="tracking">
    <dl><dt>On site pickup</dt><dd>${escapeHtml(dateTime(item.on_site_pickup))}</dd><dt>Loaded</dt><dd>${escapeHtml(dateTime(item.loaded_at))}</dd></dl>
    <dl><dt>On site delivery</dt><dd>${escapeHtml(dateTime(item.on_site_delivery))}</dd><dt>Delivered</dt><dd>${escapeHtml(dateTime(item.delivered_on))}</dd></dl>
    <dl><dt>Received by</dt><dd>${escapeHtml(fallback(item.received_by))}</dd><dt>Delivery status</dt><dd>${escapeHtml(fallback(item.delivery_status))}</dd></dl>
  </div>`;
}

function quotePanel(load) {
  if (load.status !== "Available") return tracking(load);
  const q = load.quote_analysis;
  const decided = load.ledger?.status;
  const differenceClass = q.difference_gbp >= 0 ? "positive" : "negative";
  const recommendation = q.recommendation === "REPRICE" ? "REPRICE" : q.recommendation;
  const isStatic = state.deploymentMode === "static-demo";
  const canReplay = String(load.load_id) === String(state.recordedRunLoadId);
  const analysisDisabled = isStatic && !canReplay;
  const analysisLabel = isStatic ? (canReplay ? "Replay API run" : "Live backend required") : "Watch live APIs";
  const analysisButton = `<button class="watch-analysis" data-analyze="${escapeHtml(load.load_id)}" ${analysisDisabled ? "disabled" : ""} title="${analysisDisabled ? `Recorded replay is available on load ${escapeHtml(state.recordedRunLoadId || "not captured")}` : "Show CrewAI, You.com and Parasail working on this load"}">${analysisLabel}</button>`;
  const decisionControls = decided
    ? `<div class="ledger-result"><span class="label">Manager decision</span><br><strong>${escapeHtml(decided)}</strong></div>`
    : `<button class="approve" data-action="APPROVE" data-id="${escapeHtml(load.load_id)}">Approve</button><button class="pass" data-action="PASS" data-id="${escapeHtml(load.load_id)}">Pass</button>`;
  const actions = `<div class="actions">${analysisButton}${decisionControls}</div>`;
  return `<div class="quote-panel">
    <div>
      <div class="quote-values">
        <div class="quote-value"><span>PRD quote</span><strong>${money(q.total)}</strong></div>
        <div class="quote-value"><span>Posted rate</span><strong>${money(q.offered_rate_gbp)}</strong></div>
        <div class="quote-value"><span>Rate vs quote</span><strong class="${differenceClass}">${signedMoney(q.difference_gbp)}</strong></div>
        <div class="quote-value"><span>Pricing signal</span><strong class="recommendation ${recommendation}">${escapeHtml(recommendation)}</strong></div>
      </div>
      <div class="breakdown">
        <span class="chip">${q.billed_minutes} billed minutes</span><span class="chip">Base ${money(q.base)}</span><span class="chip">Fuel tier ${money(q.fuel)}</span><span class="chip">London ${money(q.city)}</span>${q.minimum_applied ? '<span class="chip">Minimum applied</span>' : ""}${load.ulez ? '<span class="chip">ULEZ flagged</span>' : ""}
      </div>
    </div>${actions}
  </div>`;
}

function card(load) {
  const statusClass = cssClass(load.status);
  const pillClass = cssClass(load.status);
  const rateDisplay = $("#per-mile").checked ? `${money(load.rate_per_mile)}/mile` : money(load.agreed_rate_gbp);
  return `<article class="load-card ${statusClass}" data-load-id="${escapeHtml(load.load_id)}">
    <div class="card-top">
      <div>
        <div class="route-stop"><span class="label">From:</span>${locationBlock(load.from_)}</div>
        <div class="route-stop"><span class="label">To:</span>${locationBlock(load.to)}</div>
      </div>
      <div class="schedule"><span class="label">Pickup:</span><strong>${escapeHtml(pickupLabel(load.pickup))}</strong><span class="label">Deliver:</span><strong>${escapeHtml(deliveryLabel(load.deliver))}</strong></div>
      <div class="status-panel"><span class="status-pill ${pillClass}">${escapeHtml(load.status)}</span><span class="load-id">Load ID: ${escapeHtml(load.load_id)}</span><span class="vehicle">${escapeHtml(load.vehicle_requested)}</span></div>
    </div>
    <div class="detail-grid">
      <dl><dt>Booked by</dt><dd>${escapeHtml(fallback(load.booked_by_company))}</dd><dt>Phone</dt><dd>${escapeHtml(fallback(load.phone))}</dd><dt>Agreed rate</dt><dd>${rateDisplay}</dd><dt>Ref</dt><dd>${escapeHtml(fallback(load.ref))}</dd></dl>
      <dl><dt>Distance</dt><dd>${escapeHtml(load.distance_miles)} miles</dd><dt>Weight</dt><dd>${load.weight_kg == null ? "Not supplied" : `${escapeHtml(load.weight_kg)} kg`}</dd><dt>Packaging</dt><dd>${escapeHtml(fallback(load.packaging))}</dd><dt>Dims</dt><dd>${escapeHtml(fallback(load.dims))}</dd></dl>
      <dl><dt>Requested</dt><dd>${escapeHtml(load.vehicle_requested)}</dd><dt>Payment terms</dt><dd>${escapeHtml(load.payment_terms)}</dd><dt>Category</dt><dd>${escapeHtml(load.category)}</dd><dt>Flag</dt><dd>${escapeHtml(fallback(load.flag))}</dd></dl>
    </div>
    <div class="notes"><strong>Load notes:</strong> ${notes(load)}</div>
    ${quotePanel(load)}
  </article>`;
}

function populateFilters() {
  const statuses = [...new Set(state.loads.map((load) => load.status))].sort();
  const vehicles = [...new Set(state.loads.map((load) => load.vehicle_requested))].sort();
  $("#status").insertAdjacentHTML("beforeend", statuses.map((value) => `<option>${escapeHtml(value)}</option>`).join(""));
  $("#vehicle").insertAdjacentHTML("beforeend", vehicles.map((value) => `<option>${escapeHtml(value)}</option>`).join(""));
}

function renderSummary() {
  const s = state.summary;
  $("#summary").innerHTML = `<div><dt>Loads</dt><dd>${s.loads}</dd></div><div><dt>Available</dt><dd>${s.available}</dd></div><div><dt>Avg rate</dt><dd>£${Number(s.average_rate_gbp).toFixed(0)}</dd></div><div><dt>Avg £/mile</dt><dd>£${Number(s.average_rate_per_mile_gbp).toFixed(2)}</dd></div>`;
}

function applyFilters() {
  const query = $("#search").value.trim().toLowerCase();
  const status = $("#status").value;
  const vehicle = $("#vehicle").value;
  const sort = $("#sort").value;
  state.filtered = state.loads.filter((load) => {
    const haystack = JSON.stringify([load.load_id, load.from_, load.to, load.load_notes, load.booked_by_company]).toLowerCase();
    return (!query || haystack.includes(query)) && (!status || load.status === status) && (!vehicle || load.vehicle_requested === vehicle);
  });
  const pickupValue = (load) => new Date(load.pickup?.time || load.pickup?.start || 0).getTime();
  state.filtered.sort((a, b) => sort === "rate-desc" ? b.agreed_rate_gbp - a.agreed_rate_gbp : sort === "rate-asc" ? a.agreed_rate_gbp - b.agreed_rate_gbp : sort === "distance" ? a.distance_miles - b.distance_miles : pickupValue(a) - pickupValue(b));
  $("#result-count").textContent = `Showing ${state.filtered.length} of ${state.loads.length} loads`;
  $("#loads").innerHTML = state.filtered.length ? state.filtered.map(card).join("") : '<div class="empty">No loads match these filters.</div>';
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = error ? "show error" : "show";
  setTimeout(() => { element.className = ""; }, 3200);
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? escapeHtml(url.href) : "#";
  } catch (_) {
    return "#";
  }
}

function resetAnalysis(loadId, recorded = false) {
  if (analysisUI.pollTimer) clearTimeout(analysisUI.pollTimer);
  analysisUI.replayTimers.forEach(clearTimeout);
  Object.assign(analysisUI, { seen: 0, pollTimer: null, replayTimers: [], market: null, tools: null, specialists: 0 });
  document.querySelectorAll(".pipeline-stage").forEach((item) => item.classList.remove("active", "done", "failed"));
  $("#analysis-events").innerHTML = "";
  $("#analysis-impact").innerHTML = "<p>Waiting for live market evidence…</p>";
  $("#run-metrics").innerHTML = "";
  $("#analysis-title").textContent = `${recorded ? "Recorded API run" : "Live API analysis"} · Load ${loadId}`;
  $("#analysis-notice").textContent = recorded
    ? "Verified live run replay. Timestamps and API outputs were captured from the local backend; nothing will be booked."
    : "Running real provider calls with synthetic demo fleet economics. Nothing will be booked or sent to Discord.";
  $("#run-mode").textContent = recorded ? "RECORDED LIVE" : "LIVE";
  $("#run-mode").className = recorded ? "run-mode recorded" : "run-mode";
}

function setStage(name, status) {
  const stage = document.querySelector(`.pipeline-stage[data-stage="${name}"]`);
  if (!stage) return;
  stage.classList.remove("active", "done", "failed");
  stage.classList.add(status);
}

function updateStage(event) {
  const type = event.type;
  if (type === "run.started" || type === "crewai.ingest.completed") setStage("crewai", "active");
  if (type === "crewai.route.completed") setStage("crewai", "done");
  if (type === "you.grounding.started") setStage("you", "active");
  if (type === "you.grounding.completed") setStage("you", "done");
  if (type === "tools.assessment.completed") setStage("tools", "done");
  if (type.startsWith("parasail.")) setStage("parasail", type === "parasail.supervisor.completed" ? "done" : "active");
  if (type === "safety.gate.completed") setStage("decision", "done");
  if (type === "one.approval.pending") setStage("one", "active");
  if (type === "run.failed") {
    const active = document.querySelector(".pipeline-stage.active");
    if (active) { active.classList.remove("active"); active.classList.add("failed"); }
  }
}

function eventPresentation(event) {
  const d = event.data || {};
  const role = escapeHtml(String(d.role || "").replace("fleet-fit", "fleet fit"));
  switch (event.type) {
    case "run.started": return ["Analysis started", escapeHtml(d.fleet_notice), ""];
    case "crewai.ingest.completed": return ["CrewAI ingested load", `${d.selected_count} selected from ${d.source_count} fixture records`, "done"];
    case "crewai.route.completed": return ["CrewAI routed load", escapeHtml(Object.keys(d.route_counts || {}).join(", ")), "done"];
    case "you.grounding.started": return ["You.com research started", (d.research || []).map(escapeHtml).join(" · "), ""];
    case "you.grounding.completed": {
      const citation = (d.citations || [])[0];
      const source = citation ? `<a href="${safeUrl(citation.url)}" target="_blank" rel="noreferrer">${escapeHtml(citation.title)}</a>` : "No citation";
      return ["You.com grounded market facts", `<strong>${Number(d.diesel_price_ppl).toFixed(2)}p/L diesel</strong> · ${d.citations?.length || 0} citations · ${source}`, "done"];
    }
    case "tools.assessment.completed": return ["Deterministic quote calculated", `<strong>${money(d.target_quote_gbp)}</strong> target · ${Number(d.offered_margin_pct).toFixed(1)}% offered margin · live-data effect ${signedMoney(d.live_quote_delta_gbp)}`, "done"];
    case "parasail.specialist.started": return [`Parasail ${role} specialist`, `${escapeHtml(d.model)} is analyzing scoped evidence…`, ""];
    case "parasail.specialist.completed": return [`Parasail ${role} completed`, `${Number(d.elapsed_seconds).toFixed(1)}s · ${escapeHtml(String(d.summary || "").slice(0, 260))}`, "done"];
    case "parasail.supervisor.started": return ["Parasail supervisor", `${escapeHtml(d.model)} is reconciling the specialists…`, ""];
    case "parasail.supervisor.completed": return ["Parasail supervisor completed", `<strong>${escapeHtml(d.recommendation)}</strong> · ${Number(d.elapsed_seconds).toFixed(1)}s · ${escapeHtml(String(d.rationale || "").slice(0, 220))}`, "done"];
    case "safety.gate.completed": return ["Safety gate applied", `Model: ${escapeHtml(d.model_recommendation)} · deterministic eligible: ${d.deterministic_eligible ? "yes" : "no"} · final: <strong>${escapeHtml(d.final_recommendation)}</strong>`, "done"];
    case "one.approval.pending": return ["One / Discord handoff", escapeHtml(d.message), ""];
    case "run.completed": return ["Analysis complete", `${Number(d.elapsed_seconds).toFixed(1)}s · ${d.inference_usage?.requests || 0} Parasail calls · recommendation <strong>${escapeHtml(d.recommendation)}</strong>`, "done"];
    case "run.failed": return ["Analysis failed", escapeHtml(d.error), "failed"];
    default: return [escapeHtml(event.type), "", ""];
  }
}

function renderImpact() {
  const market = analysisUI.market;
  const tools = analysisUI.tools;
  if (!market && !tools) return;
  const citations = market?.citations || [];
  const citationList = citations.slice(0, 3).map((item) => `<li><a href="${safeUrl(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a></li>`).join("");
  $("#analysis-impact").innerHTML = `${market ? `<div class="impact-price"><span>You.com diesel input</span><strong>${Number(market.diesel_price_ppl).toFixed(2)}p/L</strong></div>` : ""}
    ${tools ? `<div class="impact-price"><span>145p demo baseline quote</span><strong>${money(tools.baseline_target_quote_gbp)}</strong></div>
      <div class="impact-price"><span>Live grounded quote</span><strong>${money(tools.target_quote_gbp)}</strong></div>
      <div class="impact-price delta"><span>You.com price impact</span><strong>${signedMoney(tools.live_quote_delta_gbp)}</strong></div>
      <div class="impact-price"><span>Posted rate / margin</span><strong>${money(tools.offered_rate_gbp)} · ${Number(tools.offered_margin_pct).toFixed(1)}%</strong></div>` : ""}
    ${citationList ? `<ul class="impact-citations">${citationList}</ul>` : ""}`;
}

function renderMetrics(data) {
  const usage = data.inference_usage || {};
  const tokens = Number(usage.prompt_tokens || 0) + Number(usage.completion_tokens || 0);
  $("#run-metrics").innerHTML = `<div><span>Elapsed</span><strong>${Number(data.elapsed_seconds || 0).toFixed(1)}s</strong></div><div><span>Parasail calls</span><strong>${usage.requests || 0}</strong></div><div><span>Tokens</span><strong>${tokens.toLocaleString("en-GB")}</strong></div>`;
}

function renderTraceEvent(event) {
  updateStage(event);
  if (event.type === "you.grounding.completed") analysisUI.market = event.data;
  if (event.type === "tools.assessment.completed") analysisUI.tools = event.data;
  if (event.type === "parasail.specialist.completed") analysisUI.specialists += 1;
  if (event.type === "run.completed") renderMetrics(event.data || {});
  renderImpact();
  const [label, detail, className] = eventPresentation(event);
  const elapsed = `${(Number(event.elapsed_ms || 0) / 1000).toFixed(1)}s`;
  $("#analysis-events").insertAdjacentHTML("beforeend", `<li class="event-item ${className}"><div class="event-label"><span>${label}</span><time>+${elapsed}</time></div>${detail ? `<div class="event-detail">${detail}</div>` : ""}</li>`);
  $("#analysis-events").scrollTop = $("#analysis-events").scrollHeight;
}

async function pollAnalysis(runId) {
  try {
    const response = await fetch(`api/runs/${encodeURIComponent(runId)}?v=${Date.now()}`, { cache: "no-store" });
    const run = await response.json();
    if (!response.ok) throw new Error(run.error || "Could not read analysis run");
    run.events.slice(analysisUI.seen).forEach(renderTraceEvent);
    analysisUI.seen = run.events.length;
    if (run.status === "RUNNING") {
      analysisUI.pollTimer = setTimeout(() => pollAnalysis(runId), 450);
    } else if (run.status === "FAILED") {
      toast(run.error || "Live analysis failed", true);
    }
  } catch (error) {
    toast(error.message, true);
  }
}

function replayAnalysis(run) {
  const events = run.events || [];
  events.forEach((item, index) => {
    const timer = setTimeout(() => renderTraceEvent(item), 180 + index * 320);
    analysisUI.replayTimers.push(timer);
  });
}

async function analyzeLoad(loadId) {
  const recorded = state.deploymentMode === "static-demo";
  resetAnalysis(loadId, recorded);
  $("#analysis-dialog").showModal();
  try {
    if (recorded) {
      const response = await fetch(`api/demo-run?v=${Date.now()}`, { cache: "no-store" });
      const run = await response.json();
      if (!response.ok) throw new Error(run.error || "Recorded run is unavailable");
      replayAnalysis(run);
      return;
    }
    const response = await fetch("api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ load_id: loadId }) });
    const run = await response.json();
    if (!response.ok) throw new Error(run.error || "Could not start live analysis");
    pollAnalysis(run.run_id);
  } catch (error) {
    renderTraceEvent({ type: "run.failed", elapsed_ms: 0, data: { error: error.message } });
    toast(error.message, true);
  }
}

async function decide(loadId, decision, button) {
  button.disabled = true;
  try {
    if (state.deploymentMode === "static-demo") {
      const decisions = JSON.parse(localStorage.getItem(DECISIONS_KEY) || "{}");
      const result = {
        load_id: loadId,
        status: decision === "APPROVE" ? "BOOKED" : "PASSED",
        human_decision: decision,
        manager: $("#manager").value.trim() || "Fleet Manager",
        at: new Date().toISOString(),
      };
      decisions[`Q-${loadId}`] = result;
      localStorage.setItem(DECISIONS_KEY, JSON.stringify(decisions));
      const load = state.loads.find((item) => String(item.load_id) === String(loadId));
      if (load) load.ledger = result;
      toast(`${loadId}: ${result.status} by ${result.manager} (browser demo)`);
      applyFilters();
      return;
    }
    const response = await fetch("api/decision", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ load_id: loadId, decision, manager: $("#manager").value }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Decision failed");
    toast(`${loadId}: ${result.status} by ${result.manager}`);
    await loadData(false);
  } catch (error) {
    button.disabled = false;
    toast(error.message, true);
  }
}

async function loadData(initial = true) {
  const response = await fetch(`api/loads?v=${Date.now()}`, { cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not load fixture");
  state.deploymentMode = data.deployment?.mode || "server";
  state.recordedRunLoadId = data.deployment?.recorded_run_load_id || null;
  state.loads = data.loads;
  if (state.deploymentMode === "static-demo") {
    const decisions = JSON.parse(localStorage.getItem(DECISIONS_KEY) || "{}");
    state.loads.forEach((load) => { load.ledger = decisions[`Q-${load.load_id}`] || null; });
    $(".environment").textContent = "GitHub Pages demo · decisions stay in this browser";
  }
  state.summary = data.summary;
  renderSummary();
  if (initial) populateFilters();
  applyFilters();
}

document.addEventListener("DOMContentLoaded", async () => {
  $("#manager").value = localStorage.getItem("haulage-brain-manager") || "Fleet Manager";
  $("#manager").addEventListener("change", (event) => localStorage.setItem("haulage-brain-manager", event.target.value));
  ["#search", "#status", "#vehicle", "#sort", "#per-mile"].forEach((selector) => $(selector).addEventListener(selector === "#search" ? "input" : "change", applyFilters));
  $("#loads").addEventListener("click", (event) => {
    const analysisButton = event.target.closest("button[data-analyze]");
    if (analysisButton) {
      analyzeLoad(analysisButton.dataset.analyze);
      return;
    }
    const button = event.target.closest("button[data-action]");
    if (button) decide(button.dataset.id, button.dataset.action, button);
  });
  $("#raw-json").addEventListener("click", () => { $("#json-content").textContent = JSON.stringify(state.loads.map(({ quote_analysis, ledger, ...load }) => load), null, 2); $("#json-dialog").showModal(); });
  $("#close-dialog").addEventListener("click", () => $("#json-dialog").close());
  $("#close-analysis").addEventListener("click", () => {
    if (analysisUI.pollTimer) clearTimeout(analysisUI.pollTimer);
    analysisUI.replayTimers.forEach(clearTimeout);
    $("#analysis-dialog").close();
  });
  try { await loadData(); } catch (error) { $("#loads").innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`; toast(error.message, true); }
});
