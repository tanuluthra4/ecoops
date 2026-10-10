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

# EcoOps operational heat rules (prototype settings, NOT a universal
# heatwave definition).
HEAT_RULES = {
    "threshold_c": 35.0,
    "min_streak_hours": 4,    # MEDIUM and above
    "high_streak_hours": 8,   # HIGH
}

NASA_TIMEOUT_SECONDS = 25
