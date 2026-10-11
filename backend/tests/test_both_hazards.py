"""Automatic heat + cold screening: detection, assessment, planning, simulation.

All series here are synthetic test fixtures; the app never uses them.
"""
import pytest
from fastapi.testclient import TestClient

import app as app_module
from helpers import COOL, HOT, bundle_for, make_weather
from services import incident_service
from services.incident_engine import detect_temperature_incident
from services.investigator import StrandsOllamaInvestigator, DeterministicInvestigator
from services.investigation import build_investigation_context
from services.response_engine import generate_combined_plan, generate_response_plan

COLD = 2.0


def heat(values):
    return detect_temperature_incident(make_weather(values), "heat")


def cold(values):
    return detect_temperature_incident(make_weather(values), "cold")


@pytest.fixture
def client():
    return TestClient(app_module.app)


def serve(monkeypatch, values, forecast=False):
    bundle = bundle_for(values)
    if forecast:
        bundle["source"].update(provider="Open-Meteo", is_forecast=True, kind="forecast")
        monkeypatch.setattr(incident_service, "load_forecast_bundle", lambda *a, **k: bundle)
    else:
        monkeypatch.setattr(incident_service, "load_weather_bundle", lambda *a, **k: bundle)


BOTH = [COLD] * 5 + [COOL] * 4 + [HOT] * 9          # cold 5 h (MEDIUM), heat 9 h (HIGH)
HEAT_ONLY = [COOL] * 3 + [HOT] * 4 + [COOL] * 3
COLD_ONLY = [COOL] * 3 + [COLD] * 8 + [COOL] * 3
MILD = [COOL] * 24


# ---- detection rules ----

@pytest.mark.parametrize("hours,found", [(3, False), (4, True)])
def test_heat_needs_four_consecutive_hours(hours, found):
    r = heat([COOL] * 2 + [HOT] * hours + [COOL] * 2)
    assert r["incident"] is found and r["status"] == ("RISK_DETECTED" if found else "NO_RISK")


@pytest.mark.parametrize("hours,found", [(3, False), (4, True)])
def test_cold_needs_four_consecutive_hours(hours, found):
    assert cold([COOL] * 2 + [COLD] * hours + [COOL] * 2)["incident"] is found


def test_thresholds_are_inclusive():
    assert heat([35.0] * 4)["incident"] and cold([5.0] * 4)["incident"]
    assert not heat([34.9] * 6)["incident"] and not cold([5.1] * 6)["incident"]


def test_high_severity_at_eight_hours_for_both():
    assert heat([HOT] * 7)["severity"] == "MEDIUM" and heat([HOT] * 8)["severity"] == "HIGH"
    assert cold([COLD] * 7)["severity"] == "MEDIUM" and cold([COLD] * 8)["severity"] == "HIGH"


@pytest.mark.parametrize("fn,bad", [(heat, HOT), (cold, COLD)])
def test_missing_reading_breaks_streak(fn, bad):
    r = fn([bad] * 3 + [None] + [bad] * 3)
    assert not r["incident"] and r["longest_streak_hours"] == 3


@pytest.mark.parametrize("hazard,bad", [("heat", HOT), ("cold", COLD)])
def test_time_gap_breaks_streak(hazard, bad):
    weather = make_weather([bad] * 7)
    del weather["properties"]["parameter"]["T2M"]["2025050103"]  # hour absent, not -999
    r = detect_temperature_incident(weather, hazard)
    assert not r["incident"] and r["longest_streak_hours"] == 3 and r["missing_observations"] == 1


def test_no_trigger_is_a_valid_no_risk_assessment():
    for fn in (heat, cold):
        r = fn(MILD)
        assert r["status"] == "NO_RISK" and not r["incident"]


def test_heat_and_cold_streaks_are_independent_with_times():
    h, c = heat(BOTH), cold(BOTH)
    assert (h["longest_streak_hours"], h["severity"]) == (9, "HIGH")
    assert (c["longest_streak_hours"], c["severity"]) == (5, "MEDIUM")
    assert c["min_temp"] == COLD and c["min_time"] == "2025-05-01T00:00"
    assert h["max_temp"] == HOT and h["peak_time"].startswith("2025-05-01T09")
    assert h["qualifying_streaks"][0]["start"] == "2025-05-01T09:00"


@pytest.mark.parametrize("data", [{}, None, {"properties": {}}, make_weather([None] * 5),
                                  {"properties": {"parameter": {"T2M": "bad"}}},
                                  {"properties": {"parameter": {"T2M": {"nonsense": 30}}}}])
def test_empty_or_malformed_data_is_unavailable_not_no_risk(data):
    for hazard in ("heat", "cold"):
        r = detect_temperature_incident(data, hazard)
        assert r["status"] == "UNAVAILABLE" and r["type"] == "DATA_UNAVAILABLE"


# ---- assessment endpoint, both modes ----

@pytest.mark.parametrize("values,status", [
    (HEAT_ONLY, "HEAT_ONLY"), (COLD_ONLY, "COLD_ONLY"), (BOTH, "BOTH"), (MILD, "NEITHER")])
@pytest.mark.parametrize("forecast", [False, True])
def test_assess_checks_both_hazards_in_both_modes(client, monkeypatch, values, status, forecast):
    serve(monkeypatch, values, forecast)
    body = client.get(f"/assess?mode={'forecast' if forecast else 'historical'}").json()
    assert body["status"] == status
    assert set(body["assessments"]) == {"heat", "cold"}
    assert bool(body["data_source"].get("is_forecast")) is forecast
    if status in ("HEAT_ONLY", "BOTH"):
        assert body["assessments"]["heat"]["type"] == ("FORECAST_HEAT_RISK" if forecast else "HEAT_EVENT")
    if status in ("COLD_ONLY", "BOTH"):
        assert body["assessments"]["cold"]["type"] == ("FORECAST_COLD_RISK" if forecast else "COLD_EVENT")
    if status in ("COLD_ONLY", "BOTH"):
        assert body["assessments"]["cold"]["status"] == "RISK_DETECTED"
    assert len(body["incident_ids"]) == {"HEAT_ONLY": 1, "COLD_ONLY": 1, "BOTH": 2, "NEITHER": 0}[status]


def test_status_labels_match_the_ui_vocabulary(client, monkeypatch):
    labels = {}
    for name, values in [("h", HEAT_ONLY), ("c", COLD_ONLY), ("b", BOTH), ("n", MILD)]:
        serve(monkeypatch, values)
        labels[name] = client.get("/assess").json()["status_label"]
    monkeypatch.setattr(incident_service, "load_weather_bundle",
                        lambda *a, **k: {"data": None, "source": {"kind": "unavailable"}})
    labels["u"] = client.get("/assess").json()["status_label"]
    assert labels == {"h": "Heat risk detected", "c": "Cold risk detected", "b": "Both risks detected",
                      "n": "No qualifying temperature risk", "u": "Assessment unavailable"}


def test_no_risk_and_unavailable_are_distinguishable(client, monkeypatch):
    serve(monkeypatch, MILD)
    none = client.get("/assess").json()
    monkeypatch.setattr(incident_service, "load_weather_bundle",
                        lambda *a, **k: {"data": None, "source": {"kind": "unavailable"}})
    unavailable = client.get("/assess").json()
    assert none["status"] == "NEITHER" and unavailable["status"] == "UNAVAILABLE"
    assert none["assessments"]["heat"]["status"] == "NO_RISK"
    assert unavailable["assessments"]["heat"]["status"] == "UNAVAILABLE"
    assert client.get("/response?hazard=all").json()["status"] == "ASSESSMENT_UNAVAILABLE"
    serve(monkeypatch, MILD)
    assert client.get("/response?hazard=all").json()["status"] == "NO_RESPONSE_REQUIRED"


def test_most_severe_incident_listed_first_and_none_dropped(client, monkeypatch):
    serve(monkeypatch, BOTH)
    ids = client.get("/assess").json()["incident_ids"]
    assert ids == ["ECOOPS-042", "ECOOPS-COLD-042"]


def test_repeated_requests_do_not_duplicate_incidents(client, monkeypatch):
    serve(monkeypatch, BOTH)
    first = client.get("/assess").json()
    second = client.get("/assess").json()
    assert first["incident_ids"] == second["incident_ids"]
    assert len(set(first["incident_ids"])) == 2
    plan = client.get("/response?hazard=all").json()
    ids = [a["action_id"] for a in plan["actions"]]
    assert len(ids) == len(set(ids)) == 8


def test_invalid_mode_and_hazard_are_422_not_500(client):
    assert client.get("/assess?mode=nope").status_code == 422
    assert client.get("/detect?mode=nope").status_code == 422
    assert client.get("/investigate?hazard=wind").status_code == 422
    assert client.get("/response?hazard=wind").status_code == 422


def test_legacy_detect_fields_still_present(client, monkeypatch):
    serve(monkeypatch, HEAT_ONLY)
    body = client.get("/detect").json()
    for key in ("incident_id", "type", "severity", "max_temp", "avg_temp", "hot_streak_hours",
                "threshold", "valid_observations", "evidence", "details", "data_source"):
        assert key in body


# ---- investigation ----

@pytest.mark.parametrize("hazard,words", [("heat", "cooling"), ("cold", "heated")])
def test_investigation_is_hazard_specific(client, monkeypatch, hazard, words):
    serve(monkeypatch, BOTH)
    inv = client.get(f"/investigate?hazard={hazard}").json()["investigation"]
    assert inv["hazard"] == hazard and inv["incident_found"] and inv["assessment_status"] == "RISK_DETECTED"
    assert inv["qualification"] and "consecutive" in inv["qualification"]
    text = " ".join(i["text"] for i in inv["recommended_actions"]).lower()
    assert words in text
    other = "cold" if hazard == "heat" else "heat"
    assert other not in " ".join(c["label"] for c in inv["checks"]).lower()


def test_investigation_for_unavailable_and_no_risk_differ(client, monkeypatch):
    serve(monkeypatch, MILD)
    no_risk = client.get("/investigate?hazard=cold").json()["investigation"]
    assert no_risk["assessment_status"] == "NO_RISK" and "not missing data" in no_risk["qualification"]
    monkeypatch.setattr(incident_service, "load_weather_bundle",
                        lambda *a, **k: {"data": None, "source": {"kind": "unavailable"}})
    unavailable = client.get("/investigate?hazard=cold").json()["investigation"]
    assert unavailable["assessment_status"] == "UNAVAILABLE"


# ---- planning + simulation ----

def test_planner_actions_per_risk():
    incidents = {h: incident_service._incident_from_bundle(bundle_for(BOTH), "historical", h)
                 for h in ("heat", "cold")}
    heat_plan = generate_response_plan(incidents["heat"])
    cold_plan = generate_response_plan(incidents["cold"])
    assert [a["action_id"] for a in heat_plan["actions"]] == ["A1", "A2", "A3", "A4"]
    assert [a["action_id"] for a in cold_plan["actions"]] == ["C1", "C2", "C3", "C4"]
    assert "cooling" in heat_plan["actions"][0]["name"].lower()
    assert "heated" in cold_plan["actions"][0]["name"].lower()
    assert {a["hazard"] for a in heat_plan["actions"]} == {"heat"}


def test_combined_plan_keeps_both_incidents_actions():
    incs = [incident_service._incident_from_bundle(bundle_for(BOTH), "historical", h)
            for h in ("heat", "cold")]
    plan = generate_combined_plan(incs)
    assert plan["status"] == "RESPONSE_RECOMMENDED" and len(plan["actions"]) == 8
    assert [a["priority"] for a in plan["actions"]] == list(range(1, 9))
    assert plan["incident_ids"] == ["ECOOPS-042", "ECOOPS-COLD-042"]


def test_multi_incident_flows_through_investigation_plan_and_simulation(client, monkeypatch):
    serve(monkeypatch, BOTH)
    assessment = client.get("/assess").json()
    for incident_id in assessment["incident_ids"]:
        hazard = "heat" if incident_id == "ECOOPS-042" else "cold"
        assert client.get(f"/investigate?hazard={hazard}").json()["investigation"]["incident_found"]
    plan = client.get("/response?hazard=all").json()
    assert {a["hazard"] for a in plan["actions"]} == {"heat", "cold"}
    sim = client.post("/simulate?hazard=all", json={"teams": 8, "budget": 1000, "window_hours": 12}).json()
    assert sim["incident_ids"] == ["ECOOPS-042", "ECOOPS-COLD-042"]
    executed = {a["action_id"] for a in sim["simulation"]["executed_actions"]}
    assert executed == {"A1", "A2", "A3", "A4", "C1", "C2", "C3", "C4"}
    assert sim["comparison"]["total_actions"] == 8


def test_simulation_conflict_messages_differ_for_no_risk_and_unavailable(client, monkeypatch):
    serve(monkeypatch, MILD)
    r1 = client.post("/simulate?hazard=all", json={})
    monkeypatch.setattr(incident_service, "load_weather_bundle",
                        lambda *a, **k: {"data": None, "source": {"kind": "unavailable"}})
    r2 = client.post("/simulate?hazard=all", json={})
    assert r1.status_code == r2.status_code == 409
    assert r1.json()["detail"] != r2.json()["detail"]


def test_single_hazard_simulation_still_works(client, monkeypatch):
    serve(monkeypatch, COLD_ONLY)
    body = client.post("/simulate?hazard=cold", json={"teams": 4, "budget": 300}).json()
    assert body["incident_id"] == "ECOOPS-COLD-042"


# ---- local AI (Strands/Ollama) ----

def _cold_context():
    inc = incident_service._incident_from_bundle(bundle_for(COLD_ONLY), "historical", "cold")
    return build_investigation_context(inc, {"provider": "NASA POWER", "time_standard": "LST"})


def test_unavailable_local_ai_does_not_break_workflow(monkeypatch):
    def boom(self, context):
        raise ConnectionError("ollama not running")
    monkeypatch.setattr(StrandsOllamaInvestigator, "_generate_brief", boom)
    result = StrandsOllamaInvestigator().investigate(_cold_context())
    assert result["investigation_mode"] == "deterministic_fallback"
    assert "agent_brief" not in result and result["incident_found"] and result["hazard"] == "cold"


def test_agent_brief_about_wrong_hazard_is_not_shown(monkeypatch):
    monkeypatch.setattr(StrandsOllamaInvestigator, "_generate_brief",
                        lambda self, ctx: "A severe heatwave was observed with extreme temperatures.")
    result = StrandsOllamaInvestigator().investigate(_cold_context())
    assert result["investigation_mode"] == "deterministic_fallback" and "agent_brief" not in result


def test_agent_brief_matching_hazard_is_labelled_generated(monkeypatch):
    monkeypatch.setattr(StrandsOllamaInvestigator, "_generate_brief",
                        lambda self, ctx: "Cold conditions persisted for 8 hours; confirm shelter capacity.")
    result = StrandsOllamaInvestigator().investigate(_cold_context())
    assert result["investigation_mode"] == "strands_ollama"
    assert "AI-generated" in result["agent_brief"]["basis"]
    assert result["qualification"] == DeterministicInvestigator().investigate(_cold_context())["qualification"]


def test_agent_context_receives_correct_hazard_evidence():
    ctx = _cold_context()
    assert ctx["incident"]["hazard"] == "cold" and ctx["derived_metrics"]["streak_hours"] == 8
    assert ctx["derived_metrics"]["operational_threshold_c"] == 5.0
    assert ctx["observed_data"]["lowest_temperature_c"] == COLD


# ---- configuration ----

def test_threshold_overrides_are_validated(monkeypatch):
    import importlib
    import config
    monkeypatch.setenv("ECOOPS_HEAT_THRESHOLD_C", "40")
    monkeypatch.setenv("ECOOPS_COLD_THRESHOLD_C", "banana")
    monkeypatch.setenv("ECOOPS_MIN_STREAK_HOURS", "9")   # > high (8): inconsistent -> defaults
    importlib.reload(config)
    try:
        assert config.HEAT_RULES["threshold_c"] == 40.0
        assert config.COLD_RULES["threshold_c"] == 5.0
        assert (config.HEAT_RULES["min_streak_hours"], config.HEAT_RULES["high_streak_hours"]) == (4, 8)
    finally:
        monkeypatch.undo()
        importlib.reload(config)
