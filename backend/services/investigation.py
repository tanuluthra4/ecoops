def build_investigation_context(incident, data_source=None):
    """
    Build the evidence package handed to an investigator.

    Only observed and derived values from EcoOps are included. The same
    package can later be given to an LLM-based investigator.
    """

    details = incident.get("details", {})

    return {
        "incident": {
            "id": incident["incident_id"],
            "type": incident["type"],
            "severity": incident["severity"],
            "location": incident["location"]
        },
        "observed_data": {
            "peak_temperature_c": incident["max_temp"],
            "peak_time": details.get("peak_time"),
            "lowest_temperature_c": details.get("min_temp"),
            "valid_observations": incident["valid_observations"],
            "expected_observations": details.get("expected_observations"),
            "missing_observations": details.get("missing_observations"),
            "observation_start": details.get("observation_start"),
            "observation_end": details.get("observation_end")
        },
        "derived_metrics": {
            "average_temperature_c": incident["avg_temp"],
            "hot_streak_hours": incident["hot_streak_hours"],
            "hot_streak_start": details.get("longest_streak_start"),
            "hot_streak_end": details.get("longest_streak_end"),
            "hours_at_or_above_threshold": details.get("hours_at_or_above_threshold"),
            "qualifying_streaks": details.get("qualifying_streaks", []),
            "operational_threshold_c": incident["threshold"],
            "rules": details.get("rules", {})
        },
        "data_source": data_source or {},
        "evidence": incident["evidence"]
    }


def build_investigator_prompt(context):
    """
    Build a strict prompt for a future LLM-based investigator
    (for example an AWS Strands agent). Not used by the deterministic
    investigator.
    """

    return f"""
You are EcoOps Incident Investigator.

Analyze ONLY the evidence supplied below.

Separate your analysis into:

1. Observed facts
2. Derived metrics
3. Operational assumptions
4. Recommended actions

Rules:
- Never invent environmental measurements.
- Never present assumptions as observed facts.
- Do not claim health or environmental outcomes without evidence.
- Every factual environmental claim must be supported by the supplied evidence.
- Keep recommendations operational and actionable.

Evidence package:

{context}
"""
