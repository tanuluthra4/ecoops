def simulate_response(response_plan, resources):
    """
    Simulate operational deployment of a response plan.

    This simulation models resource allocation only.
    It does not claim real-world environmental or health outcomes.
    """

    available_teams = resources.get("teams", 0)
    available_budget = resources.get("budget", 0)

    executed_actions = []
    blocked_actions = []

    for action in response_plan.get("actions", []):

        required_budget = 100
        required_team = 1

        if (
            available_teams >= required_team
            and available_budget >= required_budget
        ):
            available_teams -= required_team
            available_budget -= required_budget

            executed_actions.append({
                "action_id": action["action_id"],
                "name": action["name"],
                "status": "EXECUTED",
                "budget_used": required_budget,
                "team_used": required_team
            })

        else:
            blocked_actions.append({
                "action_id": action["action_id"],
                "name": action["name"],
                "status": "BLOCKED",
                "reason": "Insufficient available resources"
            })

    total_actions = len(response_plan.get("actions", []))
    executed_count = len(executed_actions)

    coverage = (
        executed_count / total_actions
        if total_actions > 0
        else 0
    )

    return {
        "status": "SIMULATION_COMPLETE",
        "resources": {
            "teams_initial": resources.get("teams", 0),
            "budget_initial": resources.get("budget", 0),
            "teams_remaining": available_teams,
            "budget_remaining": available_budget
        },
        "execution": {
            "actions_planned": total_actions,
            "actions_executed": executed_count,
            "actions_blocked": len(blocked_actions),
            "coverage": round(coverage * 100, 1)
        },
        "executed_actions": executed_actions,
        "blocked_actions": blocked_actions
    }