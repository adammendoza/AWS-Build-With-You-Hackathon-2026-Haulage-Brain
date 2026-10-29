const state = {
  loads: [],
  filtered: [],
  selectedId: null,
  deploymentMode: "server",
  signal: "all",
  view: "queue",
  pending: null,
  busy: false,
};
const analysisUI = {
  seen: 0,
  pollTimer: null,
  replayTimers: [],
  market: null,
  tools: null,
  specialists: 0,
};
const MANAGER_KEY = "haulage-brain-manager";
const DEFAULT_MANAGER = "Fleet Manager";
const DECISIONS_KEY = "haulage-brain-demo-decisions";
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
const money = (value) =>
  new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    minimumFractionDigits: 2,
  }).format(Number(value || 0));
const signedMoney = (value) =>
  `${Number(value) >= 0 ? "+" : "−"}${money(Math.abs(Number(value)))}`;
const fallback = (value) =>
  value == null || value === "" ? "Not supplied" : value;
const titleCase = (value) =>
  String(value || "Unknown")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
const signalName = (value) =>
  ({
    APPROVE: "Above quote",
    REPRICE: "Reprice",
    REVIEW: "Needs review",
    BOOKED: "Approved",
    PASSED: "Passed",
  })[value] || value;
const signalClass = (value) =>
  ({
    APPROVE: "approve",
    REPRICE: "reprice",
    REVIEW: "review",
    BOOKED: "booked",
    PASSED: "passed",
  })[value] || "review";
const badge = (value) =>
  `<span class="signal ${signalClass(value)}">${escapeHtml(signalName(value))}</span>`;
const isDecided = (load) => ["BOOKED", "PASSED"].includes(load.ledger?.status);
const selectedLoad = () =>
  state.loads.find((load) => String(load.load_id) === state.selectedId);
function dateTime(value, compact = false) {
  if (!value) return "Not supplied";
  // Naive fixture timestamps are UK wall times. Keep those literal; convert explicit offsets to UK time.
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    ...(compact ? {} : { year: "numeric" }),
    hour: "2-digit",
    minute: "2-digit",
    timeZone: hasZone ? "Europe/London" : "UTC",
  });
}
function pickupLabel(pickup = {}, compact = false) {
  if (pickup.type === "window")
    return `${dateTime(pickup.start, compact)} – ${dateTime(pickup.end, compact)}`;
  return `${pickup.type === "before" ? "Before " : ""}${dateTime(pickup.time, compact)}`;
}
function deliveryLabel(deliver) {
  if (typeof deliver === "string") return deliver;
  return deliver
    ? `${deliver.type === "by" ? "By " : ""}${dateTime(deliver.time || deliver.start, true)}`
    : "Not supplied";
}
function storedObject(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "{}");
    return value && typeof value === "object" && !Array.isArray(value)
      ? value
      : {};
  } catch {
    return {};
  }
}
function managerName() {
  return $("#manager").value.trim() || DEFAULT_MANAGER;
}

function restoreManager() {
  try {
    $("#manager").value = localStorage.getItem(MANAGER_KEY)?.trim() || "";
  } catch {
    $("#manager").value = "";
    $("#manager-status").textContent = "Name stays in this tab";
  }
}

function saveManager(normalize = false) {
  const name = $("#manager").value.trim();
  if (normalize) $("#manager").value = name;
  try {
    localStorage.setItem(MANAGER_KEY, name);
    $("#manager-status").textContent = name ? "Name saved" : "Used for Approve / Pass";
  } catch {
    $("#manager-status").textContent = "Name stays in this tab";
  }
  return managerName();
}

function routeTitle(load) {
  return `${titleCase(load.from_?.town)} <span class="route-arrow" aria-hidden="true">→</span><span class="sr-only"> to </span>${titleCase(load.to?.town)}`;
}
function renderSummary() {
  const count = (signal) =>
    state.loads.filter((load) => load.quote_analysis.recommendation === signal)
      .length;
  const decisions = state.loads.filter(isDecided).length;
  const pending = state.loads.filter(
    (load) => load.status === "Available" && !isDecided(load),
  ).length;
  const gap = state.loads
    .filter((load) => load.quote_analysis.recommendation === "REPRICE")
    .reduce((sum, load) => sum - load.quote_analysis.difference_gbp, 0);
  $("#summary").innerHTML =
    `<div class="metric"><div class="metric-label">Loads in the feed <span aria-hidden="true">▦</span></div><strong>${state.loads.length}</strong><small>${pending} awaiting a manager decision</small></div><div class="metric"><div class="metric-label">At or above quote <span aria-hidden="true">↗</span></div><strong>${count("APPROVE")}</strong><small><b>Posted rate meets the formula</b></small></div><div class="metric"><div class="metric-label">Need a closer look <span aria-hidden="true">◷</span></div><strong>${count("REPRICE") + count("REVIEW")}</strong><small>${count("REPRICE")} to reprice · ${count("REVIEW")} to review</small></div><div class="metric"><div class="metric-label">Average posted rate <span aria-hidden="true">£</span></div><strong>£${Number(state.summary.average_rate_gbp).toFixed(0)}</strong><small>£${Number(state.summary.average_rate_per_mile_gbp).toFixed(2)} per mile across the feed</small></div>`;
  $("#nav-total").textContent = state.loads.length;
  $("#nav-decisions").textContent = decisions;
  $("#count-all").textContent = state.loads.length;
  for (const signal of ["APPROVE", "REPRICE", "REVIEW"])
    $(`#count-${signal.toLowerCase()}`).textContent = count(signal);
  $("#insight-text").textContent =
    gap > 0
      ? `${count("REPRICE")} loads fall below their formula quote. ${money(gap)} separates their posted rates from the quote total.`
      : "Every posted rate meets its formula quote. Check load requirements before approving.";
  $("#signal-strip").replaceChildren();
  for (const signal of ["APPROVE", "REPRICE", "REVIEW"]) {
    if (!count(signal)) continue;
    const segment = document.createElement("span");
    segment.className = `signal-segment ${signalClass(signal)}`;
    segment.style.flexGrow = count(signal);
    segment.title = `${count(signal)} ${signalName(signal).toLowerCase()}`;
    $("#signal-strip").append(segment);
  }
}
function row(load) {
  const q = load.quote_analysis;
  const selected = String(load.load_id) === state.selectedId;
  const signal = isDecided(load) ? load.ledger.status : q.recommendation;
  const rate = $("#per-mile").checked
    ? `${money(load.rate_per_mile)}<small>/mi</small>`
    : money(load.agreed_rate_gbp);
  return `<button class="load-row${selected ? " selected" : ""}" data-select="${escapeHtml(load.load_id)}" aria-pressed="${selected}" aria-label="Inspect load ${escapeHtml(load.load_id)}: ${escapeHtml(titleCase(load.from_?.town))} to ${escapeHtml(titleCase(load.to?.town))}"><span class="row-meta"><span class="load-number">#${escapeHtml(load.load_id)} · ${escapeHtml(load.status)}</span>${badge(signal)}</span><span class="row-main"><span class="row-route">${routeTitle(load)}</span><strong>${rate}</strong></span><span class="row-bottom"><span>${escapeHtml(load.vehicle_requested)} · ${escapeHtml(load.distance_miles)} mi</span><span class="gap ${q.difference_gbp >= 0 ? "positive" : "negative"}">${signedMoney(q.difference_gbp)} vs quote</span></span><span class="row-schedule">Pickup ${escapeHtml(pickupLabel(load.pickup, true))} <span>·</span> UK time</span></button>`;
}
function stop(location, label, time) {
  return `<div class="route-stop"><span class="stop-dot" aria-hidden="true"></span><div class="stop-copy"><div class="stop-label"><span>${label}</span><span>${escapeHtml(time)}</span></div><b>${escapeHtml(fallback(location?.name))}</b><small>${escapeHtml(fallback(location?.address))} · ${escapeHtml(fallback(location?.postcode))}</small></div></div>`;
}
function detailField(label, value) {
  return `<div><dt>${label}</dt><dd>${escapeHtml(fallback(value))}</dd></div>`;
}
function renderInspector() {
  const load = selectedLoad();
  if (!load || !state.filtered.some((item) => item === load)) {
    $("#inspector").innerHTML =
      '<div class="empty"><strong>A little breathing room.</strong>Select a load when one matches your filters.</div>';
    return;
  }
  const q = load.quote_analysis;
  const decided = isDecided(load) ? load.ledger : null;
  let explanation =
    q.difference_gbp >= 0
      ? `${money(q.difference_gbp)} above the formula quote. Review requirements before approving.`
      : `${money(-q.difference_gbp)} below the formula quote. Consider repricing or passing.`;
  if (q.recommendation === "REVIEW")
    explanation =
      "Journey exceeds the formula’s 450-mile limit. A manager must review this quote.";
  const canReplay = String(load.load_id) === String(state.recordedRunLoadId);
  const isStatic = state.deploymentMode === "static-demo";
  const analysisButton = `<button class="button analysis-launch" data-analyze="${escapeHtml(load.load_id)}" ${isStatic && !canReplay ? "disabled" : ""}>${isStatic ? (canReplay ? "Replay recorded API run" : "Live analysis requires a backend") : "Watch live API analysis"}<span aria-hidden="true">↗</span></button>`;
  const notes =
    (load.load_notes || []).map(escapeHtml).join(" · ") ||
    "No special instructions supplied.";
  const actions = decided?.status
    ? `<div class="ledger-result ${signalClass(decided.status)}"><strong>${escapeHtml(signalName(decided.status))} by ${escapeHtml(decided.manager || DEFAULT_MANAGER)}</strong><small>${escapeHtml(dateTime(decided.at))} · ${state.deploymentMode === "static-demo" ? "Saved in this browser" : "Recorded in the prototype ledger"}</small></div>`
    : load.status === "Available"
      ? `<p>Manager approval records this load as booked in the prototype ledger.</p><div class="actions"><button class="approve" data-action="APPROVE" data-id="${escapeHtml(load.load_id)}">Approve load <span aria-hidden="true">↗</span></button><button class="pass" data-action="PASS" data-id="${escapeHtml(load.load_id)}">Pass on load</button></div>`
      : `<p>This ${escapeHtml(load.status.toLowerCase())} load is not available for a new decision.</p>`;
  $("#inspector").innerHTML =
    `<div class="inspector-top"><p class="eyebrow">LOAD INSPECTOR / #${escapeHtml(load.load_id)}</p>${badge(decided?.status || q.recommendation)}</div><h3>${routeTitle(load)}</h3><div class="route-timeline">${stop(load.from_, "PICKUP", pickupLabel(load.pickup, true))}${stop(load.to, "DELIVERY", deliveryLabel(load.deliver))}</div><div class="route-facts"><span class="fact">${escapeHtml(load.distance_miles)} miles</span><span class="fact">${escapeHtml(load.vehicle_requested)}</span>${load.ulez ? '<span class="fact warning">ULEZ flagged</span>' : ""}${load.weight_kg == null ? '<span class="fact warning">Weight not supplied</span>' : `<span class="fact">${escapeHtml(load.weight_kg)} kg</span>`}</div><div class="quote-card"><div class="quote-card-head"><div><span>Formula quote</span><strong>${money(q.total)}</strong></div><div class="quote-offer"><span>Posted rate</span><b>${money(q.offered_rate_gbp)}</b></div></div><p class="quote-explanation ${q.recommendation === "REVIEW" ? "review" : q.difference_gbp < 0 ? "negative" : ""}">${escapeHtml(explanation)}</p><dl class="formula"><div><dt>Base · ${q.billed_minutes} billed minutes</dt><dd>${money(q.base)}</dd></div><div><dt>Distance fuel tier</dt><dd>${money(q.fuel)}</dd></div><div><dt>London city surcharge</dt><dd>${money(q.city)}</dd></div>${q.minimum_applied ? "<div><dt>Minimum quote applies</dt><dd>Included</dd></div>" : ""}<div class="total"><dt>Calculated quote</dt><dd>${money(q.total)}</dd></div></dl></div><p class="evidence-line"><span aria-hidden="true">◈</span><span>Formula calculated from the fixture. Fleet fit, operating costs, and live diesel or restriction research are evaluated separately in the API analysis.</span></p><details open><summary>Load instructions</summary><p>${notes}</p></details><details><summary>Cargo, contact & payment</summary><dl class="details-grid">${detailField("Category", load.category)}${detailField("Packaging", load.packaging)}${detailField("Dimensions", load.dims)}${detailField("Booked by", load.booked_by_company)}${detailField("Phone", load.phone)}${detailField("Payment terms", load.payment_terms)}${detailField("Reference", load.ref)}${detailField("Flag", load.flag)}</dl></details>${
      load.tracking
        ? `<details><summary>Tracking details</summary><dl class="details-grid">${Object.entries(
            load.tracking,
          )
            .map(([key, value]) =>
              detailField(titleCase(key.replaceAll("_", " ")), value),
            )
            .join("")}</dl></details>`
        : ""
    }${analysisButton}<div class="decision-area">${actions}</div>`;
}
function applyFilters() {
  const query = $("#search").value.trim().toLowerCase();
  const status = $("#status").value;
  const vehicle = $("#vehicle").value;
  const sort = $("#sort").value;
  state.filtered = state.loads.filter((load) => {
    const haystack = JSON.stringify([
      load.load_id,
      load.from_,
      load.to,
      load.load_notes,
      load.booked_by_company,
    ]).toLowerCase();
    return (
      (!query || haystack.includes(query)) &&
      (!status || load.status === status) &&
      (!vehicle || load.vehicle_requested === vehicle) &&
      (state.signal === "all" ||
        load.quote_analysis.recommendation === state.signal) &&
      (state.view !== "decisions" || isDecided(load))
    );
  });
  const pickupValue = (load) =>
    String(load.pickup?.time || load.pickup?.start || "");
  state.filtered.sort((a, b) =>
    sort === "rate-desc"
      ? b.agreed_rate_gbp - a.agreed_rate_gbp
      : sort === "rate-asc"
        ? a.agreed_rate_gbp - b.agreed_rate_gbp
        : sort === "distance"
          ? a.distance_miles - b.distance_miles
          : sort === "gap"
            ? a.quote_analysis.difference_gbp - b.quote_analysis.difference_gbp
            : pickupValue(a).localeCompare(pickupValue(b)),
  );
  if (!state.filtered.some((load) => String(load.load_id) === state.selectedId))
    state.selectedId = state.filtered.length
      ? String(state.filtered[0].load_id)
      : null;
  $("#queue-total").textContent = state.filtered.length;
  $("#result-count").textContent =
    `${state.filtered.length} of ${state.loads.length} loads · UK times`;
  const pageSize = 6;
  const selectedIndex = Math.max(0, state.filtered.findIndex(load => String(load.load_id) === state.selectedId));
  state.page = Math.floor(selectedIndex / pageSize);
  const pageStart = state.page * pageSize;
  $("#loads-page").textContent = state.filtered.length ? `${pageStart + 1}–${Math.min(pageStart + pageSize, state.filtered.length)} of ${state.filtered.length}` : "0 loads";
  $("#loads-prev").disabled = state.page === 0;
  $("#loads-next").disabled = pageStart + pageSize >= state.filtered.length;
  $("#loads").innerHTML = state.filtered.length
    ? state.filtered.slice(pageStart, pageStart + pageSize).map(row).join("")
    : `<div class="empty"><strong>${state.view === "decisions" ? "No recorded decisions yet." : "No loads in this view."}</strong>${state.view === "decisions" ? "Your approved and passed loads will appear here." : "Try a different route, vehicle, or pricing signal."}<br><button class="button quiet" id="reset-filters">${state.view === "decisions" ? "Back to loadboard" : "Clear filters"}</button></div>`;
  document.querySelectorAll(".filter-tab").forEach((button) => {
    const active = button.dataset.signal === state.signal;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active);
  });
  document.querySelectorAll(".nav-item").forEach((button) => {
    const section = document.documentElement?.dataset?.workspaceSection;
    const active = button.dataset.view === state.view && (!section || section === "loadboard");
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active);
  });
  $("#view-label").textContent =
    state.view === "decisions" ? "Decision ledger" : "Loadboard";
  const section = document.documentElement?.dataset?.workspaceSection;
  if (section && section !== "loadboard")
    $("#view-label").textContent = {"brain-workspace": "Spooky Brain", "night-crew": "The night crew", "haunted-yard": "The haunted lay-by"}[section] || "Spooky Brain";
  $("#board-title").firstChild.textContent =
    state.view === "decisions"
      ? "Your decision ledger "
      : "Your decision queue ";
  $("#board-caption").textContent =
    state.view === "decisions"
      ? "A record of the calls you’ve made."
      : "Select a route. See the full picture. Make the call.";
  renderInspector();
}
function resetFilters() {
  state.signal = "all";
  state.view = "queue";
  for (const id of ["#search", "#vehicle", "#status"]) $(id).value = "";
  $("#sort").value = "pickup";
  applyFilters();
}
let toastTimer;
function toast(message, error = false) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").className = error ? "show error" : "show";
  toastTimer = setTimeout(() => {
    $("#toast").className = "";
  }, 5000);
}
function safeUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol)
      ? escapeHtml(url.href)
      : "#";
  } catch (_) {
    return "#";
  }
}

function resetAnalysis(loadId, recorded = false) {
  globalThis.SpookyServices?.reset(recorded);
  if (analysisUI.pollTimer) clearTimeout(analysisUI.pollTimer);
  analysisUI.replayTimers.forEach(clearTimeout);
  Object.assign(analysisUI, {
    seen: 0,
    pollTimer: null,
    replayTimers: [],
    market: null,
    tools: null,
    specialists: 0,
  });
  document
    .querySelectorAll(".pipeline-stage")
    .forEach((item) => item.classList.remove("active", "done", "failed"));
  $("#analysis-events").innerHTML = "";
  $("#analysis-impact").innerHTML = "<p>Waiting for live market evidence…</p>";
  $("#run-metrics").innerHTML = "";
  $("#analysis-title").textContent =
    `${recorded ? "Recorded API run" : "Live API analysis"} · Load ${loadId}`;
  $("#analysis-notice").textContent = recorded
    ? "Verified live run replay. Timestamps and API outputs were captured from the local backend; nothing will be booked."
    : "Running real provider calls with synthetic demo fleet economics. Nothing will be booked or sent to Discord.";
  $("#run-mode").textContent = recorded ? "RECORDED LIVE" : "LIVE";
  $("#run-mode").className = recorded ? "run-mode recorded" : "run-mode";
}

function setStage(name, status) {
  globalThis.SpookyServices?.stage(name, status);
  const stage = document.querySelector(`.pipeline-stage[data-stage="${name}"]`);
  if (!stage) return;
  stage.classList.remove("active", "done", "failed");
  stage.classList.add(status);
}

function updateStage(event) {
  const type = event.type;
  if (type === "crewai.ingest.completed")
    setStage("crewai", "active");
  if (type === "crewai.route.completed") setStage("crewai", "done");
  if (type === "you.grounding.started") setStage("you", "active");
  if (type === "you.grounding.completed") setStage("you", "done");
  if (type === "tools.assessment.completed") setStage("tools", "done");
  if (type.startsWith("parasail."))
    setStage(
      "parasail",
      type === "parasail.supervisor.completed" ? "done" : "active",
    );
  if (type === "safety.gate.completed") setStage("decision", "done");
  if (type === "one.approval.pending") setStage("one", "active");
  if (type === "run.failed") {
    const active = document.querySelector(".pipeline-stage.active");
    if (active) {
      setStage(active.dataset.stage, "failed");
    } else if (/parasail/i.test(event.data?.error || "")) {
      setStage("parasail", "failed");
    } else if (/YDC|YouSearch|You.com/i.test(event.data?.error || "")) {
      setStage("you", "failed");
    }
  }
}

function eventPresentation(event) {
  const d = event.data || {};
  const role = escapeHtml(
    String(d.role || "").replace("fleet-fit", "fleet fit"),
  );
  switch (event.type) {
    case "run.started":
      return ["Analysis started", escapeHtml(d.fleet_notice), ""];
    case "crewai.ingest.completed":
      return [
        "CrewAI ingested load",
        `${d.selected_count} selected from ${d.source_count} fixture records`,
        "done",
      ];
    case "crewai.route.completed":
      return [
        "CrewAI routed load",
        escapeHtml(Object.keys(d.route_counts || {}).join(", ")),
        "done",
      ];
    case "you.grounding.started":
      return [
        "You.com research started",
        (d.research || []).map(escapeHtml).join(" · "),
        "",
      ];
    case "you.grounding.completed": {
      const citation = (d.citations || [])[0];
      const source = citation
        ? `<a href="${safeUrl(citation.url)}" target="_blank" rel="noreferrer">${escapeHtml(citation.title)}</a>`
        : "No citation";
      return [
        "You.com grounded market facts",
        `<strong>${Number(d.diesel_price_ppl).toFixed(2)}p/L diesel</strong> · ${d.citations?.length || 0} citations · ${source}`,
        "done",
      ];
    }
    case "tools.assessment.completed":
      return [
        "Deterministic quote calculated",
        `<strong>${money(d.target_quote_gbp)}</strong> target · ${Number(d.offered_margin_pct).toFixed(1)}% offered margin · live-data effect ${signedMoney(d.live_quote_delta_gbp)}`,
        "done",
      ];
    case "parasail.specialist.started":
      return [
        `Parasail ${role} specialist`,
        `${escapeHtml(d.model)} is analyzing scoped evidence…`,
        "",
      ];
    case "parasail.specialist.completed":
      return [
        `Parasail ${role} completed`,
        `${Number(d.elapsed_seconds).toFixed(1)}s · ${escapeHtml(String(d.summary || "").slice(0, 260))}`,
        "done",
      ];
    case "parasail.supervisor.started":
      return [
        "Parasail supervisor",
        `${escapeHtml(d.model)} is reconciling the specialists…`,
        "",
      ];
    case "parasail.supervisor.completed":
      return [
        "Parasail supervisor completed",
        `<strong>${escapeHtml(d.recommendation)}</strong> · ${Number(d.elapsed_seconds).toFixed(1)}s · ${escapeHtml(String(d.rationale || "").slice(0, 220))}`,
        "done",
      ];
    case "safety.gate.completed":
      return [
        "Safety gate applied",
        `Model: ${escapeHtml(d.model_recommendation)} · deterministic eligible: ${d.deterministic_eligible ? "yes" : "no"} · final: <strong>${escapeHtml(d.final_recommendation)}</strong>`,
        "done",
      ];
    case "one.approval.pending":
      return ["One / Discord handoff", escapeHtml(d.message), ""];
    case "run.completed":
      return [
        "Analysis complete",
        `${Number(d.elapsed_seconds).toFixed(1)}s · ${d.inference_usage?.requests || 0} Parasail calls · recommendation <strong>${escapeHtml(d.recommendation)}</strong>`,
        "done",
      ];
    case "run.failed":
      return ["Analysis failed", escapeHtml(d.error), "failed"];
    default:
      return [escapeHtml(event.type), "", ""];
  }
}

function renderImpact() {
  const market = analysisUI.market;
  const tools = analysisUI.tools;
  if (!market && !tools) return;
  const citations = market?.citations || [];
  const citationList = citations
    .slice(0, 3)
    .map(
      (item) =>
        `<li><a href="${safeUrl(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a></li>`,
    )
    .join("");
  $("#analysis-impact").innerHTML =
    `${market ? `<div class="impact-price"><span>You.com diesel input</span><strong>${Number(market.diesel_price_ppl).toFixed(2)}p/L</strong></div>` : ""}
    ${
      tools
        ? `<div class="impact-price"><span>145p demo baseline quote</span><strong>${money(tools.baseline_target_quote_gbp)}</strong></div>
      <div class="impact-price"><span>Live grounded quote</span><strong>${money(tools.target_quote_gbp)}</strong></div>
      <div class="impact-price delta"><span>You.com price impact</span><strong>${signedMoney(tools.live_quote_delta_gbp)}</strong></div>
      <div class="impact-price"><span>Posted rate / margin</span><strong>${money(tools.offered_rate_gbp)} · ${Number(tools.offered_margin_pct).toFixed(1)}%</strong></div>`
        : ""
    }
    ${citationList ? `<ul class="impact-citations">${citationList}</ul>` : ""}`;
}

function renderMetrics(data) {
  const usage = data.inference_usage || {};
  const tokens =
    Number(usage.prompt_tokens || 0) + Number(usage.completion_tokens || 0);
  $("#run-metrics").innerHTML =
    `<div><span>Elapsed</span><strong>${Number(data.elapsed_seconds || 0).toFixed(1)}s</strong></div><div><span>Parasail calls</span><strong>${usage.requests || 0}</strong></div><div><span>Tokens</span><strong>${tokens.toLocaleString("en-GB")}</strong></div>`;
}

function renderTraceEvent(event) {
  updateStage(event);
  if (event.type === "you.grounding.completed") analysisUI.market = event.data;
  if (event.type === "tools.assessment.completed")
    analysisUI.tools = event.data;
  if (event.type === "parasail.specialist.completed")
    analysisUI.specialists += 1;
  if (event.type === "run.completed") renderMetrics(event.data || {});
  renderImpact();
  if (event.type === "run.failed")
    $("#analysis-impact").innerHTML = `<p class="negative"><strong>Analysis stopped.</strong></p><p>${escapeHtml(event.data?.error || "The provider run failed.")}</p><p>The local loop planner is still available. Configure the provider to retry live analysis.</p>`;
  const [label, detail, className] = eventPresentation(event);
  const elapsed = `${(Number(event.elapsed_ms || 0) / 1000).toFixed(1)}s`;
  $("#analysis-events").insertAdjacentHTML(
    "beforeend",
    `<li class="event-item ${className}"><div class="event-label"><span>${label}</span><time>+${elapsed}</time></div>${detail ? `<div class="event-detail">${detail}</div>` : ""}</li>`,
  );
  $("#analysis-events").scrollTop = $("#analysis-events").scrollHeight;
}

async function pollAnalysis(runId) {
  try {
    const response = await fetch(
      `api/runs/${encodeURIComponent(runId)}?v=${Date.now()}`,
      { cache: "no-store" },
    );
    const run = await response.json();
    if (!response.ok)
      throw new Error(run.error || "Could not read analysis run");
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
      const response = await fetch(`api/demo-run?v=${Date.now()}`, {
        cache: "no-store",
      });
      const run = await response.json();
      if (!response.ok)
        throw new Error(run.error || "Recorded run is unavailable");
      replayAnalysis(run);
      return;
    }
    const response = await fetch("api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ load_id: loadId }),
    });
    const run = await response.json();
    if (!response.ok)
      throw new Error(run.error || "Could not start live analysis");
    pollAnalysis(run.run_id);
  } catch (error) {
    renderTraceEvent({
      type: "run.failed",
      elapsed_ms: 0,
      data: { error: error.message },
    });
    toast(error.message, true);
  }
}

function openDecision(loadId, decision) {
  const load = state.loads.find((item) => String(item.load_id) === loadId);
  if (!load || isDecided(load) || state.busy) return;
  state.pending = { loadId, decision };
  $("#decision-title").textContent =
    decision === "APPROVE" ? "Approve this load?" : "Pass on this load?";
  $("#decision-content").innerHTML =
    `<strong>${routeTitle(load)}</strong><p>#${escapeHtml(loadId)} · Posted rate ${money(load.agreed_rate_gbp)}<br>Formula quote ${money(load.quote_analysis.total)}<br>Manager: ${escapeHtml(managerName())}</p><p class="confirmation-note">${decision === "APPROVE" ? "This records BOOKED in the prototype ledger. It does not book with a broker or send a binding quote." : "This records PASSED in the prototype ledger."} ${state.deploymentMode === "static-demo" ? "This demo saves decisions only in this browser." : "Your decision is appended to the local ledger."}</p>`;
  $("#confirm-decision").textContent =
    decision === "APPROVE" ? "Confirm approval" : "Confirm pass";
  $("#decision-dialog").showModal();
}
async function decide() {
  if (!state.pending || state.busy) return;
  const { loadId, decision } = state.pending;
  state.busy = true;
  $("#confirm-decision").disabled = true;
  $("#confirm-decision").textContent = "Saving decision…";
  try {
    const manager = saveManager(true);
    let result;
    if (state.deploymentMode === "static-demo") {
      const decisions = storedObject(DECISIONS_KEY);
      if (decisions[`Q-${loadId}`])
        throw new Error(
          "This load already has a manager decision. Refresh to see it.",
        );
      result = {
        load_id: loadId,
        status: decision === "APPROVE" ? "BOOKED" : "PASSED",
        human_decision: decision,
        manager,
        at: new Date().toISOString(),
      };
      decisions[`Q-${loadId}`] = result;
      localStorage.setItem(DECISIONS_KEY, JSON.stringify(decisions));
    } else {
      const response = await fetch("api/decision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          load_id: loadId,
          decision,
          manager,
        }),
      });
      result = await response.json();
      if (!response.ok)
        throw new Error(result.error || "Decision could not be saved");
    }
    const load = state.loads.find((item) => String(item.load_id) === loadId);
    if (load) load.ledger = result;
    renderSummary();
    applyFilters();
    if (typeof CustomEvent !== "undefined")
      document.dispatchEvent(new CustomEvent("haulage-decision"));
    $("#decision-dialog").close();
    state.pending = null;
    toast(
      `#${loadId} ${signalName(result.status).toLowerCase()} · saved ${state.deploymentMode === "static-demo" ? "in this browser" : "to the ledger"}`,
    );
  } catch (error) {
    toast(error.message, true);
  } finally {
    state.busy = false;
    $("#confirm-decision").disabled = false;
    $("#confirm-decision").textContent =
      decision === "APPROVE" ? "Confirm approval" : "Confirm pass";
  }
}
async function loadData() {
  const response = await fetch(`api/loads?v=${Date.now()}`, {
    cache: "no-store",
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not load fixture");
  state.deploymentMode = data.deployment?.mode || "server";
  state.recordedRunLoadId = data.deployment?.recorded_run_load_id || null;
  state.loads = data.loads;
  state.brain = data.brain || {};
  state.summary = data.summary;
  if (state.deploymentMode === "static-demo") {
    const decisions = storedObject(DECISIONS_KEY);
    state.loads.forEach((load) => {
      load.ledger = decisions[`Q-${load.load_id}`] || null;
    });
    $(".environment").textContent = "Browser-only demo";
    $("#storage-label").textContent =
      "Demo decisions stay in this browser’s local storage.";
  }
  for (const [selector, field] of [
    ["#status", "status"],
    ["#vehicle", "vehicle_requested"],
  ]) {
    $(selector).insertAdjacentHTML(
      "beforeend",
      [...new Set(state.loads.map((load) => load[field]))]
        .sort()
        .map((value) => `<option>${escapeHtml(value)}</option>`)
        .join(""),
    );
  }
  renderSummary();
  applyFilters();
  if (typeof CustomEvent !== "undefined")
    document.dispatchEvent(new CustomEvent("haulage-ready"));
}
document.addEventListener("DOMContentLoaded", async () => {
  restoreManager();
  $("#manager").addEventListener("input", () => saveManager());
  $("#manager").addEventListener("change", () => saveManager(true));
  $("#manager").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      saveManager(true);
      event.target.blur();
    }
  });
  ["#search", "#status", "#vehicle", "#sort", "#per-mile"].forEach((selector) =>
    $(selector).addEventListener(
      selector === "#search" ? "input" : "change",
      applyFilters,
    ),
  );
  document.querySelectorAll(".filter-tab").forEach((button) =>
    button.addEventListener("click", () => {
      state.signal = button.dataset.signal;
      applyFilters();
    }),
  );
  document.querySelectorAll(".nav-item").forEach((button) =>
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      state.signal = "all";
      $("#search").value = "";
      $("#vehicle").value = "";
      $("#status").value = "";
      applyFilters();
    }),
  );
  $("#loads").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-select]");
    if (button) {
      state.selectedId = button.dataset.select;
      applyFilters();
    }
    if (event.target.closest("#reset-filters")) resetFilters();
  });
  for (const [selector, delta] of [["#loads-prev", -1], ["#loads-next", 1]])
    $(selector).addEventListener("click", () => {
      const next = state.filtered[(state.page + delta) * 6];
      if (next) {
        state.selectedId = String(next.load_id);
        applyFilters();
      }
    });
  $("#inspector").addEventListener("click", (event) => {
    const analysisButton = event.target.closest("button[data-analyze]");
    if (analysisButton) {
      analyzeLoad(analysisButton.dataset.analyze);
      return;
    }
    const button = event.target.closest("button[data-action]");
    if (button) openDecision(button.dataset.id, button.dataset.action);
  });
  $("#review-next").addEventListener("click", () => {
    const next =
      state.filtered.find(
        (load) =>
          load.status === "Available" &&
          !isDecided(load) &&
          String(load.load_id) !== state.selectedId,
      ) ||
      state.filtered.find(
        (load) => load.status === "Available" && !isDecided(load),
      );
    if (!next) {
      toast(
        "No undecided loads in this view. Adjust your filters to continue.",
      );
      return;
    }
    state.selectedId = String(next.load_id);
    applyFilters();
    document
      .querySelector(`button[data-select="${state.selectedId}"]`)
      ?.scrollIntoView({ block: "nearest", behavior: "instant" });
    $("#inspector").scrollIntoView({ block: "nearest", behavior: "instant" });
  });
  $("#raw-json").addEventListener("click", () => {
    $("#json-content").textContent = JSON.stringify(
      state.loads.map(({ quote_analysis, ledger, ...load }) => load),
      null,
      2,
    );
    $("#json-dialog").showModal();
  });
  $("#close-dialog").addEventListener("click", () => $("#json-dialog").close());
  const closeAnalysis = () => {
    if (analysisUI.pollTimer) clearTimeout(analysisUI.pollTimer);
    analysisUI.replayTimers.forEach(clearTimeout);
  };
  $("#close-analysis").addEventListener("click", () => {
    closeAnalysis();
    $("#analysis-dialog").close();
  });
  $("#analysis-dialog").addEventListener("close", closeAnalysis);
  const closeDecision = () => {
    if (!state.busy) {
      $("#decision-dialog").close();
      state.pending = null;
    }
  };
  $("#cancel-decision").addEventListener("click", closeDecision);
  $("#back-decision").addEventListener("click", closeDecision);
  $("#decision-dialog").addEventListener("cancel", (event) => {
    if (state.busy) event.preventDefault();
    else state.pending = null;
  });
  $("#confirm-decision").addEventListener("click", decide);
  document.addEventListener("keydown", (event) => {
    if (
      event.key === "/" &&
      !event.metaKey &&
      !event.ctrlKey &&
      !/INPUT|TEXTAREA|SELECT/.test(event.target.tagName) &&
      !document.querySelector("dialog[open]")
    ) {
      event.preventDefault();
      $("#search").focus();
    }
  });
  try {
    await loadData();
  } catch (error) {
    $("#loads").innerHTML =
      `<div class="empty"><strong>Couldn’t load the workspace.</strong>${escapeHtml(error.message)}<p>Refresh the page to try again.</p></div>`;
    $("#insight-text").textContent =
      "Fixture unavailable. Refresh to reconnect to the loadboard.";
    toast(error.message, true);
  }
});
