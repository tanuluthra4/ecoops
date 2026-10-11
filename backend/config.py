"""Central configuration for EcoOps.

Everything here is an operational setting chosen for the demonstration,
not a scientific constant.
"""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"

# Saved copy of the NASA POWER response used for offline demos.
# Override with the ECOOPS_DATA_FILE environment variable (used by tests).
DATA_FILE = Path(
    os.environ.get("ECOOPS_DATA_FILE", ROOT_DIR / "data" / "demo_incident.json")
)

INCIDENT_ID = "ECOOPS-042"

# Demonstration location and historical window (unchanged from the prototype).
DEMO_LOCATION = {"name": "Delhi", "lat": 28.6139, "lon": 77.2090}
DEMO_WINDOW = {"start": "20250501", "end": "20250503"}

# EcoOps operational heat/cold rules. These are prototype settings, NOT
# official weather warnings (e.g. IMD) or universal meteorological/medical
# definitions. Override them for a demo with the optional environment
# variables below; invalid values fall back to the defaults.
def _env_number(name, default, cast=float, minimum=None):
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = cast(raw)
    except (TypeError, ValueError):
        return default
    if value != value or (minimum is not None and value < minimum):  # NaN / too small
        return default
    return value


_MIN_STREAK = _env_number("ECOOPS_MIN_STREAK_HOURS", 4, int, 1)
_HIGH_STREAK = _env_number("ECOOPS_HIGH_STREAK_HOURS", 8, int, 1)
if _HIGH_STREAK < _MIN_STREAK:  # inconsistent override: use the defaults
    _MIN_STREAK, _HIGH_STREAK = 4, 8

HEAT_RULES = {
    "hazard": "heat",
    "threshold_c": _env_number("ECOOPS_HEAT_THRESHOLD_C", 35.0),
    "comparison": "gte",
    "min_streak_hours": _MIN_STREAK,    # MEDIUM and above
    "high_streak_hours": _HIGH_STREAK,  # HIGH
}
COLD_RULES = {
    "hazard": "cold",
    "threshold_c": _env_number("ECOOPS_COLD_THRESHOLD_C", 5.0),
    "comparison": "lte",
    "min_streak_hours": _MIN_STREAK,    # MEDIUM and above
    "high_streak_hours": _HIGH_STREAK,  # HIGH
}
HAZARDS = ("heat", "cold")
RULES_BY_HAZARD = {"heat": HEAT_RULES, "cold": COLD_RULES}

NASA_TIMEOUT_SECONDS = 25
