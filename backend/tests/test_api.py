import pytest
from fastapi.testclient import TestClient

import app as app_module
from helpers import COOL, HOT, bundle_for
from services import incident_service


def use_series(monkeypatch, values):
    monkeypatch.setattr(
        incident_service, "load_weather_bundle",
        lambda *args, **kwargs: bundle_for(values),
    )


@pytest.fixture
def client():
    return TestClient(app_module.app)


@pytest.fixture
def heat(monkeypatch):
    use_series(monkeypatch, [COOL] * 6 + [HOT] * 9 + [COOL] * 6)


def test_health(client):
    assert client.get("/health").json() == {"message": "EcoOps API Running"}


def test_root_redirects_to_ui(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/ui/"


def test_ui_is_served(client):
    response = client.get("/ui/")
    assert response.status_code == 200
    assert "EcoOps" in response.text


def test_detect_returns_incident_series_and_provenance(client, heat):
    body = client.get("/detect").json()
    assert body["type"] == "HEAT_EVENT"
    assert body["severity"] == "HIGH"
    assert body["hot_streak_hours"] == 9
    assert body["max_temp"] == 38.0
    assert body["valid_observations"] == 21
    assert len(body["details"]["series"]) == 21
    assert body["data_source"]["is_live"] is False
    assert body["data_source"]["provider"] == "NASA POWER"


def test_detect_when_data_unavailable_is_a_clean_payload(client, monkeypatch):
    monkeypatch.setattr(
        incident_service, "load_weather_bundle",
        lambda *a, **k: {"data": None, "source": {"kind": "unavailable", "note": "x"}},
    )
    response = client.get("/detect")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "DATA_UNAVAILABLE"
    assert body["data_source"]["kind"] == "unavailable"


def test_response_plan(client, heat):
    body = client.get("/response").json()
    assert body["status"] == "RESPONSE_RECOMMENDED"
    assert len(body["actions"]) == 4


def test_response_without_incident(client, monkeypatch):
    use_series(monkeypatch, [COOL] * 10)
    assert client.get("/response").json()["status"] == "NO_RESPONSE_REQUIRED"


def test_investigate_has_four_sections_and_is_labelled_deterministic(client, heat):
    body = client.get("/investigate").json()
    investigation = body["investigation"]
    assert investigation["investigation_mode"] == "deterministic_rules"
    for section in ("observed_facts", "derived_metrics",
                    "operational_assumptions", "recommended_actions"):
        assert investigation[section]
        for item in investigation[section]:
            assert item["text"] and item["basis"]
    assert investigation["checks"]
    assert "evidence_package" in body


def test_investigation_values_match_detection(client, heat):
    detect = client.get("/detect").json()
    facts = " ".join(i["text"] for i in client.get("/investigate").json()["investigation"]["observed_facts"])
    assert f"{detect['max_temp']}" in facts


def test_investigate_when_data_unavailable_does_not_crash(client, monkeypatch):
    monkeypatch.setattr(
        incident_service, "load_weather_bundle",
        lambda *a, **k: {"data": None, "source": {"kind": "unavailable"}},
    )
    body = client.get("/investigate").json()
    assert body["investigation"]["incident_found"] is False
    assert body["investigation"]["recommended_actions"] == []


def test_simulate_post(client, heat):
    response = client.post("/simulate", json={
        "teams": 2, "budget": 120, "window_hours": 6,
        "action_order": ["A1", "A2", "A3", "A4"],
    })
    assert response.status_code == 200
    body = response.json()
    assert body["simulation"]["execution"]["actions_executed"] == 3
    assert body["baseline"]["execution"]["coverage"] == 100.0
    assert body["comparison"]["missing_actions"][0]["action_id"] == "A4"


def test_simulate_get_uses_defaults(client, heat):
    assert client.get("/simulate").status_code == 200


def test_simulate_changes_with_resources(client, heat):
    low = client.post("/simulate", json={"teams": 1, "budget": 30}).json()
    high = client.post("/simulate", json={"teams": 6, "budget": 400, "window_hours": 12}).json()
    assert low["simulation"]["execution"]["actions_executed"] < high["simulation"]["execution"]["actions_executed"]


@pytest.mark.parametrize("payload", [
    {"teams": -1},
    {"teams": 2.5},
    {"teams": "many"},
    {"budget": -10},
    {"window_hours": 0},
    {"window_hours": 500},
])
def test_simulate_rejects_invalid_input(client, heat, payload):
    assert client.post("/simulate", json=payload).status_code == 422


def test_simulate_rejects_unknown_action_id(client, heat):
    response = client.post("/simulate", json={"action_order": ["A9"]})
    assert response.status_code == 422
    assert "A9" in response.json()["detail"]


def test_simulate_without_incident_is_a_conflict(client, monkeypatch):
    use_series(monkeypatch, [COOL] * 10)
    assert client.post("/simulate", json={}).status_code == 409


def test_forecast_mode_marks_risk_as_projected_and_preserves_provenance(client, monkeypatch):
    bundle = bundle_for([COOL] * 6 + [HOT] * 9 + [COOL] * 6)
    bundle["source"].update({
        "kind": "forecast", "provider": "Open-Meteo", "is_forecast": True,
        "time_standard": "IST (Asia/Kolkata)",
        "window": {"start": "2026-10-10 00:00", "end": "2026-10-10 20:00"},
    })
    monkeypatch.setattr(incident_service, "load_forecast_bundle", lambda **kwargs: bundle)
    body = client.get("/detect?mode=forecast").json()
    assert body["type"] == "FORECAST_HEAT_RISK"
    assert body["incident_id"] == "ECOOPS-FCST"
    assert body["data_source"]["is_forecast"] is True
    assert body["data_source"]["provider"] == "Open-Meteo"


def test_forecast_mode_generates_plan_and_simulation(client, monkeypatch):
    bundle = bundle_for([COOL] * 6 + [HOT] * 9 + [COOL] * 6)
    bundle["source"].update({"kind": "forecast", "provider": "Open-Meteo", "is_forecast": True})
    monkeypatch.setattr(incident_service, "load_forecast_bundle", lambda **kwargs: bundle)
    plan = client.get("/response?mode=forecast").json()
    assert plan["status"] == "RESPONSE_RECOMMENDED"
    assert plan["trigger"]["basis"] == "forecast"
    sim = client.post("/simulate?mode=forecast", json={"teams": 2, "budget": 120, "window_hours": 6}).json()
    assert sim["incident_id"] == "ECOOPS-FCST"
