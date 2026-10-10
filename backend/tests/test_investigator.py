import json

from services.investigator import (
    DeterministicInvestigator,
    StrandsOllamaInvestigator,
    get_investigator,
)


def sample_context():
    return {
        "incident": {"id": "ECOOPS-042", "type": "HEAT_EVENT", "severity": "HIGH", "location": "Delhi"},
        "observed_data": {"peak_temperature_c": 38.8, "valid_observations": 72, "expected_observations": 72},
        "derived_metrics": {
            "average_temperature_c": 29.8, "hot_streak_hours": 8,
            "operational_threshold_c": 35.0,
            "rules": {"min_streak_hours": 4, "high_streak_hours": 8},
        },
        "data_source": {"time_standard": "LST"},
        "evidence": ["Historical NASA POWER hourly temperature data"],
    }


def test_deterministic_is_default(monkeypatch):
    monkeypatch.delenv("ECOOPS_INVESTIGATOR", raising=False)
    assert isinstance(get_investigator(), DeterministicInvestigator)


def test_strands_mode_can_be_selected_without_loading_sdk(monkeypatch):
    monkeypatch.setenv("ECOOPS_INVESTIGATOR", "strands_ollama")
    assert isinstance(get_investigator(), StrandsOllamaInvestigator)


def test_strands_investigator_preserves_deterministic_sections(monkeypatch):
    investigator = StrandsOllamaInvestigator()
    monkeypatch.setattr(investigator, "_generate_brief", lambda context: "Historical heat event; verify local facilities before acting.")
    result = investigator.investigate(sample_context())
    assert result["investigation_mode"] == "strands_ollama"
    assert result["agent_brief"]["text"].startswith("Historical heat event")
    assert result["observed_facts"]
    assert result["derived_metrics"]
    assert result["recommended_actions"]


def test_strands_failure_is_labelled_and_falls_back(monkeypatch):
    investigator = StrandsOllamaInvestigator()
    def fail(_context):
        raise RuntimeError("model unavailable")
    monkeypatch.setattr(investigator, "_generate_brief", fail)
    result = investigator.investigate(sample_context())
    assert result["investigation_mode"] == "deterministic_fallback"
    assert "unavailable" in result["fallback_reason"]
    assert "agent_brief" not in result
    assert result["observed_facts"]
