"use strict";

/* EcoOps frontend: plain JavaScript, no framework, no external requests.
   Served by the backend at /ui/. If opened straight from disk (file://) it
   talks to the backend on http://127.0.0.1:8000 instead. */

const API_BASE = location.protocol === "file:" ? "http://127.0.0.1:8000" : "";
const DEFAULT_CONTROLS = { teams: 2, budget: 120, window: 6 };
const MAX_PINNED = 4;

const state = {
    mode: "forecast",
    incident: null,
    source: null,
    plan: null,
    order: [],
    selected: new Set(),
    controls: { ...DEFAULT_CONTROLS },
    sim: null,
    simSeq: 0,
    simTimer: null,
    pinned: [],
    pinCounter: 0,
    stage: { detected: false, investigated: false, planned: false, simulated: false },
};

/* ---------- helpers ---------- */

const $ = (id) => document.getElementById(id);

const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (c) => (
        { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const num = (x, digits = 1) =>
    x === null || x === undefined ? "n/a" : Number.isInteger(x) ? String(x) : Number(x).toFixed(digits);

const fmtTime = (t) => (t ? String(t).replace("T", " ") : "n/a");

const fmtDate8 = (s) =>
    s && String(s).length === 8 ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}` : s || "n/a";

function modePath(path) {
    const joiner = path.includes("?") ? "&" : "?";
    return `${path}${joiner}mode=${encodeURIComponent(state.mode)}`;
}

function updateModeControls() {
    const historical = state.mode === "historical";
    $("btn-mode").textContent = historical ? "Use forecast mode" : "Historical replay";
    $("btn-refresh").textContent = historical ? "Re-fetch NASA POWER" : "Refresh forecast";
    $("btn-refresh").title = historical
        ? "Ask NASA POWER for the historical demonstration data again"
        : "Fetch the latest available forecast from Open-Meteo";
}

async function api(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 60000);
    try {
        const res = await fetch(API_BASE + path, {
            ...options,
            signal: controller.signal,
            headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        });
        let body = null;
        try {
            body = await res.json();
        } catch (_) { /* non-JSON error body */ }

        if (!res.ok) {
            let detail = res.statusText;
            if (body && body.detail) {
                detail = typeof body.detail === "string"
                    ? body.detail
                    : body.detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ");
            }
            throw new Error(`${res.status} ${detail}`);
        }
        return body;
    } catch (err) {
        if (err.name === "AbortError") throw new Error("The request timed out.");
        if (err instanceof TypeError) {
            throw new Error("Cannot reach the EcoOps backend. Is it running on port 8000?");
        }
        throw err;
    } finally {
        clearTimeout(timer);
    }
}

const loadingBlock = (text) =>
    `<div class="loading" role="status"><span class="spinner" aria-hidden="true"></span><span>${esc(text)}</span></div>`;

const errorBlock = (title, message, retryAction) => `
    <div class="error-block" role="alert">
        <h3>${esc(title)}</h3>
        <p>${esc(message)}</p>
        ${retryAction ? `<button class="btn" data-action="${retryAction}">Try again</button>` : ""}
    </div>`;

function updatePipeline() {
    document.querySelectorAll("[data-stage]").forEach((el) => {
        el.classList.toggle("done", !!state.stage[el.dataset.stage]);
    });
}

function setBanners(html) {
    $("banners").innerHTML = html;
}

/* ---------- incident ---------- */

function resetDownstream() {
    state.plan = null;
    state.order = [];
    state.selected = new Set();
    state.controls = { ...DEFAULT_CONTROLS };
    state.sim = null;
    state.pinned = [];
    state.pinCounter = 0;
    state.stage = { detected: false, investigated: false, planned: false, simulated: false };
    clearTimeout(state.simTimer);
    state.simSeq += 1;

    const usable = state.incident && state.incident.type !== "DATA_UNAVAILABLE";

    $("investigate-root").innerHTML = `
        <div class="empty">
            <p>Run the investigation to see what the data shows, how each number was derived,
            and which assumptions apply.</p>
            <button class="btn primary" data-action="investigate" ${usable ? "" : "disabled"}>Run investigation</button>
        </div>`;

    $("plan-root").innerHTML = `
        <div class="empty">
            <p>Generate a recommended response plan from the detected incident. Recommendations only; EcoOps does
            not contact anyone or dispatch teams.</p>
            <button class="btn primary" data-action="plan" ${usable ? "" : "disabled"}>Generate response plan</button>
        </div>`;

    $("simulate-root").innerHTML = `
        <div class="empty">
            <p>Generate the response plan first. Then you can change teams, budget and time, reorder actions, and see
            which become executable or blocked.</p>
        </div>`;
}

async function loadIncident(refresh = false) {
    updateModeControls();
    $("incident-root").innerHTML = loadingBlock(
        refresh ? (state.mode === "forecast" ? "Refreshing the Open-Meteo forecast..." : "Asking NASA POWER for the historical data again...")
            : (state.mode === "forecast" ? "Loading the latest available forecast..." : "Loading historical replay data...")
    );
    $("evidence-root").innerHTML = "";
    setBanners("");

    try {
        const data = await api(modePath("/detect" + (refresh ? "?refresh=true" : "")));
        state.incident = data;
        state.source = data.data_source;
        resetDownstream();
        renderIncident();
    } catch (err) {
        state.incident = null;
        state.source = null;
        resetDownstream();
        $("incident-root").innerHTML = errorBlock("Could not load the incident", err.message, "retry");
    }
}

function renderIncident() {
    const inc = state.incident;
    const src = state.source;
    const d = inc.details;
    const root = $("incident-root");

    if (src && src.synthetic) {
        setBanners(`<div class="banner danger"><strong>Synthetic test data.</strong>
            These values are not NASA observations. Do not present them as real.</div>`);
    }

    if (inc.type === "DATA_UNAVAILABLE") {
        $("evidence-root").innerHTML = "";
        root.innerHTML = `
            <div class="error-block" role="alert">
                <h3>${state.mode === "forecast" ? "Forecast unavailable" : "No historical temperature data available"}</h3>
                <p>${esc(src && src.note ? src.note : "NASA POWER returned no valid temperature observations.")}</p>
                ${state.mode === "forecast"
                    ? `<p>EcoOps never substitutes invented forecast values. You can retry the forecast or switch to the historical replay to demonstrate the complete workflow.</p>`
                    : `<p>EcoOps never substitutes invented data. To prepare the offline historical demonstration dataset, run this once while connected to the internet:</p><p><code>python scripts/fetch_demo_data.py</code></p>`}
                <button class="btn" data-action="refresh">${state.mode === "forecast" ? "Retry forecast" : "Try NASA POWER again"}</button>
            </div>`;
        return;
    }

    state.stage.detected = true;
    updatePipeline();

    const isForecast = state.mode === "forecast";
    const isEvent = inc.type === "HEAT_EVENT" || inc.type === "FORECAST_HEAT_RISK";
    const rules = d.rules;
    const ts = src.time_standard;

    root.innerHTML = `
        <div class="incident-head">
            <div>
                <div class="eyebrow" id="h-incident">${esc(inc.incident_id)} &middot; ${esc(inc.location)} &middot; ${isForecast ? "7-day forecast risk screening" : "historical demonstration replay"}</div>
                <h1>${isForecast ? (isEvent ? "Upcoming heat risk identified" : "No qualifying heat risk in forecast") : (isEvent ? "Sustained heat event detected" : "No sustained heat event in this window")}</h1>
                ${isForecast ? `<p class="rule">This is a forecast-based screening signal, not an observed incident or official warning. Forecasts can change; confirm with local authorities and current conditions.</p>` : ""}
                <p class="rule">Trigger: ${esc(rules.min_streak_hours)} or more consecutive hourly readings at or above
                ${esc(rules.threshold_c)} &deg;C. MEDIUM from ${esc(rules.min_streak_hours)} h, HIGH from
                ${esc(rules.high_streak_hours)} h. This is an EcoOps demonstration rule, not a meteorological heatwave
                definition.</p>
            </div>
            <div class="badges">
                <span class="badge sev-${esc(inc.severity)}">Severity ${esc(inc.severity)}</span>
                <span class="badge">${isForecast ? (isEvent ? "Forecast risk" : "No forecast trigger") : (isEvent ? "Incident open" : "No incident")}</span>
            </div>
        </div>

        <div class="stats">
            <div class="stat ${isEvent ? "hot" : ""}">
                <div class="label">${isForecast ? "Forecast peak temperature" : "Peak temperature"}</div>
                <div class="value">${num(inc.max_temp)}<small> &deg;C</small></div>
                <div class="sub">at ${esc(fmtTime(d.peak_time))} ${esc(ts)}</div>
            </div>
            <div class="stat">
                <div class="label">${isForecast ? "Forecast mean temperature" : "Average temperature"}</div>
                <div class="value">${num(inc.avg_temp)}<small> &deg;C</small></div>
                <div class="sub">mean of valid readings</div>
            </div>
            <div class="stat ${isEvent ? "hot" : ""}">
                <div class="label">${isForecast ? "Longest forecast hot streak" : "Longest hot streak"}</div>
                <div class="value">${esc(inc.hot_streak_hours)}<small> h</small></div>
                <div class="sub">${d.longest_streak_start
            ? `${esc(fmtTime(d.longest_streak_start))} to ${esc(fmtTime(d.longest_streak_end))}`
            : `no hour at or above ${esc(inc.threshold)} &deg;C`}</div>
            </div>
            <div class="stat">
                <div class="label">${isForecast ? "Forecast hours available" : "Valid observations"}</div>
                <div class="value">${esc(inc.valid_observations)}<small> / ${esc(d.expected_observations)}</small></div>
                <div class="sub">${esc(d.missing_observations)} missing</div>
            </div>
        </div>`;

    renderEvidence();
}

/* ---------- evidence chart ---------- */

function renderEvidence() {
    const inc = state.incident;
    const src = state.source;
    const d = inc.details;

    const kindLabel = {
        saved_copy: "Saved copy of an earlier NASA POWER response",
        retrieved: "Retrieved from NASA POWER this session",
        forecast: "Forecast model output retrieved this session",
    }[src.kind] || src.kind;
    const isForecast = state.mode === "forecast";

    $("evidence-root").innerHTML = `
        <div class="evidence-grid">
            <div class="chart-box">
                <div class="panel-head" style="margin-bottom:10px">
                    <div>
                        <div class="eyebrow">Evidence timeline</div>
                        <h2 id="h-evidence">${isForecast ? "Hourly forecast temperature" : "Hourly historical temperature"}</h2>
                    </div>
                </div>
                <div id="chart"></div>
                <div class="readout" id="readout" aria-live="polite">Hover or touch the chart to read an hour.</div>
                <div class="legend">
                    <span style="--c:#cfd6df">${isForecast ? "Forecast temperature" : "Observed / historical temperature"}</span>
                    <span style="--c:var(--hot)">At or above trigger</span>
                    <span class="shade">Qualifying streak</span>
                    <span class="dash">${esc(inc.threshold)} &deg;C trigger</span>
                </div>
            </div>
            <div class="prov">
                <div class="eyebrow">Data provenance</div>
                <h3>Where these numbers come from</h3>
                <dl>
                    <div><dt>Source</dt><dd>${isForecast ? `<a href="https://open-meteo.com/" target="_blank" rel="noopener">${esc(src.provider)}</a>` : esc(src.provider)}</dd></div>
                    <div><dt>Dataset</dt><dd>${esc(src.dataset)}</dd></div>
                    <div><dt>Location</dt><dd>${esc(inc.location)} (${esc(src.location.lat)}, ${esc(src.location.lon)})</dd></div>
                    <div><dt>${isForecast ? "Forecast window" : "Observation window"}</dt><dd>${esc(fmtDate8(src.window.start))} to ${esc(fmtDate8(src.window.end))}
                        <span class="muted">(${esc(d.observation_start ? fmtTime(d.observation_start) : "n/a")} to ${esc(fmtTime(d.observation_end))})</span></dd></div>
                    <div><dt>Time standard</dt><dd>${esc(src.time_standard)} ${src.time_standard_origin ? `<span class="muted">(${esc(src.time_standard_origin)})</span>` : ""}</dd></div>
                    <div><dt>Data kind</dt><dd>${esc(kindLabel)}</dd></div>
                    <div><dt>Retrieved at</dt><dd>${esc(src.retrieved_at || "not recorded")}</dd></div>
                    <div><dt>Data status</dt><dd>${isForecast ? "Forecast model output, not live sensor readings or an official warning." : "Historical data, not a live observation."}</dd></div>
                    <div><dt>Missing data</dt><dd>Invalid values are excluded from statistics and break a hot streak. ${esc(d.missing_observations)} of ${esc(d.expected_observations)} hours missing here.</dd></div>
                </dl>
                <div class="tag-legend" aria-label="Value types used in this app">
                    <span class="tag t-observed">Observed</span>
                    <span class="tag t-derived">Derived</span>
                    <span class="tag t-assumed">Assumed</span>
                    <span class="tag t-recommended">Recommended</span>
                </div>
            </div>
        </div>`;

    drawChart();
}

function drawChart() {
    const inc = state.incident;
    const src = state.source;
    const series = inc.details.series;
    const thr = inc.threshold;
    const n = series.length;
    if (!n) return;

    const W = 900, H = 320, ml = 52, mr = 18, mt = 22, mb = 44;
    const vals = series.map((p) => p.temp_c).filter((v) => v !== null);
    const yMin = Math.floor(Math.min(...vals, thr) - 2);
    const yMax = Math.ceil(Math.max(...vals, thr) + 2);
    const step = n > 1 ? (W - ml - mr) / (n - 1) : 0;
    const x = (i) => ml + i * step;
    const y = (v) => mt + ((yMax - v) * (H - mt - mb)) / (yMax - yMin);

    const indexOf = {};
    series.forEach((p, i) => { indexOf[p.time] = i; });

    let grid = "";
    for (let t = Math.ceil(yMin / 5) * 5; t <= yMax; t += 5) {
        grid += `<line x1="${ml}" x2="${W - mr}" y1="${y(t)}" y2="${y(t)}" stroke="#252c35" />
                 <text class="axis-label" x="${ml - 8}" y="${y(t) + 4}" text-anchor="end">${t}</text>`;
    }

    let xticks = "";
    series.forEach((p, i) => {
        const hour = parseInt(p.time.slice(11, 13), 10);
        if (hour % 6 === 0) {
            xticks += `<line x1="${x(i)}" x2="${x(i)}" y1="${H - mb}" y2="${H - mb + 5}" stroke="#5f6a78" />
                       <text class="axis-label" x="${x(i)}" y="${H - mb + 18}" text-anchor="middle">${p.time.slice(11, 16)}</text>`;
            if (hour === 0) {
                xticks += `<text class="axis-label" x="${x(i)}" y="${H - mb + 33}" text-anchor="middle" style="fill:#e8ebf0">${p.time.slice(5, 10)}</text>`;
            }
        }
    });

    const shades = inc.details.qualifying_streaks.map((s) => {
        const i0 = indexOf[s.start], i1 = indexOf[s.end];
        const left = Math.max(ml, x(i0) - step / 2);
        const right = Math.min(W - mr, x(i1) + step / 2);
        return `<rect x="${left}" y="${mt}" width="${right - left}" height="${H - mt - mb}" fill="rgba(255,91,58,0.13)" stroke="rgba(255,91,58,0.5)" stroke-dasharray="3 3" />
                <text class="axis-label" x="${(left + right) / 2}" y="${mt + 12}" text-anchor="middle" style="fill:#ff5b3a">${s.hours} h</text>`;
    }).join("");

    let basePath = "";
    let hotPath = "";
    let open = false;
    series.forEach((p, i) => {
        if (p.temp_c === null) { open = false; return; }
        basePath += `${open ? "L" : "M"}${x(i)} ${y(p.temp_c)} `;
        open = true;
        const prev = series[i - 1];
        if (prev && prev.temp_c !== null && prev.temp_c >= thr && p.temp_c >= thr) {
            hotPath += `M${x(i - 1)} ${y(prev.temp_c)} L${x(i)} ${y(p.temp_c)} `;
        }
    });

    const missing = series.map((p, i) => (p.temp_c === null
        ? `<line x1="${x(i)}" x2="${x(i)}" y1="${mt}" y2="${H - mb}" stroke="#5f6a78" stroke-dasharray="2 4" /><text class="axis-label" x="${x(i)}" y="${H - mb - 6}" text-anchor="middle">missing</text>`
        : "")).join("");

    const peakIdx = indexOf[inc.details.peak_time];
    const peak = peakIdx === undefined ? "" : `
        <circle cx="${x(peakIdx)}" cy="${y(inc.max_temp)}" r="5" fill="#0b0d10" stroke="#e8ebf0" stroke-width="2" />
        <text class="axis-label" x="${x(peakIdx)}" y="${y(inc.max_temp) - 10}" text-anchor="middle" style="fill:#e8ebf0">${num(inc.max_temp)} &deg;C</text>`;

    $("chart").innerHTML = `
        <svg viewBox="0 0 ${W} ${H}" role="img"
             aria-label="Hourly temperature from ${esc(fmtTime(series[0].time))} to ${esc(fmtTime(series[n - 1].time))}. Peak ${num(inc.max_temp)} degrees Celsius. Longest streak at or above ${esc(thr)} degrees: ${esc(inc.hot_streak_hours)} hours.">
            ${grid}
            ${shades}
            <line x1="${ml}" x2="${W - mr}" y1="${y(thr)}" y2="${y(thr)}" stroke="#ffa42e" stroke-dasharray="6 5" stroke-width="1.5" />
            <text class="axis-label" x="${W - mr}" y="${y(thr) - 6}" text-anchor="end" style="fill:#ffa42e">${esc(thr)} &deg;C trigger</text>
            ${missing}
            <path d="${basePath}" fill="none" stroke="#cfd6df" stroke-width="1.6" stroke-linejoin="round" />
            <path d="${hotPath}" fill="none" stroke="#ff5b3a" stroke-width="2.6" stroke-linejoin="round" />
            ${xticks}
            ${peak}
            <line id="guide" x1="0" x2="0" y1="${mt}" y2="${H - mb}" stroke="#8f9aa9" stroke-width="1" visibility="hidden" />
            <circle id="guide-dot" r="4" fill="#2dd4bf" visibility="hidden" />
            <rect id="hit" x="${ml}" y="${mt}" width="${W - ml - mr}" height="${H - mt - mb}" fill="transparent" />
        </svg>`;

    const svg = $("chart").querySelector("svg");
    const guide = $("guide");
    const dot = $("guide-dot");
    const readout = $("readout");

    const move = (event) => {
        const rect = svg.getBoundingClientRect();
        const px = ((event.clientX - rect.left) * W) / rect.width;
        const i = Math.max(0, Math.min(n - 1, step ? Math.round((px - ml) / step) : 0));
        const p = series[i];
        guide.setAttribute("x1", x(i));
        guide.setAttribute("x2", x(i));
        guide.setAttribute("visibility", "visible");
        if (p.temp_c === null) {
            dot.setAttribute("visibility", "hidden");
            readout.textContent = `${fmtTime(p.time)} ${src.time_standard}: missing reading (excluded)`;
        } else {
            dot.setAttribute("cx", x(i));
            dot.setAttribute("cy", y(p.temp_c));
            dot.setAttribute("visibility", "visible");
            readout.textContent = `${fmtTime(p.time)} ${src.time_standard}: ${p.temp_c.toFixed(1)} °C` +
                (p.temp_c >= thr ? "  (at or above trigger)" : "");
        }
    };
    const leave = () => {
        guide.setAttribute("visibility", "hidden");
        dot.setAttribute("visibility", "hidden");
        readout.textContent = "Hover or touch the chart to read an hour.";
    };
    $("hit").addEventListener("pointermove", move);
    $("hit").addEventListener("pointerdown", move);
    $("hit").addEventListener("pointerleave", leave);
}

/* ---------- investigation ---------- */

async function runInvestigation() {
    const root = $("investigate-root");
    root.innerHTML = loadingBlock("Checking evidence and running the configured investigator...");

    let data;
    try {
        data = await api(modePath("/investigate"));
    } catch (err) {
        root.innerHTML = errorBlock("Investigation failed", err.message, "investigate");
        return;
    }

    const inv = data.investigation;
    const forecastMode = state.mode === "forecast";
    const sectionDefs = [
        ["observed_facts", forecastMode ? "Forecast facts" : "Observed facts", "observed", forecastMode ? "Forecast" : "Observed", forecastMode ? "Values supplied by the forecast model, not measured observations." : "Values read directly from the supplied data."],
        ["derived_metrics", "Derived metrics", "derived", "Derived", "Calculated from the observations by a stated rule."],
        ["operational_assumptions", "Operational assumptions", "assumed", "Assumed", "Not measured. Planning and interpretation limits."],
        ["recommended_actions", "Recommended actions", "recommended", "Recommended", "Suggestions to consider, not official instructions."],
    ];

    const isStrands = inv.investigation_mode === "strands_ollama";
    const modeDescription = isStrands
        ? "Deterministic evidence checks plus a local Strands agent brief. Review AI-generated wording before acting."
        : inv.investigation_mode === "deterministic_fallback"
            ? "Strands/Ollama could not run. Deterministic evidence checks are shown instead; no agent brief was generated."
            : "Fixed rules applied to the evidence. This is not an AI agent.";

    root.innerHTML = `
        <p class="mode">Mode: <strong>${esc(inv.investigation_mode.replaceAll("_", " "))}</strong>.
            ${esc(modeDescription)}</p>
        ${inv.fallback_reason ? `<p class="fine">${esc(inv.fallback_reason)}</p>` : ""}
        ${inv.agent_brief ? `<div class="card agent-brief"><div class="card-head"><h3>Strands agent brief</h3><span class="tag t-recommended">AI-generated</span></div><p>${esc(inv.agent_brief.text)}</p><p class="basis">${esc(inv.agent_brief.basis)}</p></div>` : ""}
        <ol class="checks" id="checks">
            ${inv.checks.map((c) => `
                <li class="check"><span class="mark" aria-hidden="true"></span>
                    <div><div>${esc(c.label)}</div><div class="result">${esc(c.result)}</div></div></li>`).join("")}
        </ol>
        <div class="sections" id="inv-sections" hidden></div>`;

    for (const el of root.querySelectorAll(".check")) {
        await sleep(180);
        el.classList.add("done");
    }

    const sections = $("inv-sections");
    sections.innerHTML = sectionDefs.map(([key, title, cls, tagText, blurb]) => {
        const items = inv[key] || [];
        return `
            <div class="card">
                <div class="card-head"><h3>${esc(title)}</h3><span class="tag t-${cls}">${esc(tagText)}</span></div>
                <p class="fine" style="margin-bottom:10px">${esc(blurb)}</p>
                ${items.length
                ? `<ul class="items">${items.map((it) => `<li>${esc(it.text)}<span class="basis">${esc(it.basis)}</span></li>`).join("")}</ul>`
                : `<p class="fine">Nothing to report.</p>`}
            </div>`;
    }).join("");
    sections.hidden = false;

    state.stage.investigated = true;
    updatePipeline();
}

/* ---------- response plan ---------- */

async function generatePlan() {
    const root = $("plan-root");
    root.innerHTML = loadingBlock("Generating response plan...");

    let plan;
    try {
        plan = await api(modePath("/response"));
    } catch (err) {
        root.innerHTML = errorBlock("Could not generate the plan", err.message, "plan");
        return;
    }

    state.plan = plan;

    if (plan.status !== "RESPONSE_RECOMMENDED") {
        root.innerHTML = `<div class="empty"><p>No response plan is needed: ${state.mode === "forecast" ? "the available forecast did not meet the configured heat-risk trigger" : "no sustained heat incident was detected in this historical window"}.</p></div>`;
        return;
    }

    state.order = plan.actions.slice().sort((a, b) => a.priority - b.priority).map((a) => a.action_id);
    state.selected = new Set(state.order);

    root.innerHTML = `
        <div class="notice">${esc(plan.disclaimer)}</div>
        <div class="notice assumed"><span class="tag t-assumed">Assumed</span>&nbsp; ${esc(plan.assumption_note)}</div>
        <div class="action-list">
            ${plan.actions.map((a) => `
                <article class="action-card">
                    <div class="action-id">${esc(a.action_id)}</div>
                    <div>
                        <h3>${esc(a.name)}</h3>
                        <p>${esc(a.reason)}</p>
                        <div class="chips">
                            <span class="chip">${esc(a.resource)}</span>
                            <span class="chip warn">${esc(a.teams_required)} team${a.teams_required > 1 ? "s" : ""}</span>
                            <span class="chip warn">${esc(a.budget_units)} budget units</span>
                            <span class="chip warn">${esc(a.duration_hours)} h</span>
                        </div>
                    </div>
                    <span class="tag t-recommended">${esc(a.status.toLowerCase())}</span>
                </article>`).join("")}
        </div>`;

    state.stage.planned = true;
    updatePipeline();
    buildSimulation();
}

/* ---------- simulation ---------- */

function buildSimulation() {
    $("simulate-root").innerHTML = `
        <div class="notice">Simulates operational resource allocation only. It does not predict temperature
            reduction, health outcomes or real-world effectiveness.</div>
        <div class="sim-grid">
            <div class="controls">
                <div class="slider-row">
                    <label for="ctl-teams">Available teams <output id="out-teams"></output></label>
                    <input type="range" id="ctl-teams" min="0" max="8" step="1">
                </div>
                <div class="slider-row">
                    <label for="ctl-budget">Budget (planning units) <output id="out-budget"></output></label>
                    <input type="range" id="ctl-budget" min="0" max="300" step="10">
                </div>
                <div class="slider-row">
                    <label for="ctl-window">Response window (hours) <output id="out-window"></output></label>
                    <input type="range" id="ctl-window" min="1" max="12" step="0.5">
                </div>
                <div>
                    <h4>Action priority</h4>
                    <p class="fine" style="margin-top:6px">Tick to include. Order sets who gets scarce resources first.</p>
                    <ul class="order-list" id="order-list"></ul>
                </div>
                <div class="row-actions" style="margin-top:0">
                    <button class="btn small ghost" data-action="reset-sim">Reset to defaults</button>
                </div>
            </div>
            <div id="sim-results">${loadingBlock("Running simulation...")}</div>
        </div>
        <div id="pinned-root"></div>`;

    syncControls();
    renderOrderList();
    renderPinned();
    runSimulation();
}

function syncControls() {
    const c = state.controls;
    $("ctl-teams").value = c.teams;
    $("ctl-budget").value = c.budget;
    $("ctl-window").value = c.window;
    $("out-teams").textContent = c.teams;
    $("out-budget").textContent = c.budget;
    $("out-window").textContent = `${c.window} h`;
}

function actionById(id) {
    return state.plan.actions.find((a) => a.action_id === id);
}

function renderOrderList() {
    const list = $("order-list");
    list.innerHTML = state.order.map((id, i) => {
        const a = actionById(id);
        const on = state.selected.has(id);
        return `
            <li class="order-item ${on ? "" : "off"}">
                <input type="checkbox" data-select="${esc(id)}" ${on ? "checked" : ""}
                       aria-label="Include ${esc(a.name)}">
                <div>${esc(id)} &middot; ${esc(a.name)}
                    <span class="meta">${esc(a.teams_required)} team${a.teams_required > 1 ? "s" : ""} &middot; ${esc(a.budget_units)} units &middot; ${esc(a.duration_hours)} h</span>
                </div>
                <div class="move">
                    <button data-action="move-up" data-id="${esc(id)}" ${i === 0 ? "disabled" : ""} aria-label="Move ${esc(id)} up">&uarr;</button>
                    <button data-action="move-down" data-id="${esc(id)}" ${i === state.order.length - 1 ? "disabled" : ""} aria-label="Move ${esc(id)} down">&darr;</button>
                </div>
            </li>`;
    }).join("");
}

function currentOrder() {
    return state.order.filter((id) => state.selected.has(id));
}

function scheduleSimulation() {
    clearTimeout(state.simTimer);
    state.simTimer = setTimeout(runSimulation, 120);
}

async function runSimulation() {
    const seq = ++state.simSeq;
    const c = state.controls;
    const request = {
        teams: c.teams,
        budget: c.budget,
        window_hours: c.window,
        action_order: currentOrder(),
    };

    try {
        const data = await api(modePath("/simulate"), { method: "POST", body: JSON.stringify(request) });
        if (seq !== state.simSeq) return;
        state.sim = { request, ...data };
        renderSimResult();
        state.stage.simulated = true;
        updatePipeline();
    } catch (err) {
        if (seq !== state.simSeq) return;
        const el = $("sim-results");
        if (el) el.innerHTML = errorBlock("Simulation failed", err.message, "resim");
    }
}

function meter(value, total, hot = false) {
    const pct = total > 0 ? Math.min(100, (100 * value) / total) : 0;
    return `<div class="meter ${hot ? "hot" : ""}" role="presentation"><span style="width:${pct}%"></span></div>`;
}

function renderTimeline(sim) {
    const teams = sim.resources.teams_initial;
    const win = sim.resources.window_hours;

    if (teams === 0) {
        return `<p class="fine">No teams available, so nothing can be scheduled.</p>`;
    }

    const lanes = Array.from({ length: teams }, () => []);
    sim.schedule.forEach((s) => s.teams.forEach((t) => lanes[t].push(s)));

    const tickStep = win <= 6 ? 1 : win <= 12 ? 2 : 4;
    let ticks = "";
    for (let t = 0; t <= win + 1e-9; t += tickStep) {
        ticks += `<span style="left:${(100 * t) / win}%">${t}h</span>`;
    }

    return `
        <div class="timeline" role="img"
             aria-label="Schedule of ${sim.schedule.length} actions across ${teams} teams over ${win} hours">
            ${lanes.map((blocks, i) => `
                <div class="lane">
                    <span class="lane-label">Team ${i + 1}</span>
                    <div class="lane-track">
                        ${blocks.map((s) => `
                            <div class="block" title="${esc(s.action_id)} ${esc(s.name)}: hour ${s.start_hour} to ${s.end_hour}"
                                 style="left:${(100 * s.start_hour) / win}%;width:${(100 * (s.end_hour - s.start_hour)) / win}%">
                                ${esc(s.action_id)}</div>`).join("")}
                    </div>
                </div>`).join("")}
            <div class="axis">${ticks}</div>
        </div>`;
}

function renderSimResult() {
    const el = $("sim-results");
    if (!el || !state.sim) return;

    const { simulation: sim, comparison: cmp } = state.sim;
    const res = sim.resources;
    const ex = sim.execution;
    const win = res.window_hours;

    const executedHtml = sim.executed_actions.length
        ? sim.executed_actions.map((a) => {
            const entry = sim.schedule.find((s) => s.action_id === a.action_id);
            const teamLabel = entry.teams.map((t) => `Team ${t + 1}`).join(" + ");
            return `<li class="ok"><strong>${esc(a.action_id)}</strong> ${esc(a.name)}
                <span class="detail">Hour ${num(a.start_hour)} to ${num(a.end_hour)} &middot; ${esc(teamLabel)} &middot; ${esc(a.budget_used)} units</span></li>`;
        }).join("")
        : `<li class="none">No actions can be executed with these resources.</li>`;

    const blockedHtml = sim.blocked_actions.length
        ? sim.blocked_actions.map((a) => `
            <li class="blocked"><strong>${esc(a.action_id)}</strong> ${esc(a.name)}
                <span class="chip hot" style="margin-left:6px">${esc(a.reason_code)}</span>
                <span class="detail">${esc(a.reason)}</span></li>`).join("")
        : `<li class="none">Nothing is blocked.</li>`;

    const skipped = sim.not_selected_actions.length
        ? `<h4 style="margin-top:14px;margin-bottom:8px">Not selected</h4>
           <ul class="result-list">${sim.not_selected_actions.map((a) =>
            `<li class="skipped"><strong>${esc(a.action_id)}</strong> ${esc(a.name)}</li>`).join("")}</ul>`
        : "";

    const missing = cmp.missing_actions.length
        ? `<p class="fine" style="margin-top:10px">Not covered by this allocation: ${cmp.missing_actions
            .map((m) => `<strong>${esc(m.action_id)}</strong> (${esc(m.reason)})`).join("; ")}.</p>`
        : `<p class="fine" style="margin-top:10px">This allocation covers the full plan.</p>`;

    el.innerHTML = `
        <div class="tiles">
            <div class="tile">
                <div class="label">Execution coverage</div>
                <div class="value">${num(ex.coverage, 0)}<small>%</small></div>
                ${meter(ex.actions_executed, ex.actions_planned)}
                <div class="fine" style="margin-top:6px">${ex.actions_executed} of ${ex.actions_planned} selected actions</div>
            </div>
            <div class="tile">
                <div class="label">Budget used</div>
                <div class="value">${num(res.budget_used)}<small> / ${num(res.budget_initial)}</small></div>
                ${meter(res.budget_used, res.budget_initial)}
                <div class="fine" style="margin-top:6px">${num(res.budget_remaining)} units remaining</div>
            </div>
            <div class="tile">
                <div class="label">Team-hours used</div>
                <div class="value">${num(res.team_hours_used)}<small> / ${num(res.team_hours_available)}</small></div>
                ${meter(res.team_hours_used, res.team_hours_available)}
                <div class="fine" style="margin-top:6px">${res.teams_initial} teams &times; ${num(win)} h</div>
            </div>
            <div class="tile">
                <div class="label">Finishes at</div>
                <div class="value">${num(ex.completion_hour)}<small> h / ${num(win)}</small></div>
                ${meter(ex.completion_hour, win)}
                <div class="fine" style="margin-top:6px">of the response window</div>
            </div>
        </div>

        <div class="result-block">
            <h4>Schedule</h4>
            ${renderTimeline(sim)}
        </div>

        <div class="result-block two-col">
            <div>
                <h4>Executable</h4>
                <ul class="result-list">${executedHtml}</ul>
            </div>
            <div>
                <h4>Blocked</h4>
                <ul class="result-list">${blockedHtml}</ul>
                ${skipped}
            </div>
        </div>

        <div class="result-block">
            <h4>This allocation vs the full plan</h4>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Measure</th><th class="num">This allocation</th><th class="num">Full plan, all actions</th></tr></thead>
                    <tbody>
                        <tr><td>Actions executed</td><td class="num">${cmp.actions_executed} of ${cmp.total_actions}</td><td class="num">${cmp.baseline_actions_executed} of ${cmp.total_actions}</td></tr>
                        <tr><td>Budget units used</td><td class="num">${num(cmp.budget_used)}</td><td class="num">${num(cmp.baseline_budget_required)} needed</td></tr>
                        <tr><td>Teams</td><td class="num">${cmp.teams_available} available</td><td class="num">${cmp.baseline_teams_required} to run all at once</td></tr>
                        <tr><td>Finishes at hour</td><td class="num">${num(cmp.completion_hour)}</td><td class="num">${num(cmp.baseline_completion_hour)}</td></tr>
                    </tbody>
                </table>
            </div>
            ${missing}
            <div class="row-actions">
                <button class="btn teal small" data-action="pin" ${state.pinned.length >= MAX_PINNED ? "disabled" : ""}>Pin this scenario to compare</button>
                <span class="fine">${state.pinned.length >= MAX_PINNED ? "Pin limit reached. Remove one to add another." : "Pin up to " + MAX_PINNED + " scenarios and compare them below."}</span>
            </div>
        </div>`;
}

/* ---------- pinned scenarios ---------- */

function pinScenario() {
    if (!state.sim || state.pinned.length >= MAX_PINNED) return;
    const { simulation: sim, request } = state.sim;
    const label = String.fromCharCode(65 + (state.pinCounter++ % 26));
    state.pinned.push({
        label: `Scenario ${label}`,
        teams: request.teams,
        budget: request.budget,
        window: request.window_hours,
        order: request.action_order.join(", ") || "none",
        executed: sim.execution.actions_executed,
        planned: sim.execution.actions_planned,
        coverage: sim.execution.coverage,
        budgetUsed: sim.resources.budget_used,
        finish: sim.execution.completion_hour,
        blocked: sim.blocked_actions.map((b) => `${b.action_id} (${b.reason_code})`).join(", ") || "none",
    });
    renderPinned();
    renderSimResult();
}

function renderPinned() {
    const root = $("pinned-root");
    if (!root) return;

    if (!state.pinned.length) {
        root.innerHTML = "";
        return;
    }

    root.innerHTML = `
        <div class="result-block">
            <h4>Pinned scenarios</h4>
            <div class="table-wrap">
                <table>
                    <thead><tr>
                        <th>Scenario</th><th class="num">Teams</th><th class="num">Budget</th><th class="num">Window</th>
                        <th>Priority order</th><th class="num">Executed</th><th class="num">Coverage</th>
                        <th class="num">Budget used</th><th class="num">Finish</th><th>Blocked</th><th></th>
                    </tr></thead>
                    <tbody>
                        ${state.pinned.map((p, i) => `
                            <tr>
                                <td>${esc(p.label)}</td>
                                <td class="num">${esc(p.teams)}</td>
                                <td class="num">${esc(p.budget)}</td>
                                <td class="num">${esc(p.window)} h</td>
                                <td class="num">${esc(p.order)}</td>
                                <td class="num">${esc(p.executed)} / ${esc(p.planned)}</td>
                                <td class="num">${num(p.coverage, 0)}%</td>
                                <td class="num">${num(p.budgetUsed)}</td>
                                <td class="num">${num(p.finish)} h</td>
                                <td class="num">${esc(p.blocked)}</td>
                                <td><button class="btn small ghost" data-action="unpin" data-index="${i}">Remove</button></td>
                            </tr>`).join("")}
                    </tbody>
                </table>
            </div>
        </div>`;
}

/* ---------- events ---------- */

document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action]");
    if (!target || target.disabled) return;

    switch (target.dataset.action) {
        case "refresh": loadIncident(true); break;
        case "retry": loadIncident(false); break;
        case "switch-mode":
            state.mode = state.mode === "forecast" ? "historical" : "forecast";
            loadIncident(false);
            break;
        case "investigate": runInvestigation(); break;
        case "plan": generatePlan(); break;
        case "resim": runSimulation(); break;
        case "pin": pinScenario(); break;
        case "unpin":
            state.pinned.splice(Number(target.dataset.index), 1);
            renderPinned();
            renderSimResult();
            break;
        case "reset-sim":
            state.controls = { ...DEFAULT_CONTROLS };
            state.order = state.plan.actions.slice().sort((a, b) => a.priority - b.priority).map((a) => a.action_id);
            state.selected = new Set(state.order);
            syncControls();
            renderOrderList();
            runSimulation();
            break;
        case "move-up":
        case "move-down": {
            const i = state.order.indexOf(target.dataset.id);
            const j = target.dataset.action === "move-up" ? i - 1 : i + 1;
            if (i < 0 || j < 0 || j >= state.order.length) break;
            [state.order[i], state.order[j]] = [state.order[j], state.order[i]];
            renderOrderList();
            scheduleSimulation();
            break;
        }
        default: break;
    }
});

document.addEventListener("input", (event) => {
    const id = event.target.id;
    if (id === "ctl-teams") state.controls.teams = Number(event.target.value);
    else if (id === "ctl-budget") state.controls.budget = Number(event.target.value);
    else if (id === "ctl-window") state.controls.window = Number(event.target.value);
    else return;
    syncControls();
    scheduleSimulation();
});

document.addEventListener("change", (event) => {
    const id = event.target.dataset && event.target.dataset.select;
    if (!id) return;
    if (event.target.checked) state.selected.add(id);
    else state.selected.delete(id);
    renderOrderList();
    scheduleSimulation();
});

loadIncident(false);
