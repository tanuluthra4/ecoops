import pytest

from services.response_engine import generate_response_plan
from services.simulation import (
    SimulationInputError,
    baseline_requirements,
    simulate_response,
    simulate_with_baseline,
)

INCIDENT = {
    "incident_id": "T-1",
    "type": "HEAT_EVENT",
    "severity": "HIGH",
    "hot_streak_hours": 8,
    "threshold": 35.0,
}


@pytest.fixture
def plan():
    return generate_response_plan(INCIDENT)


def run(plan, teams=2, budget=120, window=6, order=None):
    resources = {"teams": teams, "budget": budget, "window_hours": window}
    if order is not None:
        resources["action_order"] = order
    return simulate_response(plan, resources)


def ids(items):
    return [item["action_id"] for item in items]


def test_no_incident_gives_empty_plan():
    plan = generate_response_plan({**INCIDENT, "type": "NO_HEAT_EVENT"})
    assert plan["status"] == "NO_RESPONSE_REQUIRED"
    assert plan["actions"] == []


def test_every_action_has_explanation_requirements_and_status(plan):
    for action in plan["actions"]:
        assert action["reason"]
        assert action["resource"]
        assert action["teams_required"] >= 1
        assert action["budget_units"] > 0
        assert action["status"] == "RECOMMENDED"
        assert action["kind"] == "recommendation"


def test_plan_labels_values_as_assumed_and_not_official(plan):
    assert "assumed" in plan["assumption_note"].lower()
    assert "not official" in plan["disclaimer"].lower()


def test_simulation_is_deterministic(plan):
    assert run(plan) == run(plan)


def test_default_scenario_executes_three_and_blocks_water_check_on_budget(plan):
    result = run(plan)
    assert ids(result["executed_actions"]) == ["A1", "A2", "A3"]
    blocked = result["blocked_actions"]
    assert ids(blocked) == ["A4"]
    assert blocked[0]["reason_code"] == "BUDGET"
    assert "50" in blocked[0]["reason"]


def test_budget_accounting(plan):
    result = run(plan)
    res = result["resources"]
    assert res["budget_used"] == 60 + 20 + 40
    assert res["budget_remaining"] == 0
    assert res["budget_used"] + res["budget_remaining"] == res["budget_initial"]


def test_zero_teams_blocks_everything(plan):
    result = run(plan, teams=0)
    assert result["executed_actions"] == []
    assert {b["reason_code"] for b in result["blocked_actions"]} == {"TEAMS"}
    assert result["execution"]["coverage"] == 0.0


def test_two_team_action_blocked_with_one_team(plan):
    result = run(plan, teams=1, budget=500, window=24)
    blocked = {b["action_id"]: b for b in result["blocked_actions"]}
    assert blocked["A4"]["reason_code"] == "TEAMS"
    assert ids(result["executed_actions"]) == ["A1", "A2", "A3"]


def test_zero_budget_blocks_everything(plan):
    result = run(plan, budget=0)
    assert result["executed_actions"] == []
    assert {b["reason_code"] for b in result["blocked_actions"]} == {"BUDGET"}


def test_time_window_blocks_actions_that_cannot_finish(plan):
    # One team, 4 hours: A1 (2h) + A2 (1h) fit, A3 (2h) would end at hour 5.
    result = run(plan, teams=1, budget=500, window=4)
    assert ids(result["executed_actions"]) == ["A1", "A2"]
    blocked = {b["action_id"]: b for b in result["blocked_actions"]}
    assert blocked["A3"]["reason_code"] == "TIME"
    assert "hour 5" in blocked["A3"]["reason"]


def test_full_resources_execute_everything(plan):
    result = run(plan, teams=4, budget=500, window=12)
    assert result["execution"]["actions_executed"] == 4
    assert result["execution"]["coverage"] == 100.0
    assert result["blocked_actions"] == []


def test_priority_order_decides_who_gets_scarce_budget(plan):
    # Budget 70 affords A4 (50) or A1 (60), but not both.
    first = run(plan, teams=4, budget=70, window=12, order=["A4", "A1", "A2"])
    assert "A4" in ids(first["executed_actions"])
    assert "A1" in [b["action_id"] for b in first["blocked_actions"]]

    second = run(plan, teams=4, budget=70, window=12, order=["A1", "A4", "A2"])
    assert "A1" in ids(second["executed_actions"])
    assert "A4" in [b["action_id"] for b in second["blocked_actions"]]


def test_unselected_actions_are_reported_not_blocked(plan):
    result = run(plan, teams=4, budget=500, window=12, order=["A1", "A2"])
    assert ids(result["not_selected_actions"]) == ["A3", "A4"]
    assert result["execution"]["actions_planned"] == 2
    assert result["execution"]["coverage"] == 100.0


def test_blocked_actions_consume_nothing_and_later_actions_still_run(plan):
    # A4 needs 2 teams; with 1 team it is blocked, then A1 still executes.
    result = run(plan, teams=1, budget=500, window=12, order=["A4", "A1"])
    assert ids(result["executed_actions"]) == ["A1"]
    assert result["executed_actions"][0]["start_hour"] == 0


def test_teams_are_reused_over_time(plan):
    result = run(plan, teams=1, budget=500, window=12, order=["A1", "A2"])
    a1, a2 = result["executed_actions"]
    assert (a1["start_hour"], a1["end_hour"]) == (0, 2)
    assert (a2["start_hour"], a2["end_hour"]) == (2, 3)


def test_team_hours_used(plan):
    result = run(plan, teams=4, budget=500, window=12)
    # A1 2h*1 + A2 1h*1 + A3 2h*1 + A4 3h*2 teams
    assert result["resources"]["team_hours_used"] == 2 + 1 + 2 + 6
    assert result["resources"]["team_hours_available"] == 48


def test_schedule_never_double_books_a_team(plan):
    result = run(plan, teams=3, budget=500, window=12)
    by_team = {}
    for entry in result["schedule"]:
        for team in entry["teams"]:
            by_team.setdefault(team, []).append((entry["start_hour"], entry["end_hour"]))
    for slots in by_team.values():
        slots.sort()
        for (_, end), (start, _) in zip(slots, slots[1:]):
            assert start >= end


@pytest.mark.parametrize("resources", [
    {"teams": -1, "budget": 10},
    {"teams": 1.5, "budget": 10},
    {"teams": "2", "budget": 10},
    {"teams": True, "budget": 10},
    {"teams": 1, "budget": -5},
    {"teams": 1, "budget": float("nan")},
    {"teams": 1, "budget": 10, "window_hours": 0},
    {"teams": 1, "budget": 10, "window_hours": -2},
    {"teams": 1, "budget": 10, "action_order": ["A9"]},
    {"teams": 1, "budget": 10, "action_order": "A1"},
])
def test_invalid_inputs_raise(plan, resources):
    with pytest.raises(SimulationInputError):
        simulate_response(plan, resources)


def test_duplicate_action_ids_are_ignored(plan):
    result = run(plan, teams=4, budget=500, window=12, order=["A1", "A1", "A2"])
    assert result["action_order"] == ["A1", "A2"]


def test_baseline_requirements_cover_the_whole_plan(plan):
    needs = baseline_requirements(plan)
    assert needs == {"teams": 5, "budget": 170, "window_hours": 3}


def test_comparison_against_full_plan(plan):
    result = simulate_with_baseline(plan, {"teams": 2, "budget": 120, "window_hours": 6})
    comparison = result["comparison"]
    assert result["baseline"]["execution"]["coverage"] == 100.0
    assert comparison["actions_executed"] == 3
    assert comparison["total_actions"] == 4
    assert comparison["coverage_of_full_plan"] == 75.0
    assert comparison["baseline_budget_required"] == 170
    assert comparison["missing_actions"][0]["action_id"] == "A4"
