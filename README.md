# EcoOps

**Anticipate the risk. Investigate the evidence. Prepare the response.**

EcoOps is a decision-support prototype for proactive environmental operations. Its primary mode screens the next seven days of **Delhi hourly temperature forecasts** from Open-Meteo for configurable sustained-heat risk windows. It can investigate the forecast evidence, propose preparation actions, and simulate whether assumed teams, budget and time are sufficient. A separate historical replay mode uses NASA POWER data for a repeatable demonstration.

```
Open-Meteo forecast -> projected risk window -> evidence-backed investigation
                    -> preparation plan -> resource simulation -> compare allocations

NASA POWER historical replay -------------------------------------^ (demo fallback)
```

Forecasts are model predictions, not live sensor readings, certainties or official warnings. No forecast is fabricated: if the feed is unavailable, switch to historical replay. The app runs locally without an AWS account or paid API. An optional AWS Strands Agents SDK integration can add a local Ollama-generated brief; it requires a downloaded local model.

## What is real, derived, assumed

| Type | Examples | Where it comes from |
|---|---|---|
| **Forecast** | Hourly forecast temperature, forecast peak and timing | Open-Meteo forecast API |
| **Historical** | Hourly historical temperature, peak reading and its time | NASA POWER `T2M` |
| **Derived** | Average, hours above trigger, longest hot streak, severity | Calculated from the observations by a stated rule |
| **Assumed** | The 35 °C / 4 h / 8 h rules; team counts, budget units, durations of each action | Chosen for this demo. Not measured, not official |

The UI tags every investigation line with one of these. EcoOps never fabricates readings, health outcomes, casualties
prevented or temperature reductions. The simulation models **resource allocation only**.

## Primary workflow: forecast screening

The UI opens in forecast mode and requests seven days of hourly temperature values from Open-Meteo for Delhi. EcoOps applies its explicitly configurable demonstration rule (4+ consecutive hours at or above 35 °C; HIGH at 8+ hours) to identify a **projected heat-risk window**. A forecast match is not an observed incident or an official heatwave classification. If no match is found, EcoOps says so rather than manufacturing a risk.

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
```


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
2. Hover the chart to read single hours. Shaded bands are the qualifying hot streaks; dashed lines mark missing hours.
3. **Run investigation**: five deterministic checks, then Forecast (or Observed in replay) / Derived / Assumed / Recommended sections.
4. **Generate response plan**: four recommended actions with explanation, resource needs and status.
5. In **Response simulation**, drag *Available teams*, *Budget* and *Response window*.
6. Reorder or untick actions. Watch actions flip between **Executable** and **Blocked** (reason: `TEAMS`, `BUDGET` or `TIME`).
7. Read the schedule lanes, the resource meters and the table comparing your allocation with the full plan.
8. **Pin** up to four scenarios and compare them side by side.

Good scenarios to show: defaults (3 of 4 actions, water check blocked on budget); budget 170 (all four); window 5 h
(water check blocked on time); teams 1 (water check blocked, needs two teams).

## Detection rule (prototype settings)

- Trigger: at least **4 consecutive** valid hourly readings **at or above 35 °C**.
- Severity: MEDIUM at 4+ consecutive hours, HIGH at 8+.
- A missing hour (`-999`, non-numeric, or absent timestamp) is excluded from statistics **and breaks a streak**. The
  prototype used to join hot stretches across gaps; that bug is fixed and covered by a test.
- Historical replay window: Delhi (28.6139, 77.2090), 2025-05-01 to 2025-05-03. Forecast mode instead uses the current seven-day Open-Meteo forecast and displays its actual returned window.
- These are EcoOps operational settings, not a meteorological heatwave definition. Metrics are recalculated from the
  data on every request; none are hardcoded.
- NASA POWER hourly data defaults to **Local Solar Time (LST)**, not Delhi clock time (IST). The UI labels timestamps
  with the time standard reported by the response, or the documented default when the response does not say.

The earlier prototype recorded 72 valid observations, a peak near 38.8 °C and an 8-hour streak for this window. Compare
that with what the app shows after you fetch the data. If they differ, trust the data and investigate the difference.

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
| `GET /detect?mode=forecast` | Projected risk screening from hourly Open-Meteo forecasts (default in UI) |
| `GET /detect?mode=historical` | Historical NASA POWER replay; `?refresh=true` re-fetches NASA POWER |
| `GET /response?mode=forecast` | Preparation plan when forecast values meet the trigger |
| `GET /investigate?mode=forecast` | Forecast evidence package and investigation |
| `GET /simulate?mode=forecast` | Simulation with default resources |
| `POST /simulate?mode=forecast` | `{"teams": 2, "budget": 120, "window_hours": 6, "action_order": ["A1","A2"]}` |

Invalid input (negative teams, unknown action id, and so on) returns `422`. Simulating without an incident returns `409`.
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
    incident_service.py        builds the incident once per request from cached data
    investigation.py           evidence package + prompt for a future LLM investigator
    investigator.py            Investigator interface + DeterministicInvestigator
    response_engine.py         action catalog and plan
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

## What is implemented, and what is not

**Implemented:** everything above, with no cloud dependency.

**AWS integration status:** the repository now includes the AWS open-source Strands Agents SDK and an optional local Ollama-backed investigator. This is not an AWS-hosted deployment and requires the local model to be available. Do not claim the Strands agent ran unless the UI reports `strands ollama` and shows its generated brief in your own demo. Confirm that this satisfies the organisers' interpretation of the current rules before submission.

## Before you submit

- [ ] Run `fetch_demo_data.py` and check the numbers against what you expect.
- [ ] Add and verify the AWS component, and make sure the demo video shows it.
- [ ] Confirm the submission deadline time on the event schedule page. It listed only "Sunday, Oct 11".
- [ ] Public GitHub repository, demo video of at most 3 minutes on YouTube (public or unlisted), short write-up.
- [ ] Optional: publish a blog post on AWS Builder Center and link it (separate prize).
- [ ] Say in the video that the window is historical and the simulation models allocation, not outcomes.
