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


_EVENT_TYPES = {
    "heat": {"HEAT_EVENT", "FORECAST_HEAT_RISK"},
    "cold": {"COLD_EVENT", "FORECAST_COLD_RISK"},
}
_TEMPLATES = {"heat": HEAT_ACTIONS, "cold": COLD_ACTIONS}


def _hazard_of(incident):
    incident_type = incident.get("type")
    return incident.get("hazard") or incident.get("details", {}).get(
        "hazard", "cold" if "COLD" in str(incident_type) else "heat"
    )


def generate_response_plan(incident):
    """Generate a hazard-specific planning response for ONE detected incident."""
    incident_type = incident.get("type")
    hazard = _hazard_of(incident)

    if incident_type == "DATA_UNAVAILABLE":
        # Distinct from "no risk": the data could not be assessed at all.
        return {
            "incident_id": incident["incident_id"],
            "status": "ASSESSMENT_UNAVAILABLE",
            "hazard": hazard,
            "actions": [],
        }
    if incident_type not in _EVENT_TYPES.get(hazard, set()):
        return {
            "incident_id": incident["incident_id"],
            "status": "NO_RESPONSE_REQUIRED",
            "hazard": hazard,
            "actions": [],
        }

    actions = []
    for priority, template in enumerate(_TEMPLATES[hazard], start=1):
        action = dict(template)
        action["priority"] = priority
        action["status"] = "RECOMMENDED"
        action["kind"] = "recommendation"
        action["hazard"] = hazard
        action["incident_id"] = incident["incident_id"]
        actions.append(action)

    streak = incident.get("streak_hours", incident.get("hot_streak_hours", 0))
    forecast = str(incident_type).startswith("FORECAST_")
    return {
        "incident_id": incident["incident_id"],
        "status": "RESPONSE_RECOMMENDED",
        "hazard": hazard,
        "trigger": {
            "type": incident_type,
            "hazard": hazard,
            "basis": "forecast" if forecast else "historical observation",
            "severity": incident["severity"],
            "streak_hours": streak,
            "hot_streak_hours": streak,  # legacy field name
            "threshold": incident.get("threshold"),
        },
        "disclaimer": DISCLAIMER,
        "assumption_note": ASSUMPTION_NOTE,
        "actions": actions,
    }


def generate_combined_plan(incidents, unavailable=False):
    """Merge per-hazard plans so no qualifying incident's actions are lost.

    `incidents` should be ordered most-severe first (see rank_incidents);
    action ids (A1-A4 heat, C1-C4 cold) are unique, and priorities are
    renumbered across the merged list in that order.
    """
    plans = [generate_response_plan(i) for i in incidents]
    plans = [p for p in plans if p["status"] == "RESPONSE_RECOMMENDED"]
    if not plans:
        return {
            "incident_id": None, "incident_ids": [], "hazards": [], "plans": [],
            "status": "ASSESSMENT_UNAVAILABLE" if unavailable else "NO_RESPONSE_REQUIRED",
            "actions": [],
        }
    actions = []
    for plan in plans:
        for action in plan["actions"]:
            merged = dict(action)
            merged["priority"] = len(actions) + 1
            actions.append(merged)
    return {
        "incident_id": "+".join(p["incident_id"] for p in plans),
        "incident_ids": [p["incident_id"] for p in plans],
        "hazards": [p["hazard"] for p in plans],
        "status": "RESPONSE_RECOMMENDED",
        "plans": plans,
        "disclaimer": DISCLAIMER,
        "assumption_note": ASSUMPTION_NOTE,
        "actions": actions,
    }
