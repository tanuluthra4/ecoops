"""Build a risk assessment from forecast or historical temperature data."""
from config import DEMO_LOCATION, DEMO_WINDOW, INCIDENT_ID
from models.incident import Incident
from services.incident_engine import detect_temperature_incident
from services.nasa_power import load_weather_bundle
from services.forecast import load_forecast_bundle

_TOP_LEVEL = {
    "type", "hazard", "severity", "max_temp", "avg_temp",
    "longest_hot_streak_hours", "longest_streak_hours", "threshold",
    "valid_observations", "evidence",
}


def build_incident(refresh=False, mode="historical", hazard="heat"):
    """Return (incident_dict, provenance). mode=forecast|historical; hazard=heat|cold."""
    if hazard not in {"heat", "cold"}:
        raise ValueError("hazard must be 'heat' or 'cold'")

    if mode == "forecast":
        bundle = load_forecast_bundle(refresh=refresh)
    elif mode == "historical":
        bundle = load_weather_bundle(
            DEMO_LOCATION["lat"], DEMO_LOCATION["lon"],
            DEMO_WINDOW["start"], DEMO_WINDOW["end"], refresh=refresh,
        )
    else:
        raise ValueError("mode must be 'forecast' or 'historical'")

    if bundle.get("data") is None:
        # Feed the detector an empty series so the API returns a standard
        # DATA_UNAVAILABLE result without fabricating any temperature values.
        data = {"properties": {"parameter": {"T2M": {}}}}
    else:
        data = bundle["data"]

    detection = detect_temperature_incident(data, hazard=hazard)
    if mode == "forecast":
        if detection["type"] == "HEAT_EVENT":
            detection["type"] = "FORECAST_HEAT_RISK"
        elif detection["type"] == "NO_HEAT_EVENT":
            detection["type"] = "NO_FORECAST_RISK"
        elif detection["type"] == "COLD_EVENT":
            detection["type"] = "FORECAST_COLD_RISK"
        elif detection["type"] == "NO_COLD_EVENT":
            detection["type"] = "NO_FORECAST_COLD_RISK"
        if detection["type"].startswith("FORECAST_"):
            detection["evidence"] = [f"Forecast risk: {item}" for item in detection["evidence"]]

    incident_id = (
        "ECOOPS-FCST" if mode == "forecast" and hazard == "heat"
        else "ECOOPS-FCST-COLD" if mode == "forecast"
        else INCIDENT_ID if hazard == "heat"
        else "ECOOPS-COLD-042"
    )
    incident = Incident(
        incident_id=incident_id,
        type=detection["type"],
        severity=detection["severity"],
        location=DEMO_LOCATION["name"],
        max_temp=detection["max_temp"],
        avg_temp=detection["avg_temp"],
        hot_streak_hours=detection.get("longest_streak_hours", 0),
        threshold=detection.get("threshold", 0),
        valid_observations=detection.get("valid_observations", 0),
        evidence=detection["evidence"],
        details={
            key: value for key, value in detection.items()
            if key not in _TOP_LEVEL
        },
    )
    incident_payload = incident.to_dict()
    incident_payload["hazard"] = hazard
    return incident_payload, bundle["source"]
