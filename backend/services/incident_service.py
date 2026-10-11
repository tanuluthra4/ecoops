"""Build heat and cold risk assessments from forecast or historical data.

The deterministic detector (services.incident_engine) is the single source of
truth. Data is loaded once per request and screened for BOTH hazards, so one
incident is never silently dropped when heat and cold both qualify.
"""
from config import DEMO_LOCATION, DEMO_WINDOW, HAZARDS, INCIDENT_ID
from models.incident import Incident
from services.forecast import load_forecast_bundle
from services.incident_engine import detect_temperature_incident
from services.nasa_power import load_weather_bundle

MODES = ("forecast", "historical")

_TOP_LEVEL = {
    "type", "hazard", "severity", "max_temp", "avg_temp",
    "longest_hot_streak_hours", "longest_streak_hours", "threshold",
    "valid_observations", "evidence", "status",
}
_EVENT_TYPES = {
    "heat": {"HEAT_EVENT", "FORECAST_HEAT_RISK"},
    "cold": {"COLD_EVENT", "FORECAST_COLD_RISK"},
}
_SEVERITY_RANK = {"HIGH": 2, "MEDIUM": 1}
_STATUS_LABELS = {
    "HEAT_ONLY": "Heat risk detected",
    "COLD_ONLY": "Cold risk detected",
    "BOTH": "Both risks detected",
    "NEITHER": "No qualifying temperature risk",
    "UNAVAILABLE": "Assessment unavailable",
}


def is_risk(incident):
    """True when the incident is a qualifying risk of its own hazard."""
    return incident.get("type") in _EVENT_TYPES.get(incident.get("hazard"), set())


def _check(mode, hazard):
    if hazard not in HAZARDS:
        raise ValueError("hazard must be 'heat' or 'cold'")
    if mode not in MODES:
        raise ValueError("mode must be 'forecast' or 'historical'")


def load_bundle(mode="historical", refresh=False):
    _check(mode, "heat")
    if mode == "forecast":
        return load_forecast_bundle(refresh=refresh)
    return load_weather_bundle(
        DEMO_LOCATION["lat"], DEMO_LOCATION["lon"],
        DEMO_WINDOW["start"], DEMO_WINDOW["end"], refresh=refresh,
    )


def _incident_id(mode, hazard):
    if mode == "forecast":
        return "ECOOPS-FCST" if hazard == "heat" else "ECOOPS-FCST-COLD"
    return INCIDENT_ID if hazard == "heat" else "ECOOPS-COLD-042"


def _incident_from_bundle(bundle, mode, hazard):
    if bundle.get("data") is None:
        # Empty series -> the detector reports DATA_UNAVAILABLE; no values are invented.
        data = {"properties": {"parameter": {"T2M": {}}}}
    else:
        data = bundle["data"]

    detection = detect_temperature_incident(data, hazard=hazard)
    if mode == "forecast":
        remap = {
            "HEAT_EVENT": "FORECAST_HEAT_RISK", "NO_HEAT_EVENT": "NO_FORECAST_RISK",
            "COLD_EVENT": "FORECAST_COLD_RISK", "NO_COLD_EVENT": "NO_FORECAST_COLD_RISK",
        }
        detection["type"] = remap.get(detection["type"], detection["type"])
        if detection["type"].startswith("FORECAST_"):
            detection["evidence"] = [f"Forecast risk: {item}" for item in detection["evidence"]]

    incident = Incident(
        incident_id=_incident_id(mode, hazard),
        type=detection["type"],
        severity=detection["severity"],
        location=DEMO_LOCATION["name"],
        max_temp=detection["max_temp"],
        avg_temp=detection["avg_temp"],
        hot_streak_hours=detection.get("longest_streak_hours", 0),  # legacy field name
        threshold=detection.get("threshold", 0),
        valid_observations=detection.get("valid_observations", 0),
        evidence=detection["evidence"],
        details={k: v for k, v in detection.items() if k not in _TOP_LEVEL},
    )
    payload = incident.to_dict()
    payload["hazard"] = hazard
    payload["status"] = detection["status"]
    payload["streak_hours"] = detection.get("longest_streak_hours", 0)
    return payload


def build_incident(refresh=False, mode="historical", hazard="heat"):
    """Return (incident_dict, provenance) for a single hazard (API compatible)."""
    _check(mode, hazard)
    bundle = load_bundle(mode, refresh)
    return _incident_from_bundle(bundle, mode, hazard), bundle["source"]


def rank_incidents(incidents):
    """Qualifying incidents, most severe first, then longest streak, then heat before cold."""
    risks = [i for i in incidents if is_risk(i)]
    return sorted(risks, key=lambda i: (
        -_SEVERITY_RANK.get(i["severity"], 0), -i["streak_hours"], HAZARDS.index(i["hazard"])))


def overall_status(assessments):
    """Normalise both assessments into one of HEAT_ONLY/COLD_ONLY/BOTH/NEITHER/UNAVAILABLE."""
    if any(a["status"] == "UNAVAILABLE" for a in assessments.values()):
        return "UNAVAILABLE"
    heat, cold = is_risk(assessments["heat"]), is_risk(assessments["cold"])
    if heat and cold:
        return "BOTH"
    return "HEAT_ONLY" if heat else "COLD_ONLY" if cold else "NEITHER"


def build_assessment(refresh=False, mode="historical", bundle=None):
    """Screen the same data for heat AND cold. Returns both, never just one."""
    _check(mode, "heat")
    bundle = bundle or load_bundle(mode, refresh)
    assessments = {h: _incident_from_bundle(bundle, mode, h) for h in HAZARDS}
    status = overall_status(assessments)
    return {
        "mode": mode,
        "status": status,
        "status_label": _STATUS_LABELS[status],
        "assessments": assessments,
        "incident_ids": [i["incident_id"] for i in rank_incidents(assessments.values())],
        "data_source": bundle["source"],
    }
