import pytest

from helpers import COOL, HOT, make_weather
from services.incident_engine import detect_heat_incident


def detect(values):
    return detect_heat_incident(make_weather(values))


def test_three_hot_hours_is_not_an_incident():
    result = detect([COOL, HOT, HOT, HOT, COOL])
    assert result["incident"] is False
    assert result["type"] == "NO_HEAT_EVENT"
    assert result["severity"] == "LOW"
    assert result["longest_hot_streak_hours"] == 3


def test_four_consecutive_hours_is_medium():
    result = detect([COOL, HOT, HOT, HOT, HOT, COOL])
    assert result["incident"] is True
    assert result["type"] == "HEAT_EVENT"
    assert result["severity"] == "MEDIUM"
    assert result["longest_hot_streak_hours"] == 4


def test_seven_is_medium_and_eight_is_high():
    assert detect([HOT] * 7)["severity"] == "MEDIUM"
    assert detect([HOT] * 8)["severity"] == "HIGH"


def test_threshold_is_inclusive():
    result = detect([35.0] * 4)
    assert result["incident"] is True


def test_just_below_threshold_does_not_count():
    result = detect([34.9] * 10)
    assert result["incident"] is False
    assert result["longest_hot_streak_hours"] == 0


def test_streak_resets_after_a_cool_hour():
    result = detect([HOT, HOT, HOT, COOL, HOT, HOT, HOT])
    assert result["longest_hot_streak_hours"] == 3
    assert result["incident"] is False


def test_missing_hour_breaks_a_streak():
    # Regression: removing -999 values used to glue these into a 4-hour run.
    result = detect([HOT, HOT, None, HOT, HOT])
    assert result["longest_hot_streak_hours"] == 2
    assert result["incident"] is False
    assert result["missing_observations"] == 1
    assert result["valid_observations"] == 4


def test_missing_hours_are_excluded_from_statistics():
    result = detect([30.0, None, 40.0])
    assert result["avg_temp"] == 35.0
    assert result["max_temp"] == 40.0
    assert result["min_temp"] == 30.0


def test_timestamp_gap_in_payload_breaks_a_streak():
    weather = make_weather([HOT, HOT, HOT, HOT])
    series = weather["properties"]["parameter"]["T2M"]
    del series["2025050102"]  # hour absent from the payload entirely
    result = detect_heat_incident(weather)
    assert result["longest_hot_streak_hours"] == 2
    assert result["expected_observations"] == 4
    assert result["valid_observations"] == 3


def test_all_missing_is_data_unavailable():
    result = detect([None, None, None])
    assert result["type"] == "DATA_UNAVAILABLE"
    assert result["severity"] == "UNKNOWN"
    assert result["incident"] is False
    assert result["max_temp"] is None
    assert result["series"] == []


@pytest.mark.parametrize("payload", [
    None,
    {},
    {"properties": {}},
    {"properties": {"parameter": {}}},
    {"properties": {"parameter": {"T2M": None}}},
    {"properties": {"parameter": {"T2M": {}}}},
    {"properties": {"parameter": {"T2M": {"not-a-timestamp": 40}}}},
])
def test_malformed_payloads_do_not_crash(payload):
    result = detect_heat_incident(payload)
    assert result["type"] == "DATA_UNAVAILABLE"


def test_non_numeric_values_are_treated_as_missing():
    weather = make_weather([HOT, HOT, HOT, HOT])
    weather["properties"]["parameter"]["T2M"]["2025050101"] = "hot"
    weather["properties"]["parameter"]["T2M"]["2025050102"] = None
    result = detect_heat_incident(weather)
    assert result["valid_observations"] == 2
    assert result["incident"] is False


def test_metrics_are_computed_from_the_data():
    values = [30.0] * 4 + [36.0, 37.0, 38.0, 39.0] + [30.0] * 4
    result = detect(values)
    assert result["max_temp"] == 39.0
    assert result["peak_time"] == "2025-05-01T07:00"
    assert result["longest_streak_start"] == "2025-05-01T04:00"
    assert result["longest_streak_end"] == "2025-05-01T07:00"
    assert result["hours_at_or_above_threshold"] == 4
    assert result["valid_observations"] == 12
    assert len(result["series"]) == 12
    assert result["qualifying_streaks"][0]["hours"] == 4


def test_qualifying_streaks_lists_every_run_of_four_or_more():
    values = [HOT] * 4 + [COOL] + [HOT] * 5 + [COOL] + [HOT] * 2
    result = detect(values)
    assert [s["hours"] for s in result["qualifying_streaks"]] == [4, 5]
    assert result["longest_hot_streak_hours"] == 5
