"""Operational response planner for heat and cold screening.

All actions, teams, budgets, and durations are illustrative planning
assumptions. They are not official emergency instructions or real dispatches.
"""
ASSUMPTION_NOTE = (
    "Team counts, budget units and durations are assumed planning values "
    "chosen for this demonstration. They are not cost estimates, and EcoOps "
    "has no data about real teams, facilities or budgets."
)
DISCLAIMER = (
    "Recommendations for planning purposes only, not official emergency "
    "instructions. EcoOps cannot notify people or dispatch teams."
)

HEAT_ACTIONS = [
    {
        "action_id": "A1", "name": "Verify cooling locations",
        "reason": "Confirm which shaded or cooled locations are actually open and accessible before sustained heat reaches its peak.",
        "resource": "Facilities team", "teams_required": 1, "budget_units": 60, "duration_hours": 2,
    },
    {
        "action_id": "A2", "name": "Prepare heat-risk notification",
        "reason": "Draft a heat-risk message for review by a qualified authority. EcoOps does not send it.",
        "resource": "Communications team", "teams_required": 1, "budget_units": 20, "duration_hours": 1,
    },
    {
        "action_id": "A3", "name": "Review non-essential outdoor activities",
        "reason": "Identify outdoor activities that could be moved away from the hottest hours or rescheduled.",
        "resource": "Operations team", "teams_required": 1, "budget_units": 40, "duration_hours": 2,
    },
    {
        "action_id": "A4", "name": "Check drinking-water access at outdoor sites",
        "reason": "Confirm that drinking water is available where people must stay outdoors. Needs two teams working together.",
        "resource": "Logistics team", "teams_required": 2, "budget_units": 50, "duration_hours": 3,
    },
]

COLD_ACTIONS = [
    {
        "action_id": "C1", "name": "Verify heated indoor shelter options",
        "reason": "Confirm which indoor locations are open, accessible, and suitable for people seeking warmth.",
        "resource": "Facilities team", "teams_required": 1, "budget_units": 60, "duration_hours": 2,
    },
    {
        "action_id": "C2", "name": "Prepare cold-risk notification",
        "reason": "Draft a cold-risk message for review by a qualified authority. EcoOps does not send it.",
        "resource": "Communications team", "teams_required": 1, "budget_units": 20, "duration_hours": 1,
    },
    {
        "action_id": "C3", "name": "Review prolonged outdoor work or activities",
        "reason": "Identify outdoor activities that may need timing changes, warm-up breaks, or review by the responsible authority.",
        "resource": "Operations team", "teams_required": 1, "budget_units": 40, "duration_hours": 2,
    },
    {
        "action_id": "C4", "name": "Check access to warm clothing and basic supplies",
        "reason": "Review whether relevant local services have a process for checking access to warm clothing and basic cold-weather supplies.",
        "resource": "Logistics team", "teams_required": 2, "budget_units": 50, "duration_hours": 3,
    },
]


def generate_response_plan(incident):
    """Generate a hazard-specific planning response from a detected incident."""
    incident_type = incident.get("type")
    hazard = incident.get("hazard") or incident.get("details", {}).get(
        "hazard", "cold" if "COLD" in str(incident_type) else "heat"
    )
    event_types = (
        {"HEAT_EVENT", "FORECAST_HEAT_RISK"} if hazard == "heat"
        else {"COLD_EVENT", "FORECAST_COLD_RISK"}
    )
    if incident_type not in event_types:
        return {
            "incident_id": incident["incident_id"],
            "status": "NO_RESPONSE_REQUIRED",
            "hazard": hazard,
            "actions": [],
        }

    templates = HEAT_ACTIONS if hazard == "heat" else COLD_ACTIONS
    actions = []
    for priority, template in enumerate(templates, start=1):
        action = dict(template)
        action["priority"] = priority
        action["status"] = "RECOMMENDED"
        action["kind"] = "recommendation"
        actions.append(action)

    forecast = str(incident_type).startswith("FORECAST_")
    return {
        "incident_id": incident["incident_id"],
        "status": "RESPONSE_RECOMMENDED",
        "hazard": hazard,
        "trigger": {
            "type": incident_type,
            "basis": "forecast" if forecast else "historical observation",
            "severity": incident["severity"],
            "hot_streak_hours": incident.get("hot_streak_hours", 0),
            "threshold": incident.get("threshold"),
        },
        "disclaimer": DISCLAIMER,
        "assumption_note": ASSUMPTION_NOTE,
        "actions": actions,
    }
