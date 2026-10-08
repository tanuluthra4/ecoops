def build_investigation_context(incident):
    """
    Build the evidence package that will later be sent to Bedrock.

    Only observed and derived values from EcoOps are included.
    """

    return {
        "incident": {
            "id": incident["incident_id"],
            "type": incident["type"],
            "severity": incident["severity"],
            "location": incident["location"]
        },
        "observed_data": {
            "peak_temperature_c": incident["max_temp"],
            "average_temperature_c": incident["avg_temp"],
            "valid_observations": incident["valid_observations"]
        },
        "derived_metrics": {
            "hot_streak_hours": incident["hot_streak_hours"],
            "operational_threshold_c": incident["threshold"]
        },
        "evidence": incident["evidence"]
    }


def build_investigator_prompt(context):
    """
    Build a strict prompt for the future Bedrock investigator.
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