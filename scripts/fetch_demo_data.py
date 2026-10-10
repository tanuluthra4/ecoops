"""Download the NASA POWER demonstration window once and save it locally.

Run from the ecoops folder while online:

    python scripts/fetch_demo_data.py

This creates data/demo_incident.json, which the app then uses offline.
The file is a real NASA POWER response; nothing here is generated.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import backend.config as config # noqa: E402
from backend.services import nasa_power  # noqa: E402


def main():
    bundle = nasa_power.load_weather_bundle(refresh=True)
    source = bundle["source"]

    if bundle["data"] is None:
        print("FAILED: could not reach NASA POWER and no saved copy exists.")
        print(source["note"])
        return 1

    print(f"Source kind : {source['kind']}")
    print(f"Retrieved   : {source['retrieved_at']}")
    print(f"Saved file  : {config.DATA_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
