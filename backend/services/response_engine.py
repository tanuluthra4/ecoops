def generate_response_plan(incident):
    """
    Generate an operational response plan from a detected incident.

    Environmental measurements come only from the incident.
    Actions are operational recommendations, not measured outcomes.
    """

    if incident["type"] != "HEAT_EVENT":
        return {
            "incident_id": incident["incident_id"],
            "status": "NO_RESPONSE_REQUIRED",
            "actions": []
        }

    actions = [
        {
            "action_id": "A1",
            "name": "Activate cooling points",
            "reason": "Provide accessible cooling locations during sustained heat.",
            "resource": "Facilities team"
        },
        {
            "action_id": "A2",
            "name": "Issue heat-risk notification",
            "reason": "Notify people that a sustained heat event has been detected.",
            "resource": "Communications team"
        },
        {
            "action_id": "A3",
            "name": "Reduce outdoor exposure",
            "reason": "Recommend postponing non-essential outdoor activity during the event.",
            "resource": "Operations team"
        }
    ]

    return {
        "incident_id": incident["incident_id"],
        "status": "RESPONSE_RECOMMENDED",
        "trigger": {
            "type": incident["type"],
            "severity": incident["severity"],
            "hot_streak_hours": incident["hot_streak_hours"],
            "threshold": incident["threshold"]
        },
        "actions": actions
    }