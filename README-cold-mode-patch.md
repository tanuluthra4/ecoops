# EcoOps heat/cold mode patch

This patch adds a selectable heat/cold screening hazard while retaining the existing forecast/historical data mode and simulation pipeline.

## Apply it

1. Make a backup or commit your current working tree.
2. Copy the files in this archive over the matching files in your repository:
   - `backend/config.py`
   - `backend/services/incident_engine.py`
   - `backend/services/response_engine.py`
   - `backend/services/incident_service.py`
   - `backend/app.py`
   - `frontend/app.js`
   - `frontend/index.html`
3. Restart FastAPI and hard-refresh the browser.

## Prototype thresholds

- Heat: at least 4 consecutive hourly readings at or above 35°C; HIGH at 8+ hours.
- Cold: at least 4 consecutive hourly readings at or below 5°C; HIGH at 8+ hours.

These are illustrative EcoOps demo settings, not official IMD criteria, health guidance, or universal definitions. Have a qualified authority validate any operational thresholds before real-world use.

## What changes

- The UI gains a Heat risk / Cold risk selector.
- Forecast and historical screening both use the selected hazard.
- Cold mode evaluates low-temperature streaks and highlights the correct side of the threshold.
- Cold response recommendations are distinct from heat recommendations.
- The resource-allocation simulation remains the existing deterministic model and does not claim to predict real-world outcomes.
- The detector retains `detect_heat_incident` as a compatibility wrapper and keeps the existing `hot_streak_hours` API/model field for backward compatibility, even in cold mode.

## Validation

This patch was syntax-checked and the detector/response logic was exercised with synthetic unit-test readings. These tests do not replace running the full app against the repository's actual dependencies and saved data.


## Automatic heat + cold screening update

The UI now requests heat and cold assessments together on every load/refresh. It automatically focuses the incident/response workflow on a qualifying risk (higher severity first, then longer streak); if neither qualifies, it focuses on the longer near-threshold streak while stating that neither risk triggered. The manual risk selector has been removed. The evidence chart plots both threshold lines at once (heat and cold), so users can see both on the same temperature graph.
