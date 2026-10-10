"""Operational response planner.

Environmental measurements come only from the incident. Actions are
recommendations for planning purposes, not official emergency instructions.

Team counts, budget units and durations below are ASSUMED planning values for
this demonstration. They are not cost estimates and EcoOps holds no data about
real teams, facilities or budgets.
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

ACTION_CATALOG = [
    {
        "action_id": "A1",
        "name": "Verify cooling locations",
        "reason": "Confirm which shaded or cooled locations are actually "
                  "open and accessible before sustained heat reaches its peak.",
        "resource": "Facilities team",
        "teams_required": 1,
        "budget_units": 60,
        "duration_hours": 2,
    },
    {
        "action_id": "A2",
        "name": "Prepare heat-risk notification",
        "reason": "Draft a warning for review by a qualified authority. "
                  "EcoOps does not send it.",
        "resource": "Communications team",
        "teams_required": 1,
        "budget_units": 20,
        "duration_hours": 1,
    },
    {
        "action_id": "A3",
        "name": "Review non-essential outdoor activities",
        "reason": "Identify outdoor activities that could be moved away from "
                  "the hottest hours, or rescheduled.",
        "resource": "Operations team",
        "teams_required": 1,
        "budget_units": 40,
        "duration_hours": 2,
    },
    {
        "action_id": "A4",
        "name": "Check drinking-water access at outdoor sites",
        "reason": "Confirm that water is available where people must stay "
                  "outdoors. Needs two teams working together.",
        "resource": "Logistics team",
        "teams_required": 2,
        "budget_units": 50,
        "duration_hours": 3,
    },
]


def generate_response_plan(incident):
    """Generate an operational response plan from a detected incident."""

    if incident["type"] not in {"HEAT_EVENT", "FORECAST_HEAT_RISK"}:
        return {
            "incident_id": incident["incident_id"],
            "status": "NO_RESPONSE_REQUIRED",
            "actions": [],
        }

    actions = []
    for priority, template in enumerate(ACTION_CATALOG, start=1):
        action = dict(template)
        action["priority"] = priority
        action["status"] = "RECOMMENDED"
        action["kind"] = "recommendation"
        actions.append(action)

    return {
        "incident_id": incident["incident_id"],
        "status": "RESPONSE_RECOMMENDED",
        "trigger": {
            "type": incident["type"],
            "basis": "forecast" if incident["type"] == "FORECAST_HEAT_RISK" else "historical observation",
            "severity": incident["severity"],
            "hot_streak_hours": incident["hot_streak_hours"],
            "threshold": incident["threshold"],
        },
        "disclaimer": DISCLAIMER,
        "assumption_note": ASSUMPTION_NOTE,
        "actions": actions,
    }
