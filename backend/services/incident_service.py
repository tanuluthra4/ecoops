"""Build an incident/risk assessment from either forecast or historical data."""

from config import DEMO_LOCATION, DEMO_WINDOW, INCIDENT_ID
from models.incident import Incident
from services.incident_engine import detect_heat_incident
from services.nasa_power import load_weather_bundle
from services.forecast import load_forecast_bundle

_TOP_LEVEL = {
    "type", "severity", "max_temp", "avg_temp", "longest_hot_streak_hours",
    "threshold", "valid_observations", "evidence",
}


def build_incident(refresh=False, mode="historical"):
    """Return (incident_dict, provenance). mode is forecast or historical."""

    if mode == "forecast":
        bundle = load_forecast_bundle(refresh=refresh)
    elif mode == "historical":
        bundle = load_weather_bundle(
            DEMO_LOCATION["lat"], DEMO_LOCATION["lon"],
            DEMO_WINDOW["start"], DEMO_WINDOW["end"], refresh=refresh,
        )
    else:
        raise ValueError("mode must be 'forecast' or 'historical'")
    detection = detect_heat_incident(bundle["data"])

    if mode == "forecast" and detection["type"] == "HEAT_EVENT":
        detection["type"] = "FORECAST_HEAT_RISK"
        detection["evidence"] = [f"Forecast risk: {item}" for item in detection["evidence"]]
    elif mode == "forecast" and detection["type"] == "NO_HEAT_EVENT":
        detection["type"] = "NO_FORECAST_RISK"

    incident = Incident(
        incident_id=("ECOOPS-FCST" if mode == "forecast" else INCIDENT_ID),
        type=detection["type"],
        severity=detection["severity"],
        location=DEMO_LOCATION["name"],
        max_temp=detection["max_temp"],
        avg_temp=detection["avg_temp"],
        hot_streak_hours=detection.get("longest_hot_streak_hours", 0),
        threshold=detection.get("threshold", 0),
        valid_observations=detection.get("valid_observations", 0),
        evidence=detection["evidence"],
        details={
            key: value for key, value in detection.items()
            if key not in _TOP_LEVEL
        },
    )
    return incident.to_dict(), bundle["source"]
