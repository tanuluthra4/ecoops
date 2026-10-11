"""Investigators turn an evidence package into a structured investigation.

The interface is deliberately small so a different implementation (for
example an AWS Strands agent) can replace the deterministic one later without
touching routes or the frontend:

    investigator.investigate(context: dict) -> dict

One investigation covers ONE incident (heat or cold); callers investigate each
qualifying incident separately.

Output sections: observed_facts, derived_metrics, operational_assumptions,
recommended_actions, plus `checks` (the steps that were run).
Each item is {"text": str, "basis": str}.

DeterministicInvestigator is plain rule-based code. It is NOT an AI agent and
is reported as such via investigation_mode.
"""

import json
import os
from typing import Protocol


class Investigator(Protocol):
    mode: str

    def investigate(self, context: dict) -> dict:
        ...


def _item(text, basis):
    return {"text": text, "basis": basis}


def _num(value, unit=""):
    if value is None:
        return "n/a"
    if isinstance(value, str):
        value = value.replace("T", " ")  # 2025-05-03T13:00 -> 2025-05-03 13:00
    return f"{value}{unit}"


_HAZARD_TEXT = {
    "heat": {
        "event_types": {"HEAT_EVENT", "FORECAST_HEAT_RISK"},
        "adjective": "hot", "relation": "at or above", "compare": ">=",
        "extreme_word": "Peak", "extreme_key": "peak_temperature_c", "extreme_time": "peak_time",
        "label": "heat",
        "recommended": [
            "Verify cooling locations and their availability.",
            "Prepare a heat-risk notification for review by a qualified authority.",
            "Review non-essential outdoor activities and consider rescheduling.",
            "Check drinking-water access at sites where people must stay outdoors.",
        ],
        "definition": "heatwave",
    },
    "cold": {
        "event_types": {"COLD_EVENT", "FORECAST_COLD_RISK"},
        "adjective": "cold", "relation": "at or below", "compare": "<=",
        "extreme_word": "Lowest", "extreme_key": "lowest_temperature_c", "extreme_time": "lowest_time",
        "label": "cold",
        "recommended": [
            "Verify heated indoor shelter options and their availability.",
            "Prepare a cold-risk notification for review by a qualified authority.",
            "Review prolonged outdoor work or activities and consider timing changes.",
            "Check access to warm clothing and basic cold-weather supplies.",
        ],
        "definition": "cold-wave",
    },
}


class DeterministicInvestigator:
    """Rule-based, hazard-aware investigation of ONE incident (heat or cold)."""

    mode = "deterministic_rules"

    def investigate(self, context):
        incident = context["incident"]
        observed = context["observed_data"]
        metrics = context["derived_metrics"]
        source = context.get("data_source", {})
        rules = metrics.get("rules", {})

        hazard = incident.get("hazard") or metrics.get("hazard") or "heat"
        h = _HAZARD_TEXT.get(hazard, _HAZARD_TEXT["heat"])
        threshold = metrics["operational_threshold_c"]
        min_streak = rules.get("min_streak_hours")
        high_streak = rules.get("high_streak_hours")
        streak = metrics.get("streak_hours", metrics.get("hot_streak_hours", 0))
        streak_start = metrics.get("streak_start", metrics.get("hot_streak_start"))
        streak_end = metrics.get("streak_end", metrics.get("hot_streak_end"))
        beyond = metrics.get("hours_beyond_threshold", metrics.get("hours_at_or_above_threshold"))
        time_standard = source.get("time_standard", "data time")
        is_forecast = bool(source.get("is_forecast"))
        provider = source.get("provider", "data provider")
        temperature_word = "forecast temperature" if is_forecast else "temperature reading"
        basis_label = f"{provider} hourly forecast" if is_forecast else f"{provider} historical temperature data"
        found = incident["type"] in h["event_types"]

        base = {
            "investigation_mode": self.mode,
            "hazard": hazard,
            "incident_id": incident.get("id"),
            "risk_basis": "forecast" if is_forecast else "historical",
        }

        if incident["type"] == "DATA_UNAVAILABLE":
            return {
                **base,
                "incident_found": False,
                "assessment_status": "UNAVAILABLE",
                "checks": [{
                    "label": "Load hourly temperature data",
                    "result": "No valid temperature data available, so this risk could not be assessed.",
                }],
                "observed_facts": [],
                "derived_metrics": [],
                "operational_assumptions": [
                    _item("No conclusion can be drawn without observations. This is not a 'no risk' result.",
                          "assumption"),
                ],
                "recommended_actions": [],
                "qualification": None,
            }

        checks = [
            {
                "label": "Load hourly forecast values" if is_forecast else "Load hourly temperature observations",
                "result": f"{observed['valid_observations']} valid of "
                          f"{_num(observed.get('expected_observations'))} expected hourly readings "
                          f"({_num(observed.get('missing_observations'))} missing).",
            },
            {
                "label": "Exclude invalid readings",
                "result": f"Sentinel (-999) and non-numeric values removed. "
                          f"Each excluded or missing hour breaks a {h['adjective']} streak.",
            },
            {
                "label": f"Compare every hour with the {threshold:g}°C {h['label']} trigger",
                "result": f"{_num(beyond)} hours {h['relation']} the trigger.",
            },
            {
                "label": f"Find the longest consecutive {h['adjective']} run",
                "result": f"{streak} hours"
                          + (f", {_num(streak_start)} to {_num(streak_end)}." if streak_start else "."),
            },
            {
                "label": "Apply the severity rule",
                "result": f"Longest run {streak} h against the {_num(min_streak)} h minimum "
                          f"and HIGH at {_num(high_streak)} h gives {incident['severity']}.",
            },
        ]

        observed_facts = [
            _item(f"{h['extreme_word']} {temperature_word}: {_num(observed.get(h['extreme_key']), ' °C')} at "
                  f"{_num(observed.get(h['extreme_time']))} ({time_standard}).", basis_label),
            _item(f"Valid hourly {'forecast values' if is_forecast else 'readings'}: {observed['valid_observations']} of "
                  f"{_num(observed.get('expected_observations'))}.",
                  f"count of {provider} hourly values"),
            _item(f"{'Forecast' if is_forecast else 'Observation'} window: {_num(observed.get('observation_start'))} to "
                  f"{_num(observed.get('observation_end'))} ({time_standard}).",
                  f"{provider} timestamps"),
        ]

        derived = [
            _item(f"Average temperature: {_num(metrics['average_temperature_c'], ' °C')}.",
                  "calculation: mean of valid readings"),
            _item(f"Hours {h['relation']} {threshold:g} °C: {_num(beyond)}.",
                  f"calculation: count of readings {h['compare']} trigger"),
            _item(f"Longest consecutive run {h['relation']} {threshold:g} °C: {streak} hours.",
                  "calculation: longest unbroken run"),
            _item(f"Severity: {incident['severity']}.",
                  f"rule: MEDIUM at {_num(min_streak)} h, HIGH at {_num(high_streak)} h"),
        ]

        assumptions = [
            _item("This is a forecast-based screening signal, not an observed incident or official warning. Forecasts can change."
                  if is_forecast else "This is a historical demonstration window, not a live incident.",
                  "forecast limitation" if is_forecast else "assumption"),
            _item(f"The {threshold:g} °C trigger and the {_num(min_streak)} h / "
                  f"{_num(high_streak)} h severity rules are EcoOps demo settings, not an official "
                  f"or universal {h['definition']} definition.", "assumption"),
            _item("Open-Meteo values are weather-model forecasts, not future certainties or local sensor readings."
                  if is_forecast else
                  "NASA POWER hourly values are gridded, model-based estimates for the given coordinates, not a single weather-station reading.",
                  "forecast limitation" if is_forecast else "assumption"),
            _item("Humidity, wind, exposed population and local facilities are not used, "
                  "so exposure and health risk are not assessed.", "limitation"),
            _item("Recommended actions need local verification of facilities and teams.", "assumption"),
        ]

        qualification = None
        if found:
            intervals = (metrics.get("qualifying_streaks") or [])
            qualification = (
                f"{streak} consecutive hourly values {h['relation']} {threshold:g} °C "
                f"({_num(streak_start)} to {_num(streak_end)}) meet the {_num(min_streak)} h minimum; "
                f"severity {incident['severity']} (HIGH needs {_num(high_streak)} h)."
                + (f" {len(intervals)} qualifying interval(s) in total." if intervals else "")
            )
        else:
            qualification = (
                f"The longest run {h['relation']} {threshold:g} °C was {streak} h, "
                f"below the {_num(min_streak)} h minimum, so no {h['label']} risk was triggered. "
                "This is a valid assessment of the data, not missing data."
            )

        return {
            **base,
            "incident_found": found,
            "assessment_status": "RISK_DETECTED" if found else "NO_RISK",
            "qualification": qualification,
            "checks": checks,
            "observed_facts": observed_facts,
            "derived_metrics": derived,
            "operational_assumptions": assumptions,
            "recommended_actions": [_item(t, "recommendation") for t in h["recommended"]] if found else [],
        }


class StrandsOllamaInvestigator:
    """Optional Strands Agents SDK investigator backed by a local Ollama model.

    The deterministic investigation remains the source of truth for measured and
    calculated facts. Strands adds only a short, clearly labelled operational
    brief. If the SDK, local model, or Ollama server is unavailable, the app
    returns the deterministic investigation and labels the fallback honestly.
    """

    mode = "strands_ollama"

    def __init__(self):
        self.model_id = os.getenv("ECOOPS_OLLAMA_MODEL", "qwen2.5:1.5b")
        self.host = os.getenv("ECOOPS_OLLAMA_HOST", "http://localhost:11434")
        self.rules_investigator = DeterministicInvestigator()

    def _generate_brief(self, context):
        # Import lazily so ordinary tests and deterministic mode do not require
        # the optional SDK to be importable at module load time.
        from strands import Agent
        from strands.models.ollama import OllamaModel

        model = OllamaModel(host=self.host, model_id=self.model_id)
        agent = Agent(
            model=model,
            system_prompt=(
                "You are EcoOps' environmental incident operations assistant. "
                "The evidence package covers ONE hazard (see incident.hazard: heat or cold); "
                "write only about that hazard. The deterministic detector is the source of "
                "truth: never contradict its hazard, severity, streak or times. "
                "Use only the supplied evidence package. Never invent readings, "
                "times, populations, casualties, health outcomes, or impacts. "
                "Clearly distinguish forecast model output from observed data; "
                "never call a forecast an observed event or official warning. "
                "Do not claim historical demonstrations are live. Distinguish "
                "observations from assumptions. Do not issue medical advice or "
                "claim actions have been executed. Write a concise operational "
                "brief of 2-4 sentences, including one important limitation."
            ),
        )
        prompt = (
            "Create a concise operational brief from this JSON evidence package. "
            "If data is unavailable, say that no conclusion can be drawn.\n\n"
            + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        )
        return str(agent(prompt)).strip()

    def investigate(self, context):
        # Keep every evidence-labelled fact and rule-based check deterministic.
        result = self.rules_investigator.investigate(context)
        if not result.get("incident_found"):
            result["investigation_mode"] = "deterministic_rules"
            return result

        try:
            brief = self._generate_brief(context)
            if not brief:
                raise ValueError("The local agent returned an empty brief")
            hazard = result.get("hazard", "heat")
            if hazard not in brief.lower():
                # Commentary that never names the detected hazard disagrees with
                # the detector; do not present it.
                raise ValueError("The local agent brief did not match the detected hazard")
            result["investigation_mode"] = self.mode
            result["agent_brief"] = {
                "text": brief,
                "basis": f"Strands Agents SDK + local Ollama model ({self.model_id}); AI-generated and requires human review.",
            }
        except Exception:
            # Keep the main workflow usable and never imply the agent ran when it did not.
            result["investigation_mode"] = "deterministic_fallback"
            result["fallback_reason"] = (
                "Strands/Ollama was unavailable; the evidence checks and sections "
                "below were produced by deterministic rules."
            )
        return result


def get_investigator():
    """Select the investigator via ECOOPS_INVESTIGATOR (deterministic by default)."""
    mode = os.getenv("ECOOPS_INVESTIGATOR", "deterministic").strip().lower()
    if mode in {"strands", "strands_ollama", "ollama"}:
        return StrandsOllamaInvestigator()
    return DeterministicInvestigator()
