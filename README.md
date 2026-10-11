# EcoOps

**Anticipate the risk. Investigate the evidence. Prepare the response.**

EcoOps is a decision-support prototype for proactive environmental operations. Its primary mode screens the next seven days of **Delhi hourly temperature forecasts** from Open-Meteo for configurable sustained **heat and cold** risk windows, with no manual hazard selector. It can investigate the forecast evidence, propose preparation actions, and simulate whether assumed teams, budget and time are sufficient. A separate historical replay mode uses NASA POWER data for a repeatable demonstration.

```
Open-Meteo forecast -> automatic heat + cold screening -> evidence-backed investigation (per risk)
                    -> combined preparation plan -> resource simulation -> compare allocations

NASA POWER historical replay -------------------------------------^ (demo fallback)
```

Forecasts are model predictions, not live sensor readings, certainties or official warnings. No forecast is fabricated: if the feed is unavailable, switch to historical replay. The app runs locally without an AWS account or paid API. An optional AWS Strands Agents SDK integration can add a local Ollama-generated brief; it requires a downloaded local model.

## What is real, derived, assumed

| Type | Examples | Where it comes from |
|---|---|---|
| **Forecast** | Hourly forecast temperature, forecast peak and timing | Open-Meteo forecast API |
| **Historical** | Hourly historical temperature, peak reading and its time | NASA POWER `T2M` |
| **Derived** | Average, hours above trigger, longest hot streak, severity | Calculated from the observations by a stated rule |
| **Assumed** | The 35 °C heat / 5 °C cold, 4 h / 8 h rules; team counts, budget units, durations of each action | Chosen for this demo. Not measured, not official |

The UI tags every investigation line with one of these. EcoOps never fabricates readings, health outcomes, casualties
prevented or temperature reductions. The simulation models **resource allocation only**.

## Primary workflow: forecast screening

The UI opens in forecast mode and requests seven days of hourly temperature values from Open-Meteo for Delhi. EcoOps applies its explicitly configurable demonstration rules to the same data for **both** hazards (heat: 4+ consecutive hours at or above 35 °C; cold: 4+ consecutive hours at or below 5 °C; HIGH at 8+ hours) to identify **projected heat-risk and/or cold-risk windows**. A forecast match is not an observed incident or an official heatwave classification. If no match is found, EcoOps says so rather than manufacturing a risk.

Use **Historical replay** in the header to switch to the NASA POWER May 1–3, 2025 demonstration window. This fallback is useful when the forecast service is unavailable or when a repeatable heat-event demo is needed. Use the header refresh button to fetch the selected source again.

Open-Meteo is credited in the data provenance panel. The forecast API is a third-party service and requires an internet connection; there is no guarantee of network availability. This prototype does not forecast health outcomes or verify local cooling facilities, populations, staffing, or official alerts.

## Quick start (Windows PowerShell)

Use `python -m ...` throughout. On machines with Application Control, `pip.exe` and similar launchers can be blocked
while `python.exe` is not.

```powershell
cd ecoops
python -m pip install -r backend\requirements-dev.txt

# Optional, while online: saves the real NASA POWER historical replay to data\demo_incident.json
python scripts\fetch_demo_data.py

# Optional: download a small local model once (requires internet and disk space)
# ollama pull qwen2.5:1.5b

# Start the app in deterministic mode (works without a local model)
cd backend
python -m uvicorn app:app --port 8000
```

Open <http://127.0.0.1:8000/> (it redirects to `/ui/`). The UI opens in forecast mode. The forecast mode requires internet access; historical replay can use a saved NASA POWER response offline.

If you skip `fetch_demo_data.py`, the app tries NASA POWER on first use of historical replay and saves the response. Once the file exists, historical replay works offline.

### Run the tests

```powershell
cd ecoops\backend
python -m pytest
node --check ..\frontend\app.js
```

The suite uses synthetic series only. It covers detection rules (4 h / 8 h, gaps, malformed data), both modes, the combined plan and simulation, and Strands/Ollama fallback. Browser behaviour (chart, buttons) is checked manually with the demo checklist; the suite does not drive a browser.


### Optional AWS Strands agent (local Ollama model)

The project includes the AWS open-source Strands Agents SDK. To run its local-model investigator, install Ollama, download a model, start Ollama, then set the mode **before** starting FastAPI:

```powershell
# In a separate PowerShell window, if Ollama is installed and on PATH:
ollama pull qwen2.5:1.5b

# In the PowerShell window used to run EcoOps:
$env:ECOOPS_INVESTIGATOR = "strands_ollama"
$env:ECOOPS_OLLAMA_MODEL = "qwen2.5:1.5b"
cd ecoops\backend
python -m uvicorn app:app --port 8000
```

If `ollama` is not on PATH, use its full executable path or run the Ollama desktop app. The agent mode is only active when the local model call succeeds. If the SDK/server/model is unavailable, EcoOps labels the deterministic fallback instead of claiming an agent ran. The observed facts, derived metrics, response actions and allocation simulation remain deterministic; only the additional short operational brief is generated by the agent and must be reviewed by a human. This uses the Strands SDK as an open-source tool, not an AWS-hosted service.

To return to the default deterministic mode, close the server or run `$env:ECOOPS_INVESTIGATOR = "deterministic"` before restarting.

## Demo path

1. Open the command center. Forecast mode screens the next seven days and labels any trigger match as a projected risk, not an observed incident. The chart and data provenance show the forecast source and retrieval time.
2. Hover the chart to read single hours. Both threshold lines (red heat, blue cold) are always drawn; shaded bands are qualifying heat/cold intervals; dashed vertical lines mark missing hours.
3. **Run investigation**: one block per qualifying risk, each with five deterministic checks, a "why it qualified" line, then Forecast (or Observed in replay) / Derived / Assumed / Recommended sections.
4. **Generate response plan**: heat actions (A1-A4) and/or cold actions (C1-C4), grouped per risk; the simulation covers all of them.
5. In **Response simulation**, drag *Available teams*, *Budget* and *Response window*.
6. Reorder or untick actions. Watch actions flip between **Executable** and **Blocked** (reason: `TEAMS`, `BUDGET` or `TIME`).
7. Read the schedule lanes, the resource meters and the table comparing your allocation with the full plan.
8. **Pin** up to four scenarios and compare them side by side.

Good scenarios to show: defaults (3 of 4 actions, water check blocked on budget); budget 170 (all four); window 5 h
(water check blocked on time); teams 1 (water check blocked, needs two teams).

## Automatic heat and cold detection (prototype settings)

Every load calls `GET /assess`, which screens the **same** hourly series for heat and for cold. There is no heat/cold
selector; only the data mode (forecast / historical) is chosen. The overall status is one of:

| Status | Meaning |
|---|---|
| Heat risk detected | only the heat rule qualified |
| Cold risk detected | only the cold rule qualified |
| Both risks detected | both qualified; each keeps its own incident, investigation, plan and actions |
| No qualifying temperature risk | data was assessed and neither rule qualified (a valid result) |
| Assessment unavailable | no usable data; **not** the same as "no risk" and nothing was evaluated |

- Heat: at least **4 consecutive** valid hourly readings **at or above 35 °C**. Cold: **at or below 5 °C**. HIGH at 8+ hours for each.
- Streaks are independent per hazard. The result records the longest streak, every qualifying interval, the peak (heat) / lowest (cold) temperature and its timestamp.
- A missing hour (`-999`, non-numeric, or absent timestamp) is excluded from statistics **and breaks a streak**.
- Qualifying incidents are ordered by severity, then streak length. Incident ids are fixed per mode and hazard, so repeating a request never creates duplicates.
- Historical replay window: Delhi (28.6139, 77.2090), 2025-05-01 to 2025-05-03. Forecast mode uses the current seven-day Open-Meteo forecast and displays its actual returned window. Historical mode never invents hourly data the source did not provide.
- These are EcoOps demo settings, **not** official IMD criteria, medical guidance or a meteorological definition. A qualified authority must validate any real thresholds.
- NASA POWER hourly data defaults to **Local Solar Time (LST)**, not Delhi clock time (IST). The UI labels timestamps with the time standard reported by the response, or the documented default.

### Configuring the rules

Defined once in `backend/config.py`. Optional environment variables override them (invalid values fall back to defaults):
`ECOOPS_HEAT_THRESHOLD_C` (35), `ECOOPS_COLD_THRESHOLD_C` (5), `ECOOPS_MIN_STREAK_HOURS` (4), `ECOOPS_HIGH_STREAK_HOURS` (8).
Other variables: `ECOOPS_DATA_FILE`, `ECOOPS_INVESTIGATOR` (`deterministic` or `strands_ollama`), `ECOOPS_OLLAMA_MODEL`, `ECOOPS_OLLAMA_HOST`.

## Simulation model

- Actions are handled in the priority order you set.
- Each action needs `teams_required` teams at once for `duration_hours`. Teams are reused when they finish.
- An action runs only if teams, budget and time all allow it. Otherwise it is **blocked** with the specific reason,
  consumes nothing, and later actions are still considered.
- The "full plan" reference is every action running in parallel: it shows the teams, budget and time that would take.
- Deterministic: the same inputs always give the same result.

Per-action team counts, budget units and durations are in `backend/services/response_engine.py` and are labelled as
assumptions in the UI.

## API

| Route | Purpose |
|---|---|
| `GET /` | Redirects to the UI |
| `GET /health` | Liveness check |
| `GET /assess?mode=forecast` | **Used by the UI.** Heat and cold assessments, overall status, ranked incident ids, provenance |
| `GET /detect?mode=forecast&hazard=heat\|cold` | One hazard's incident (kept for compatibility; defaults to heat) |
| `GET /detect?mode=historical` | Historical NASA POWER replay; `?refresh=true` re-fetches NASA POWER |
| `GET /response?mode=forecast&hazard=all` | Combined plan for every qualifying risk (`heat`, `cold` or `all`) |
| `GET /investigate?mode=forecast&hazard=heat\|cold` | Evidence package and investigation for one risk |
| `GET /simulate?mode=forecast` | Simulation with default resources |
| `POST /simulate?mode=forecast&hazard=all` | `{"teams": 2, "budget": 120, "window_hours": 6, "action_order": ["A1","A2"]}` |

Invalid input (negative teams, unknown action id, bad `mode`/`hazard`) returns `422`. Simulating with no qualifying risk, or with the assessment unavailable, returns `409` with different messages.
Interactive docs: <http://127.0.0.1:8000/docs>.

## Architecture

```
backend/
  app.py                       thin FastAPI routes + serves the frontend
  config.py                    rules, location, window, file paths
  models/incident.py           Incident dataclass
  services/
    forecast.py                Open-Meteo forecast retrieval, caching, provenance
    nasa_power.py              NASA POWER historical retrieval, saved copy, provenance
    incident_engine.py         detection (gap-aware streaks)
    incident_service.py        screens heat AND cold from one data load; ranks incidents; overall status
    investigation.py           evidence package + prompt for a future LLM investigator
    investigator.py            Investigator interface; hazard-aware DeterministicInvestigator; optional Strands/Ollama
    response_engine.py         heat (A1-A4) and cold (C1-C4) action catalogs, per-risk and combined plan
    simulation.py              allocation simulator and baseline comparison
  tests/                       automated backend tests
frontend/                      plain HTML, CSS, JavaScript (no framework, no external requests)
scripts/fetch_demo_data.py     saves the NASA POWER demo window locally
data/demo_incident.json        created by the fetch step (real NASA POWER response)
```

## Data and failure handling

- Forecast mode requests Open-Meteo's seven-day hourly forecast and caches it in memory for 10 minutes. It never falls back to historical values silently.
- Historical mode uses memory, then saved copy (`data/demo_incident.json`), then NASA POWER.
- Requests have a 25 s timeout. Timeouts, HTTP errors, bad JSON and unexpected shapes all return "no data", never a crash.
- If the forecast is unavailable, the UI shows an error state and lets the user switch to historical replay. If historical data is unavailable, it explains how to create the saved copy. **No substitute data is ever generated.**
- If `meta.synthetic` is true in the saved file, the UI shows a red banner. Tests use synthetic data only.

## Troubleshooting

| Problem | Fix |
|---|---|
| `pip.exe ... blocked by an Application Control policy` | Use `python -m pip install ...` |
| `uvicorn` not recognised or blocked | Use `python -m uvicorn app:app --port 8000` |
| "Cannot reach the EcoOps backend" in the page | Start the server from the `backend` folder; check the port |
| "No temperature data available" | Run `python scripts\fetch_demo_data.py` while online |
| Port 8000 in use | Pick another: `--port 8001` and open that port |
| Opened `index.html` by double-clicking | Works only if the backend runs on port 8000; prefer `http://127.0.0.1:8000/` |

## Implementation status

EcoOps is a local decision-support prototype that combines weather data, rule-based automatic heat and cold risk screening, evidence-based investigation, response planning, and resource-allocation simulation.

- **Forecast screening:** Retrieves hourly Delhi temperature forecasts from Open-Meteo and evaluates them against configurable demonstration thresholds.
- **Historical replay:** Uses NASA POWER data for a repeatable historical demonstration.
- **Investigation:** Presents available evidence and distinguishes forecast or historical data, derived metrics, assumptions, and recommendations.
- **Response planning:** Recommends preparation actions when the configured risk trigger is met.
- **Resource simulation:** Evaluates action feasibility against available teams, budget, and response time.
- **Optional AWS open-source component:** EcoOps includes an optional integration with the Strands Agents SDK and a locally hosted Ollama model. This is not an AWS-hosted deployment. The agent is only considered active when the configured integration successfully runs.

## Limitations

EcoOps is a prototype for decision support, not an official warning system. Forecasts are model predictions and may change. The demonstration thresholds and resource costs are assumptions, not official standards or measured operational costs.

The simulation evaluates resource allocation; it does not predict health outcomes, casualties prevented, or temperature reductions. Recommendations require human review before real-world use. Humidity, wind chill, exposure and local facilities are not modelled. EcoOps is not production-ready.

## Running the project

Follow the [Quick start](#quick-start-windows-powershell) instructions to run EcoOps locally. Forecast mode requires internet access. Historical replay can use a previously saved NASA POWER response.

For the demonstration, clearly identify whether the displayed data is forecast or historical, and whether the investigator is running in deterministic or Strands-backed mode.