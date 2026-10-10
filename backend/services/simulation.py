"""Deterministic simulation of operational resource allocation.

MODEL
  * Actions are handled in priority order (the order the user chose).
  * An action needs `teams_required` teams at the same time for
    `duration_hours`. Teams are reusable: when a team finishes one action it
    can start the next, within the response window.
  * An action runs only if teams, budget and time all allow it; otherwise it
    is BLOCKED with the specific reason. Blocked actions never consume
    resources, and later actions are still considered.

This models resource allocation only. It does not predict temperature
changes, health outcomes or lives affected.
"""

import math

DEFAULT_WINDOW_HOURS = 6.0

MODEL_DESCRIPTION = (
    "Greedy allocation in priority order. Each action needs its required "
    "teams simultaneously for its duration; teams are reused over the "
    "response window."
)
DISCLAIMER = (
    "Simulates operational resource allocation only. It does not predict "
    "temperature reduction, health outcomes or real-world effectiveness."
)


class SimulationInputError(ValueError):
    """Raised when simulation inputs are invalid."""


def _fmt(number):
    return f"{number:g}"


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _validate(resources, plan_actions):
    teams = resources.get("teams", 0)
    budget = resources.get("budget", 0)
    window = resources.get("window_hours", DEFAULT_WINDOW_HOURS)

    if isinstance(teams, float) and teams.is_integer():
        teams = int(teams)
    if isinstance(teams, bool) or not isinstance(teams, int) or teams < 0:
        raise SimulationInputError("teams must be a whole number, 0 or more")
    if teams > 1000:
        raise SimulationInputError("teams must be at most 1000")
    if not _is_number(budget) or budget < 0:
        raise SimulationInputError("budget must be a number, 0 or more")
    if not _is_number(window) or window <= 0:
        raise SimulationInputError("window_hours must be a number above 0")

    known = {action["action_id"] for action in plan_actions}
    order = resources.get("action_order")
    if order is None:
        order = [
            action["action_id"]
            for action in sorted(plan_actions, key=lambda a: a["priority"])
        ]
    else:
        if not isinstance(order, list):
            raise SimulationInputError("action_order must be a list")
        unknown = [item for item in order if item not in known]
        if unknown:
            raise SimulationInputError(f"unknown action ids: {', '.join(map(str, unknown))}")
        seen = set()
        order = [item for item in order if not (item in seen or seen.add(item))]

    return teams, float(budget), float(window), order


def simulate_response(response_plan, resources):
    """Simulate operational deployment of a response plan."""

    plan_actions = response_plan.get("actions", [])
    teams, budget, window, order = _validate(resources, plan_actions)
    by_id = {action["action_id"]: action for action in plan_actions}

    team_free_at = [0.0] * teams
    budget_left = budget
    executed = []
    blocked = []
    schedule = []

    for action_id in order:
        action = by_id[action_id]
        needed_teams = action["teams_required"]
        cost = action["budget_units"]
        duration = action["duration_hours"]

        reason_code = None
        reason = None
        start = end = None

        if needed_teams > teams:
            reason_code = "TEAMS"
            reason = (
                f"Needs {needed_teams} teams at once; only {teams} available."
            )
        elif cost > budget_left:
            reason_code = "BUDGET"
            reason = (
                f"Needs {_fmt(cost)} budget units; "
                f"{_fmt(budget_left)} remaining."
            )
        else:
            chosen = sorted(range(teams), key=lambda i: (team_free_at[i], i))[:needed_teams]
            start = max(team_free_at[i] for i in chosen)
            end = start + duration
            if end > window + 1e-9:
                reason_code = "TIME"
                reason = (
                    f"Would finish at hour {_fmt(end)}, after the "
                    f"{_fmt(window)}-hour response window."
                )

        if reason_code:
            blocked.append({
                "action_id": action_id,
                "name": action["name"],
                "status": "BLOCKED",
                "reason_code": reason_code,
                "reason": reason,
            })
            continue

        for index in chosen:
            team_free_at[index] = end
        budget_left -= cost
        executed.append({
            "action_id": action_id,
            "name": action["name"],
            "status": "EXECUTED",
            "budget_used": cost,
            "team_used": needed_teams,
            "start_hour": start,
            "end_hour": end,
        })
        schedule.append({
            "action_id": action_id,
            "name": action["name"],
            "teams": sorted(chosen),
            "start_hour": start,
            "end_hour": end,
        })

    not_selected = [
        {"action_id": a["action_id"], "name": a["name"], "status": "NOT_SELECTED"}
        for a in plan_actions
        if a["action_id"] not in order
    ]

    planned = len(order)
    executed_count = len(executed)
    budget_used = budget - budget_left
    team_hours_used = sum(item["team_used"] * (item["end_hour"] - item["start_hour"]) for item in executed)

    return {
        "status": "SIMULATION_COMPLETE",
        "model": {
            "type": "operational resource allocation",
            "description": MODEL_DESCRIPTION,
            "disclaimer": DISCLAIMER,
        },
        "resources": {
            "teams_initial": teams,
            "budget_initial": budget,
            "budget_used": budget_used,
            "budget_remaining": budget_left,
            "window_hours": window,
            "team_hours_available": teams * window,
            "team_hours_used": team_hours_used,
        },
        "execution": {
            "actions_planned": planned,
            "actions_executed": executed_count,
            "actions_blocked": len(blocked),
            "actions_not_selected": len(not_selected),
            "coverage": round(100 * executed_count / planned, 1) if planned else 0.0,
            "completion_hour": max((item["end_hour"] for item in executed), default=0.0),
        },
        "action_order": order,
        "executed_actions": executed,
        "blocked_actions": blocked,
        "not_selected_actions": not_selected,
        "schedule": schedule,
    }


def baseline_requirements(response_plan):
    """Resources needed to run the FULL plan with every action in parallel."""
    actions = response_plan.get("actions", [])
    return {
        "teams": sum(a["teams_required"] for a in actions),
        "budget": sum(a["budget_units"] for a in actions),
        "window_hours": max((a["duration_hours"] for a in actions), default=0),
    }


def simulate_with_baseline(response_plan, resources):
    """Run the requested allocation and compare it with the full plan."""

    simulation = simulate_response(response_plan, resources)
    needs = baseline_requirements(response_plan)
    baseline = simulate_response(response_plan, {
        "teams": needs["teams"],
        "budget": needs["budget"],
        "window_hours": max(needs["window_hours"], 1),
    })

    sim_exec = simulation["execution"]
    base_exec = baseline["execution"]
    total_actions = len(response_plan.get("actions", []))

    missing = [
        {"action_id": item["action_id"], "name": item["name"], "reason": item["reason"]}
        for item in simulation["blocked_actions"]
    ] + [
        {"action_id": item["action_id"], "name": item["name"], "reason": "Not selected"}
        for item in simulation["not_selected_actions"]
    ]

    comparison = {
        "total_actions": total_actions,
        "actions_executed": sim_exec["actions_executed"],
        "baseline_actions_executed": base_exec["actions_executed"],
        "coverage_of_full_plan": round(100 * sim_exec["actions_executed"] / total_actions, 1) if total_actions else 0.0,
        "budget_used": simulation["resources"]["budget_used"],
        "baseline_budget_required": needs["budget"],
        "teams_available": simulation["resources"]["teams_initial"],
        "baseline_teams_required": needs["teams"],
        "completion_hour": sim_exec["completion_hour"],
        "baseline_completion_hour": base_exec["completion_hour"],
        "missing_actions": missing,
    }

    return {"simulation": simulation, "baseline": baseline, "comparison": comparison}
