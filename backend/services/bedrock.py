
def investigate_with_bedrock(context):
    """Evidence-constrained local investigation for EcoOps."""

    incident = context["incident"]
    observed = context["observed_data"]
    metrics = context["derived_metrics"]

    return {
        "observed_facts": [
            f"Incident type: {incident['type']}",
            f"Location: {incident['location']}",
            f"Peak temperature: "
            f"{observed['peak_temperature_c']}°C",
            f"Average temperature: "
            f"{observed['average_temperature_c']}°C",
            f"Valid observations: "
            f"{observed['valid_observations']}"
        ],
        "derived_metrics": [
            f"Longest hot streak: "
            f"{metrics['hot_streak_hours']} hours",
            f"Operational trigger: "
            f"{metrics['operational_threshold_c']}°C"
        ],
        "operational_assumptions": [
            "Recommended actions require local verification "
            "of available facilities and response teams.",
            "The configured heat trigger is an EcoOps operational "
            "rule, not a universal heatwave classification."
        ],
        "recommended_actions": [
            "Verify cooling locations and their availability.",
            "Prepare a heat-risk notification.",
            "Review non-essential outdoor activities."
        ],
        "investigation_mode": "deterministic_local"
    }