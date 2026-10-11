"use strict";

/* EcoOps frontend: plain JavaScript, no framework, no external requests.
   Served by the backend at /ui/. If opened straight from disk (file://) it
   talks to the backend on http://127.0.0.1:8000 instead.

   Heat AND cold are always screened together (GET /assess). There is no
   manual hazard selector; only the data mode (forecast / historical) is chosen. */

const API_BASE = location.protocol === "file:" ? "http://127.0.0.1:8000" : "";
const DEFAULT_CONTROLS = { teams: 2, budget: 120, window: 6 };
const MAX_PINNED = 4;

const HAZ = {
    heat: { name: "Heat", color: "#ff5b3a", soft: "rgba(255,91,58,0.13)", rel: "at or above", sym: "≥", dash: "6 5", extreme: "Peak", noun: "hot" },
    cold: { name: "Cold", color: "#60a5fa", soft: "rgba(96,165,250,0.15)", rel: "at or below", sym: "≤", dash: "2 4", extreme: "Lowest", noun: "cold" },
};
const HAZARDS = ["heat", "cold"];

const state = {
    mode: "forecast",
    assessment: null,   // full /assess payload
    incidents: [],      // qualifying incidents, most severe first
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

const isRisk = (inc) => !!inc && inc.status === "RISK_DETECTED";
const hazardOf = (inc) => (inc && inc.hazard === "cold" ? "cold" : "heat");

function modePath(path, hazard) {
    const joiner = path.includes("?") ? "&" : "?";
    const base = `${path}${joiner}mode=${encodeURIComponent(state.mode)}`;
    return hazard ? `${base}&hazard=${encodeURIComponent(hazard)}` : base;
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
        let malformed = false;
        try {
            body = await res.json();
        } catch (_) { malformed = true; }

        if (!res.ok) {
            let detail = res.statusText;
            if (body && body.detail) {
                detail = typeof body.detail === "string"
                    ? body.detail
                    : Array.isArray(body.detail)
                        ? body.detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ")
                        : JSON.stringify(body.detail);
            }
            throw new Error(`${res.status} ${detail}`);
        }
        if (malformed || body === null || typeof body !== "object") {
            throw new Error("The backend returned a response EcoOps could not read (malformed JSON).");
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

function overallStatus() {
    return state.assessment ? state.assessment.status : null;
}

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

    const status = overallStatus();
    const hasRisk = state.incidents.length > 0;
    const why = status === "UNAVAILABLE"
        ? "The temperature data could not be assessed, so there is nothing to investigate yet. Fix the data source and try again."
        : status === "NEITHER"
            ? "No qualifying heat or cold risk was found in this data, so there is nothing to investigate. This is a valid result, not missing data."
            : null;

    $("investigate-root").innerHTML = hasRisk ? `
        <div class="empty">
            <p>Run the investigation to see, for each qualifying risk, what the data shows, how each number was
            derived, and which assumptions apply.</p>
            <button class="btn primary" data-action="investigate">Run investigation</button>
        </div>` : `<div class="empty"><p>${esc(why || "Load an assessment first.")}</p></div>`;

    $("plan-root").innerHTML = hasRisk ? `
        <div class="empty">
            <p>Generate a recommended response plan covering every qualifying risk. Recommendations only; EcoOps
            does not contact anyone or dispatch teams.</p>
            <button class="btn primary" data-action="plan">Generate response plan</button>
        </div>` : `<div class="empty"><p>${esc(status === "UNAVAILABLE"
            ? "No plan can be made because the assessment is unavailable."
            : status === "NEITHER" ? "No response plan is needed: no qualifying temperature risk." : "Load an assessment first.")}</p></div>`;

    $("simulate-root").innerHTML = `
        <div class="empty">
            <p>${hasRisk
            ? "Generate the response plan first. Then you can change teams, budget and time, reorder actions, and see which become executable or blocked."
            : "There is no response plan to simulate."}</p>
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
        const data = await api(modePath(`/assess${refresh ? "?refresh=true" : ""}`));
        const a = data.assessments;
        if (!a || !a.heat || !a.cold || !data.status || !data.data_source) {
            throw new Error("The backend returned an incomplete assessment (heat/cold results missing).");
        }
        state.assessment = data;
        state.source = data.data_source;
        state.incidents = (data.incident_ids || [])
            .map((id) => HAZARDS.map((h) => a[h]).find((x) => x.incident_id === id))
            .filter(Boolean);
        resetDownstream();
        renderIncident();
    } catch (err) {
        state.assessment = null;
        state.incidents = [];
        state.source = null;
        resetDownstream();
        $("evidence-root").innerHTML = "";
        $("incident-root").innerHTML = errorBlock("Could not load the assessment", err.message, "retry");
    }
}

const STATUS_CLASS = {
    HEAT_ONLY: "heat", COLD_ONLY: "cold", BOTH: "both", NEITHER: "none", UNAVAILABLE: "unavailable",
};

function riskCard(hazard) {
    const inc = state.assessment.assessments[hazard];
    const hz = HAZ[hazard];
    const d = inc.details || {};
    const rules = d.rules || {};
    const ts = state.source.time_standard;
    const isForecast = state.mode === "forecast";
    const rule = `${hz.sym} ${num(inc.threshold)} °C for ${esc(rules.min_streak_hours)}+ consecutive hours (HIGH at ${esc(rules.high_streak_hours)} h)`;

    let chip;
    let body;
    if (inc.status === "UNAVAILABLE") {
        chip = `<span class="badge st-unavailable">Could not assess</span>`;
        body = `<p class="fine">No valid hourly temperatures were available, so ${hz.name.toLowerCase()} risk was <strong>not evaluated</strong>. This is not a "no risk" result.</p>`;
    } else {
        chip = isRisk(inc)
            ? `<span class="badge sev-${esc(inc.severity)}">${isForecast ? "Forecast " : ""}${hz.name.toLowerCase()} risk &middot; ${esc(inc.severity)}</span>`
            : `<span class="badge st-none">No qualifying ${hz.name.toLowerCase()} risk</span>`;
        const extremeVal = hazard === "cold" ? d.min_temp : inc.max_temp;
        const extremeTime = hazard === "cold" ? d.min_time : d.peak_time;
        const intervals = (d.qualifying_streaks || []);
        body = `
            <div class="mini-stats">
                <div><span class="label">${hz.extreme} temperature</span>
                    <span class="value">${num(extremeVal)}<small> &deg;C</small></span>
                    <span class="sub">${esc(fmtTime(extremeTime))} ${esc(ts)}</span></div>
                <div><span class="label">Longest ${hz.noun} run</span>
                    <span class="value">${esc(inc.streak_hours)}<small> h</small></span>
                    <span class="sub">${d.longest_streak_start ? `${esc(fmtTime(d.longest_streak_start))} to ${esc(fmtTime(d.longest_streak_end))}` : `no hour ${hz.rel} ${num(inc.threshold)} °C`}</span></div>
                <div><span class="label">Hours ${hz.rel} trigger</span>
                    <span class="value">${esc(d.hours_beyond_threshold ?? 0)}<small> h</small></span>
                    <span class="sub">of ${esc(inc.valid_observations)} valid hours</span></div>
            </div>
            ${isRisk(inc) && intervals.length ? `<p class="fine"><strong>Qualifying ${intervals.length > 1 ? "intervals" : "interval"}:</strong> ${intervals.map((s) =>
                `${esc(fmtTime(s.start))} to ${esc(fmtTime(s.end))} (${esc(s.hours)} h)`).join("; ")}</p>` : ""}
            ${!isRisk(inc) ? `<p class="fine">Valid assessment: the longest run ${hz.rel} the trigger was shorter than the ${esc(rules.min_streak_hours)} h minimum.</p>` : ""}`;
    }

    return `
        <article class="risk-card hz-${hazard} ${isRisk(inc) ? "active" : ""}" aria-label="${hz.name} risk assessment">
            <div class="risk-head"><h3><span class="swatch" style="background:${hz.color}"></span>${hz.name} risk</h3>${chip}</div>
            <p class="rule-line">Rule: ${rule}</p>
            ${body}
            <p class="fine id-line">${esc(inc.incident_id)}</p>
        </article>`;
}

function renderIncident() {
    const a = state.assessment;
    const src = state.source;
    const root = $("incident-root");
    const isForecast = state.mode === "forecast";
    const status = a.status;
    const heat = a.assessments.heat;
    const cold = a.assessments.cold;
    const heatD = heat.details || {};

    if (src && src.synthetic) {
        setBanners(`<div class="banner danger"><strong>Synthetic test data.</strong>
            These values are not NASA observations. Do not present them as real.</div>`);
    }

    const rules = heatD.rules || {};
    const unavailable = status === "UNAVAILABLE";

    root.innerHTML = `
        <div class="incident-head">
            <div>
                <div class="eyebrow" id="h-incident">${esc(heat.location)} &middot; ${isForecast ? "7-day forecast risk screening" : "historical demonstration replay"}</div>
                <h1>${esc(a.status_label)}</h1>
                ${isForecast ? `<p class="rule">Forecast screening, not an observed incident or official warning. Forecasts can change; confirm with local authorities and current conditions.</p>` : `<p class="rule">Historical replay of saved NASA POWER data, not a live incident.</p>`}
                <p class="rule">Heat and cold are always checked together: heat at or above ${esc(num(heat.threshold))} &deg;C and cold at or below ${esc(num(cold.threshold))} &deg;C, each for ${esc(rules.min_streak_hours ?? 4)} consecutive hourly readings (MEDIUM), HIGH from ${esc(rules.high_streak_hours ?? 8)} h. These are EcoOps demo settings, not official IMD or medical thresholds.</p>
            </div>
            <div class="badges">
                <span class="badge status-${STATUS_CLASS[status] || "none"}" id="overall-status">${esc(a.status_label)}</span>
            </div>
        </div>

        ${unavailable ? `
        <div class="error-block" role="alert">
            <h3>${isForecast ? "Forecast unavailable" : "No historical temperature data available"}</h3>
            <p>${esc(src && src.note ? src.note : "No valid temperature observations were returned.")}</p>
            ${isForecast
                ? `<p>EcoOps never substitutes invented forecast values. Retry the forecast or switch to the historical replay.</p>`
                : `<p>EcoOps never substitutes invented data. To prepare the offline demonstration dataset, run this once while connected to the internet:</p><p><code>python scripts/fetch_demo_data.py</code></p>`}
            <button class="btn" data-action="refresh">${isForecast ? "Retry forecast" : "Try NASA POWER again"}</button>
        </div>` : ""}

        <div class="risk-grid">${riskCard("heat")}${riskCard("cold")}</div>

        ${unavailable ? "" : `
        <div class="stats stats-3">
            <div class="stat">
                <div class="label">${isForecast ? "Forecast mean temperature" : "Average temperature"}</div>
                <div class="value">${num(heat.avg_temp)}<small> &deg;C</small></div>
                <div class="sub">mean of valid readings</div>
            </div>
            <div class="stat">
                <div class="label">${isForecast ? "Forecast hours available" : "Valid observations"}</div>
                <div class="value">${esc(heat.valid_observations)}<small> / ${esc(heatD.expected_observations)}</small></div>
                <div class="sub">${esc(heatD.missing_observations)} missing</div>
            </div>
            <div class="stat">
                <div class="label">Temperature range</div>
                <div class="value">${num(cold.details.min_temp)}<small> to </small>${num(heat.max_temp)}<small> &deg;C</small></div>
                <div class="sub">lowest to highest valid hour</div>
            </div>
        </div>`}`;

    if (unavailable) {
        $("evidence-root").innerHTML = `<div class="empty"><p>There is no hourly series to plot because no valid temperature data was available.</p></div>`;
        return;
    }

    state.stage.detected = true;
    updatePipeline();
    renderEvidence();
}

/* ---------- evidence chart ---------- */

function renderEvidence() {
    const a = state.assessment;
    const src = state.source;
    const heat = a.assessments.heat;
    const d = heat.details;

    const kindLabel = {
        saved_copy: "Saved copy of an earlier NASA POWER response",
        retrieved: "Retrieved from NASA POWER this session",
        forecast: "Forecast model output retrieved this session",
    }[src.kind] || src.kind;
    const isForecast = state.mode === "forecast";
    const loc = src.location || {};
    const win = src.window || {};

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
                    <span style="--c:${HAZ.heat.color}">Heat: hours at or above ${esc(num(heat.threshold))} &deg;C</span>
                    <span style="--c:${HAZ.cold.color}">Cold: hours at or below ${esc(num(a.assessments.cold.threshold))} &deg;C</span>
                    <span class="shade heat-shade">Qualifying heat interval</span>
                    <span class="shade cold-shade">Qualifying cold interval</span>
                    <span class="dash" style="--c:${HAZ.heat.color}">Heat threshold ${esc(num(heat.threshold))} &deg;C</span>
                    <span class="dash" style="--c:${HAZ.cold.color}">Cold threshold ${esc(num(a.assessments.cold.threshold))} &deg;C</span>
                </div>
            </div>
            <div class="prov">
                <div class="eyebrow">Data provenance</div>
                <h3>Where these numbers come from</h3>
                <dl>
                    <div><dt>Source</dt><dd>${isForecast ? `<a href="https://open-meteo.com/" target="_blank" rel="noopener">${esc(src.provider)}</a>` : esc(src.provider)}</dd></div>
                    <div><dt>Dataset</dt><dd>${esc(src.dataset)}</dd></div>
                    <div><dt>Location</dt><dd>${esc(heat.location)} (${esc(loc.lat)}, ${esc(loc.lon)})</dd></div>
                    <div><dt>${isForecast ? "Forecast window" : "Observation window"}</dt><dd>${esc(isForecast ? fmtTime(win.start) : fmtDate8(win.start))} to ${esc(isForecast ? fmtTime(win.end) : fmtDate8(win.end))}
                        <span class="muted">(${esc(d.observation_start ? fmtTime(d.observation_start) : "n/a")} to ${esc(fmtTime(d.observation_end))})</span></dd></div>
                    <div><dt>Time standard</dt><dd>${esc(src.time_standard)} ${src.time_standard_origin ? `<span class="muted">(${esc(src.time_standard_origin)})</span>` : ""}</dd></div>
                    <div><dt>Data kind</dt><dd>${esc(kindLabel)}</dd></div>
                    <div><dt>Retrieved at</dt><dd>${esc(src.retrieved_at || "not recorded")}</dd></div>
                    <div><dt>Data status</dt><dd>${isForecast ? "Forecast model output, not live sensor readings or an official warning." : "Historical data, not a live observation. Hourly values are model-based estimates; EcoOps does not create hourly values the source did not provide."}</dd></div>
                    <div><dt>Missing data</dt><dd>Invalid or missing hours are excluded from statistics and break a heat or cold streak. ${esc(d.missing_observations)} of ${esc(d.expected_observations)} hours missing here.</dd></div>
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
    const a = state.assessment;
    const src = state.source;
    const heat = a.assessments.heat;
    const cold = a.assessments.cold;
    const series = (heat.details && heat.details.series) || [];
    const n = series.length;
    const box = $("chart");
    if (!n || series.every((p) => p.temp_c === null)) {
        box.innerHTML = `<div class="empty"><p>No valid hourly temperatures to plot.</p></div>`;
        return;
    }
    const heatThr = Number(heat.threshold);
    const coldThr = Number(cold.threshold);
    const atTrigger = (value, hazard) => (hazard === "cold" ? value <= coldThr : value >= heatThr);

    const W = 900, H = 340, ml = 58, mr = 18, mt = 22, mb = 56;
    const vals = series.map((p) => p.temp_c).filter((v) => v !== null);
    const yMin = Math.floor(Math.min(...vals, heatThr, coldThr) - 2);
    const yMax = Math.ceil(Math.max(...vals, heatThr, coldThr) + 2);
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

    // Label spacing adapts to the window length so 7-day forecasts stay legible.
    const labelEvery = n > 120 ? 12 : 6;
    let xticks = "";
    series.forEach((p, i) => {
        const hour = parseInt(p.time.slice(11, 13), 10);
        if (hour % labelEvery === 0) {
            xticks += `<line x1="${x(i)}" x2="${x(i)}" y1="${H - mb}" y2="${H - mb + 5}" stroke="#5f6a78" />
                       <text class="axis-label" x="${x(i)}" y="${H - mb + 18}" text-anchor="middle">${p.time.slice(11, 16)}</text>`;
            if (hour === 0) {
                xticks += `<text class="axis-label" x="${x(i)}" y="${H - mb + 32}" text-anchor="middle" style="fill:#e8ebf0">${p.time.slice(5, 10)}</text>`;
            }
        }
    });
    const axisTitles = `
        <text class="axis-label" x="${(ml + W - mr) / 2}" y="${H - 6}" text-anchor="middle">Time (${esc(src.time_standard)}), hourly</text>
        <text class="axis-label" transform="translate(14 ${(mt + H - mb) / 2}) rotate(-90)" text-anchor="middle">Temperature (&deg;C)</text>`;

    const shadeFor = (inc) => {
        const hz = HAZ[hazardOf(inc)];
        if (!isRisk(inc)) return "";
        return (inc.details.qualifying_streaks || []).map((s) => {
            const i0 = indexOf[s.start], i1 = indexOf[s.end];
            if (i0 === undefined || i1 === undefined) return "";
            const left = Math.max(ml, x(i0) - step / 2);
            const right = Math.min(W - mr, x(i1) + step / 2);
            return `<rect x="${left}" y="${mt}" width="${right - left}" height="${H - mt - mb}" fill="${hz.soft}" stroke="${hz.color}" stroke-opacity="0.55" stroke-dasharray="3 3" />
                <text class="axis-label" x="${(left + right) / 2}" y="${mt + 12}" text-anchor="middle" style="fill:${hz.color}">${esc(hz.name)} ${s.hours} h</text>`;
        }).join("");
    };

    let basePath = "";
    let hotPath = "";
    let coldPath = "";
    let open = false;
    series.forEach((p, i) => {
        if (p.temp_c === null) { open = false; return; }
        basePath += `${open ? "L" : "M"}${x(i)} ${y(p.temp_c)} `;
        open = true;
        const prev = series[i - 1];
        if (prev && prev.temp_c !== null) {
            if (atTrigger(prev.temp_c, "heat") && atTrigger(p.temp_c, "heat")) hotPath += `M${x(i - 1)} ${y(prev.temp_c)} L${x(i)} ${y(p.temp_c)} `;
            if (atTrigger(prev.temp_c, "cold") && atTrigger(p.temp_c, "cold")) coldPath += `M${x(i - 1)} ${y(prev.temp_c)} L${x(i)} ${y(p.temp_c)} `;
        }
    });

    const missing = series.map((p, i) => (p.temp_c === null
        ? `<line x1="${x(i)}" x2="${x(i)}" y1="${mt}" y2="${H - mb}" stroke="#5f6a78" stroke-dasharray="2 4" /><text class="axis-label" x="${x(i)}" y="${H - mb - 6}" text-anchor="middle">missing</text>`
        : "")).join("");

    const mark = (time, temp, above) => {
        const i = indexOf[time];
        if (i === undefined || temp === null || temp === undefined) return "";
        return `<circle cx="${x(i)}" cy="${y(temp)}" r="4.5" fill="#0b0d10" stroke="#e8ebf0" stroke-width="2" />
            <text class="axis-label" x="${x(i)}" y="${y(temp) + (above ? -10 : 17)}" text-anchor="middle" style="fill:#e8ebf0">${num(temp)} &deg;C</text>`;
    };
    const markers = mark(heat.details.peak_time, heat.max_temp, true) + mark(cold.details.min_time, cold.details.min_temp, false);

    box.innerHTML = `
        <svg viewBox="0 0 ${W} ${H}" role="img"
             aria-label="Hourly temperature in degrees Celsius from ${esc(fmtTime(series[0].time))} to ${esc(fmtTime(series[n - 1].time))}, with a heat threshold at ${esc(num(heatThr))} degrees and a cold threshold at ${esc(num(coldThr))} degrees. Longest heat run ${esc(heat.streak_hours)} hours; longest cold run ${esc(cold.streak_hours)} hours.">
            ${grid}
            ${shadeFor(heat)}
            ${shadeFor(cold)}
            <line x1="${ml}" x2="${W - mr}" y1="${y(heatThr)}" y2="${y(heatThr)}" stroke="${HAZ.heat.color}" stroke-dasharray="${HAZ.heat.dash}" stroke-width="1.5" />
            <text class="axis-label" x="${W - mr}" y="${y(heatThr) - 6}" text-anchor="end" style="fill:#ff8a70">Heat ${esc(num(heatThr))} &deg;C</text>
            <line x1="${ml}" x2="${W - mr}" y1="${y(coldThr)}" y2="${y(coldThr)}" stroke="${HAZ.cold.color}" stroke-dasharray="${HAZ.cold.dash}" stroke-width="1.5" />
            <text class="axis-label" x="${W - mr}" y="${y(coldThr) - 6}" text-anchor="end" style="fill:${HAZ.cold.color}">Cold ${esc(num(coldThr))} &deg;C</text>
            ${missing}
            <path d="${basePath}" fill="none" stroke="#cfd6df" stroke-width="1.6" stroke-linejoin="round" />
            <path d="${hotPath}" fill="none" stroke="${HAZ.heat.color}" stroke-width="2.8" stroke-linejoin="round" />
            <path d="${coldPath}" fill="none" stroke="${HAZ.cold.color}" stroke-width="2.8" stroke-linejoin="round" />
            ${xticks}
            ${axisTitles}
            ${markers}
            <line id="guide" x1="0" x2="0" y1="${mt}" y2="${H - mb}" stroke="#8f9aa9" stroke-width="1" visibility="hidden" />
            <circle id="guide-dot" r="4" fill="#2dd4bf" visibility="hidden" />
            <rect id="hit" x="${ml}" y="${mt}" width="${W - ml - mr}" height="${H - mt - mb}" fill="transparent" />
        </svg>`;

    const svg = box.querySelector("svg");
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
            const notes = [];
            if (atTrigger(p.temp_c, "heat")) notes.push(`heat trigger reached: at or above ${num(heatThr)} °C`);
            if (atTrigger(p.temp_c, "cold")) notes.push(`cold trigger reached: at or below ${num(coldThr)} °C`);
            readout.textContent = `${fmtTime(p.time)} ${src.time_standard}: ${p.temp_c.toFixed(1)} °C` +
                (notes.length ? `  (${notes.join("; ")})` : "");
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

const SECTION_DEFS = (forecastMode) => [
    ["observed_facts", forecastMode ? "Forecast facts" : "Observed facts", "observed", forecastMode ? "Forecast" : "Observed", forecastMode ? "Values supplied by the forecast model, not measured observations." : "Values read directly from the supplied data."],
    ["derived_metrics", "Derived metrics", "derived", "Derived", "Calculated from the observations by a stated rule."],
    ["operational_assumptions", "Operational assumptions", "assumed", "Assumed", "Not measured. Planning and interpretation limits."],
    ["recommended_actions", "Recommended actions", "recommended", "Recommended", "Suggestions to consider, not official instructions."],
];

function investigationBlock(inc, outcome, idx) {
    const hz = HAZ[hazardOf(inc)];
    const head = `
        <div class="inv-head hz-${hazardOf(inc)}">
            <h3><span class="swatch" style="background:${hz.color}"></span>${hz.name} risk investigation</h3>
            <span class="badge sev-${esc(inc.severity)}">${esc(inc.severity)}</span>
            <span class="fine">${esc(inc.incident_id)}</span>
        </div>`;
    if (outcome.status === "rejected") {
        return `<section class="inv-block" data-inv="${idx}">${head}${errorBlock(`${hz.name} investigation failed`, outcome.reason.message, "investigate")}</section>`;
    }
    const inv = outcome.value.investigation;
    const isStrands = inv.investigation_mode === "strands_ollama";
    const modeDescription = isStrands
        ? "Deterministic evidence checks plus a local Strands agent brief. The detector, not the agent, decides what qualified. Review AI-generated wording before acting."
        : inv.investigation_mode === "deterministic_fallback"
            ? "Strands/Ollama could not run. Deterministic evidence checks are shown instead; no agent brief was generated."
            : "Fixed rules applied to the evidence. This is not an AI agent.";
    const sections = SECTION_DEFS(state.mode === "forecast").map(([key, title, cls, tagText, blurb]) => {
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
    return `
        <section class="inv-block" data-inv="${idx}">
            ${head}
            <p class="mode">Mode: <strong>${esc(String(inv.investigation_mode).replaceAll("_", " "))}</strong>. ${esc(modeDescription)}</p>
            ${inv.fallback_reason ? `<p class="fine">${esc(inv.fallback_reason)}</p>` : ""}
            ${inv.qualification ? `<p class="qualified"><strong>Why it qualified:</strong> ${esc(inv.qualification)}</p>` : ""}
            ${inv.agent_brief ? `<div class="card agent-brief"><div class="card-head"><h3>Strands agent brief</h3><span class="tag t-recommended">AI-generated</span></div><p>${esc(inv.agent_brief.text)}</p><p class="basis">${esc(inv.agent_brief.basis)}</p></div>` : ""}
            <ol class="checks">
                ${(inv.checks || []).map((c) => `
                    <li class="check"><span class="mark" aria-hidden="true"></span>
                        <div><div>${esc(c.label)}</div><div class="result">${esc(c.result)}</div></div></li>`).join("")}
            </ol>
            <div class="sections">${sections}</div>
        </section>`;
}

async function runInvestigation() {
    const root = $("investigate-root");
    const incidents = state.incidents.slice();
    if (!incidents.length) return;
    root.innerHTML = loadingBlock("Checking evidence and running the configured investigator...");

    const outcomes = await Promise.allSettled(
        incidents.map((inc) => api(modePath("/investigate", hazardOf(inc))))
    );
    if (outcomes.every((o) => o.status === "rejected")) {
        root.innerHTML = errorBlock("Investigation failed", outcomes[0].reason.message, "investigate");
        return;
    }
    root.innerHTML = incidents.map((inc, i) => investigationBlock(inc, outcomes[i], i)).join("");

    for (const el of root.querySelectorAll(".check")) {
        await sleep(90);
        el.classList.add("done");
    }

    state.stage.investigated = true;
    updatePipeline();
}

/* ---------- response plan ---------- */

function planCard(a) {
    return `
        <article class="action-card hz-${esc(a.hazard)}">
            <div class="action-id">${esc(a.action_id)}</div>
            <div>
                <h3>${esc(a.name)}</h3>
                <p>${esc(a.reason)}</p>
                <div class="chips">
                    <span class="chip ${a.hazard === "cold" ? "cold" : "hot"}">${esc(HAZ[a.hazard] ? HAZ[a.hazard].name : a.hazard)}</span>
                    <span class="chip">${esc(a.resource)}</span>
                    <span class="chip warn">${esc(a.teams_required)} team${a.teams_required > 1 ? "s" : ""}</span>
                    <span class="chip warn">${esc(a.budget_units)} budget units</span>
                    <span class="chip warn">${esc(a.duration_hours)} h</span>
                </div>
            </div>
            <span class="tag t-recommended">${esc(String(a.status).toLowerCase())}</span>
        </article>`;
}

async function generatePlan() {
    const root = $("plan-root");
    root.innerHTML = loadingBlock("Generating response plan...");

    let plan;
    try {
        plan = await api(modePath("/response", "all"));
    } catch (err) {
        root.innerHTML = errorBlock("Could not generate the plan", err.message, "plan");
        return;
    }

    state.plan = plan;

    if (plan.status !== "RESPONSE_RECOMMENDED" || !Array.isArray(plan.actions) || !plan.actions.length) {
        root.innerHTML = plan.status === "ASSESSMENT_UNAVAILABLE"
            ? `<div class="empty"><p>No plan can be generated because the temperature data could not be assessed.</p></div>`
            : `<div class="empty"><p>No response plan is needed: ${state.mode === "forecast" ? "the available forecast did not meet the configured heat or cold trigger" : "no sustained heat or cold event was detected in this historical window"}.</p></div>`;
        return;
    }

    state.order = plan.actions.slice().sort((a, b) => a.priority - b.priority).map((a) => a.action_id);
    state.selected = new Set(state.order);

    const groups = (plan.plans || []).map((p) => {
        const hz = HAZ[p.hazard] || HAZ.heat;
        return `
            <div class="plan-group hz-${esc(p.hazard)}">
                <h3 class="plan-group-title"><span class="swatch" style="background:${hz.color}"></span>${hz.name} response plan
                    <span class="fine">${esc(p.incident_id)} &middot; ${esc(p.trigger.severity)}</span></h3>
                <div class="action-list">${p.actions.map(planCard).join("")}</div>
            </div>`;
    }).join("");

    root.innerHTML = `
        <div class="notice">${esc(plan.disclaimer)}</div>
        <div class="notice assumed"><span class="tag t-assumed">Assumed</span>&nbsp; ${esc(plan.assumption_note)}</div>
        ${groups}`;

    state.stage.planned = true;
    updatePipeline();
    buildSimulation();
}

/* ---------- simulation ---------- */

function buildSimulation() {
    $("simulate-root").innerHTML = `
        <div class="notice">Simulates operational resource allocation only, across every action in the combined plan.
            It does not predict temperature reduction, health outcomes or real-world effectiveness.</div>
        <div class="notice assumed"><span class="tag t-assumed">Hypothetical</span>&nbsp; Teams, budget and window are
            planning inputs you set here. They are not data about any real teams, facilities or funds.</div>
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
                    <span class="meta">${esc(a.hazard)} &middot; ${esc(a.teams_required)} team${a.teams_required > 1 ? "s" : ""} &middot; ${esc(a.budget_units)} units &middot; ${esc(a.duration_hours)} h</span>
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
        const data = await api(modePath("/simulate", "all"), { method: "POST", body: JSON.stringify(request) });
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
