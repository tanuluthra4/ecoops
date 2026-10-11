# EcoOps

**Anticipate the risk. Investigate the evidence. Prepare the response.**

EcoOps is an environmental operations decision-support prototype that turns hourly temperature data into an inspectable workflow: automatic heat/cold risk screening, evidence-backed investigation, response planning, and resource-allocation simulation.

- **Live demo:** https://ecoops-1.onrender.com/
- **Demo video:** https://youtu.be/PCa2lDuLzWE
- **Repository:** https://github.com/tanuluthra4/ecoops

> **Important:** EcoOps is a prototype, not an official warning system. Its thresholds and resource costs are demonstration assumptions. It does not dispatch teams, verify local facilities, or predict health outcomes or temperature reductions.

## At a glance

- Screens the next seven days of Delhi hourly temperature forecasts from [Open-Meteo](https://open-meteo.com/) for sustained heat **and** cold conditions.
- Supports a historical replay using [NASA POWER](https://power.larc.nasa.gov/) data for a repeatable demonstration.
- Distinguishes source observations/predictions, derived metrics, assumptions, and recommendations.
- Builds preparation actions and simulates whether assumed team, budget, and time constraints allow those actions to run.
- Includes an optional local investigator using the open-source **AWS Strands Agents SDK** with an Ollama model.
- Runs without AWS cloud credentials; the public app is hosted on Render, not AWS.

## How it works

```text
Open-Meteo forecast ─┐
                     ├─> Heat + cold screening ─> Evidence-backed investigation
NASA POWER replay ───┘                              │
                                                    v
                                      Combined preparation plan
                                                    │
                                                    v
                                    Resource-allocation simulation
                                                    │
                                                    v
                                    Compare feasible/blocked actions
```

Forecast mode is the default. EcoOps assesses both hazards from the same hourly series; users choose the data mode, not a heat-versus-cold selector. If no rule qualifies, the app reports that result. If usable data is unavailable, it reports an unavailable assessment rather than treating missing data as “no risk” or fabricating substitute readings.

## Data, rules, and assumptions

| Category | Examples | Source or method |
|---|---|---|
| Forecast data | Hourly forecast temperature and forecast timing | Open-Meteo forecast API |
| Historical data | Hourly temperature and its reported timestamp | NASA POWER `T2M` |
| Derived metrics | Average, qualifying hours, longest streak, severity | Calculated from the returned hourly series |
| Demonstration assumptions | Temperature thresholds, streak lengths, team counts, budget units, action durations | Configured prototype rules and action catalog |

### Demonstration detection rules

- **Heat:** at least 4 consecutive valid hourly readings at or above **35 °C**.
- **Cold:** at least 4 consecutive valid hourly readings at or below **5 °C**.
- **HIGH severity:** a qualifying streak of at least 8 hours.
- Missing or invalid readings are excluded from statistics and break a streak.
- Heat and cold streaks are evaluated independently. If both qualify, each keeps its own incident and investigation.

These are configurable **EcoOps demo settings**, not official IMD criteria, medical guidance, or a formal meteorological definition. A qualified authority must validate thresholds before any real-world use.

### Forecast and historical modes

- **Forecast:** requests the current seven-day hourly forecast for Delhi and displays the actual returned time window. Forecast values are model predictions, not sensor readings or certainties.
- **Historical replay:** uses a repeatable Delhi demonstration window from **1–3 May 2025**, based on NASA POWER data. NASA POWER hourly timestamps default to Local Solar Time (LST), which is not the same as India Standard Time (IST); use the time standard reported by the response.
- Forecast mode requires internet access. Historical replay can work offline after a NASA POWER response has been saved locally.
- EcoOps does not silently substitute historical values when a forecast request fails.

## Try the demo

1. Open the [EcoOps live demo](https://ecoops-1.onrender.com/).
2. Review the forecast chart, retrieval details, and data provenance.
3. Run the investigation for any qualifying risk.
4. Generate the combined response plan.
5. In the resource simulation, adjust available teams, budget, and response window.
6. Reorder or disable actions and compare which actions are executable or blocked, including the reason (`TEAMS`, `BUDGET`, or `TIME`).
7. Pin up to four scenarios to compare allocations side by side.

A useful repeatable demonstration is to start with the default resources, then change budget, response time, or team count to see how feasibility changes. The simulator demonstrates allocation logic only; it does not estimate real-world outcomes.

## Tech stack

- **Backend:** Python, FastAPI
- **Frontend:** HTML, CSS, vanilla JavaScript
- **Data sources:** Open-Meteo forecast API, NASA POWER historical data
- **Optional local agent:** AWS Strands Agents SDK + Ollama
- **Testing:** pytest and JavaScript syntax checking
- **Deployment:** Render

## Quick start (Windows PowerShell)

The commands below assume you have cloned the repository and have Python installed. Run commands with `python -m` to avoid issues with blocked executable launchers on some Windows systems.

```powershell
cd ecoops
python -m pip install -r backend\requirements-dev.txt

# Optional: fetch and save the real NASA POWER replay response while online
python scripts\fetch_demo_data.py

# Start in deterministic mode; a local language model is not required
cd backend
python -m uvicorn app:app --port 8000
```

Open <http://127.0.0.1:8000/>. The app redirects to the UI. Forecast mode requires internet access. Historical replay attempts to fetch NASA POWER data if no saved response exists; after a successful response is saved, replay can work offline.

### Run tests

From the repository root:

```powershell
python -m pytest
node --check frontend\app.js
```

The automated suite uses synthetic series to test detection rules, gaps and malformed data, both modes, combined plans, simulation, and Strands/Ollama fallback behavior. It does not automate browser interactions; chart and button behaviour should be checked manually.

## Optional: local Strands + Ollama investigator

EcoOps includes an optional integration with the open-source **Strands Agents SDK** from AWS. It can use a locally running Ollama model to produce a concise investigation brief. The integration was tested locally; it is **not** an AWS-hosted service and is not required to run the project.

1. Install Ollama and ensure it is running.
2. Download the example model:

   ```powershell
   ollama pull qwen2.5:1.5b
   ```

3. In the PowerShell window used to start EcoOps, set the mode before launching FastAPI:

   ```powershell
   $env:ECOOPS_INVESTIGATOR = "strands_ollama"
   $env:ECOOPS_OLLAMA_MODEL = "qwen2.5:1.5b"
   cd ecoops\backend
   python -m uvicorn app:app --port 8000
   ```

If the SDK, Ollama server, or model is unavailable, EcoOps labels the deterministic fallback rather than claiming an agent ran. The agent may add a short brief; risk screening, evidence metrics, response actions, and resource simulation remain deterministic. Review generated text before using it for decisions.

To return to deterministic mode, set `$env:ECOOPS_INVESTIGATOR = "deterministic"` before restarting the server. Other supported configuration variables include `ECOOPS_OLLAMA_HOST`.

**AWS disclosure:** the project uses the Strands Agents SDK as an open-source tool in a local setup. The deployed application runs on Render; no AWS managed cloud services are integrated into the deployed app.

## Resource simulation model

- Actions are considered in the priority order selected by the user.
- Each action requires its configured number of teams simultaneously for its duration; teams can be reused after an action finishes.
- An action runs only when team, budget, and response-window constraints are satisfied.
- A blocked action consumes no resources, and later actions are still considered.
- The full-plan reference assumes every action can run in parallel and is used for comparison.
- Identical inputs produce identical simulation results.

Per-action team counts, budget units, and durations are assumptions defined in `backend/services/response_engine.py` and labelled in the UI.

## API overview

| Route | Purpose |
|---|---|
| `GET /` | Redirects to the UI |
| `GET /health` | Liveness check |
| `GET /assess?mode=forecast` | Heat and cold assessments, overall status, ranked incident IDs, and provenance |
| `GET /detect?mode=forecast&hazard=heat` | One hazard's incident; `hazard` can be `heat` or `cold` |
| `GET /detect?mode=historical` | Historical NASA POWER replay; `?refresh=true` re-fetches data |
| `GET /response?mode=forecast&hazard=all` | Combined response plan for qualifying risks |
| `GET /investigate?mode=forecast&hazard=heat` | Evidence package and investigation for one risk |
| `GET /simulate?mode=forecast` | Simulation with default resources |
| `POST /simulate?mode=forecast&hazard=all` | Runs simulation with supplied resources and action order |

Example request body for `POST /simulate`:

```json
{
  "teams": 2,
  "budget": 120,
  "window_hours": 6,
  "action_order": ["A1", "A2"]
}
```

Invalid values (for example, negative team counts, unknown action IDs, or invalid `mode`/`hazard`) return `422`. Simulation without a qualifying risk or with an unavailable assessment returns `409` with a distinct message. Interactive API documentation is available at <http://127.0.0.1:8000/docs> when running locally.

## Project structure

```text
backend/
  app.py                       FastAPI routes and frontend serving
  config.py                    Rules, location, window, and file paths
  models/incident.py            Incident data model
  services/
    forecast.py                 Open-Meteo retrieval, caching, provenance
    nasa_power.py                NASA POWER retrieval, saved copy, provenance
    incident_engine.py           Gap-aware heat/cold detection
    incident_service.py          Combined assessment and incident ranking
    investigation.py             Evidence package and investigator prompt
    investigator.py              Deterministic and optional Strands/Ollama investigators
    response_engine.py           Heat/cold action catalogs and response plans
    simulation.py                Resource allocation and baseline comparison
  tests/                         Automated backend tests
frontend/                        HTML, CSS, and vanilla JavaScript
scripts/fetch_demo_data.py       Saves a NASA POWER demonstration response
 data/demo_incident.json          Created by the fetch step (real NASA POWER response)
```

## Failure handling and troubleshooting

- Forecast data is cached in memory for 10 minutes. Historical mode checks memory, then a saved response, then NASA POWER.
- Requests use a 25-second timeout. Timeouts, HTTP errors, invalid JSON, and unexpected response shapes result in an unavailable-data state rather than fabricated readings.
- If forecast data is unavailable, switch to historical replay. If no saved historical response exists, run `python scripts\fetch_demo_data.py` while online.

| Problem | What to try |
|---|---|
| `pip.exe` is blocked by an Application Control policy | Use `python -m pip install -r backend\requirements-dev.txt` |
| `uvicorn` is not recognised or blocked | Use `python -m uvicorn app:app --port 8000` from the `backend` directory |
| The page cannot reach the backend | Start the server from `backend` and check that the chosen port matches the URL |
| No temperature data is available | Check internet access or create the saved NASA POWER response while online |
| Port 8000 is already in use | Start with `--port 8001` and open <http://127.0.0.1:8001/> |
| You opened `frontend/index.html` directly | Prefer <http://127.0.0.1:8000/> while the backend is running |

## Limitations and responsible use

- EcoOps is a prototype for decision support, not an official alert or emergency-response system.
- Forecasts are model predictions and can change. Data services may be unavailable.
- Thresholds, severity rules, action costs, staffing requirements, and durations are configurable demonstration assumptions—not official standards or measured operational costs.
- The app does not model humidity, wind chill, exposure, population vulnerability, local facilities, or official alerts.
- The resource simulator models feasibility only. It does not dispatch real teams or predict temperature reductions, health outcomes, or casualties prevented.
- Recommendations require human review and validation by qualified authorities before any real-world use.

## Implementation status

- **Implemented:** forecast retrieval, historical replay, automatic heat/cold screening, provenance and evidence display, investigation workflow, response planning, and resource-allocation simulation.
- **Optional:** local Strands Agents SDK + Ollama investigation brief, active only when the configured local integration succeeds.
- **Not implemented:** official warnings, real dispatch/notifications, AWS-hosted inference or deployment, and measured real-world outcome prediction.

---

Built by **Tanu Luthra** as a solo project for Environmental Hacks 2026.
