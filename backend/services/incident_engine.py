"""Heat/cold incident detection from hourly temperature readings.

EcoOps thresholds are demonstration settings, not official warnings or
universal meteorological definitions. Missing/invalid hours break a streak.
"""
import math
from datetime import datetime, timedelta

from config import HEAT_RULES, COLD_RULES

SENTINEL = -999


def _is_valid_reading(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if not math.isfinite(value):
        return False
    return value != SENTINEL


def _parse_hour(key):
    try:
        return datetime.strptime(str(key), "%Y%m%d%H")
    except (TypeError, ValueError):
        return None


def _extract_hourly_grid(weather_data):
    """Return every hour from first to last timestamp, filling gaps with None."""
    try:
        raw = weather_data["properties"]["parameter"]["T2M"]
    except (KeyError, TypeError):
        return []
    if not isinstance(raw, dict):
        return []

    readings = {}
    for key, value in raw.items():
        stamp = _parse_hour(key)
        if stamp is not None:
            readings[stamp] = value if _is_valid_reading(value) else None
    if not readings:
        return []

    grid = []
    stamp, last = min(readings), max(readings)
    while stamp <= last:
        grid.append((stamp, readings.get(stamp)))
        stamp += timedelta(hours=1)
    return grid


def _iso(stamp):
    return stamp.strftime("%Y-%m-%dT%H:00")


def _is_triggered(value, threshold, comparison):
    return value >= threshold if comparison == "gte" else value <= threshold


def _unavailable(rules, message):
    threshold = rules["threshold_c"]
    return {
        "incident": False,
        "type": "DATA_UNAVAILABLE",
        "hazard": rules["hazard"],
        "severity": "UNKNOWN",
        "max_temp": None,
        "avg_temp": None,
        "longest_hot_streak_hours": 0,  # retained for API compatibility
        "longest_streak_hours": 0,
        "threshold": threshold,
        "valid_observations": 0,
        "evidence": [message],
        "min_temp": None,
        "peak_time": None,
        "hours_at_or_above_threshold": 0,
        "hours_at_or_below_threshold": 0,
        "longest_streak_start": None,
        "longest_streak_end": None,
        "qualifying_streaks": [],
        "missing_observations": 0,
        "expected_observations": 0,
        "observation_start": None,
        "observation_end": None,
        "series": [],
        "rules": dict(rules),
    }


def detect_temperature_incident(weather_data, hazard="heat", rules=None):
    """Detect a sustained heat or cold threshold crossing in hourly data."""
    if hazard not in {"heat", "cold"}:
        raise ValueError("hazard must be 'heat' or 'cold'")
    rules = dict(rules or (HEAT_RULES if hazard == "heat" else COLD_RULES))
    rules.setdefault("hazard", hazard)
    rules.setdefault("comparison", "gte" if hazard == "heat" else "lte")
    threshold = rules["threshold_c"]
    min_streak = rules["min_streak_hours"]
    high_streak = rules["high_streak_hours"]
    comparison = rules["comparison"]
    triggered_label = "at or above" if comparison == "gte" else "at or below"

    grid = _extract_hourly_grid(weather_data)
    valid = [(stamp, value) for stamp, value in grid if value is not None]
    if not valid:
        return _unavailable(
            rules, "No valid hourly temperature observations were available."
        )

    values = [value for _, value in valid]
    max_temp, min_temp = max(values), min(values)
    avg_temp = sum(values) / len(values)
    peak_time = next(stamp for stamp, value in valid if value == max_temp)
    min_time = next(stamp for stamp, value in valid if value == min_temp)

    runs, current = [], []
    for stamp, value in grid:
        if value is not None and _is_triggered(value, threshold, comparison):
            current.append((stamp, value))
        else:
            if current:
                runs.append(current)
            current = []
    if current:
        runs.append(current)

    longest = max(runs, key=len) if runs else []
    longest_hours = len(longest)
    incident = longest_hours >= min_streak
    severity = (
        "HIGH" if longest_hours >= high_streak
        else "MEDIUM" if longest_hours >= min_streak
        else "LOW"
    )
    qualifying = [
        {
            "start": _iso(run[0][0]),
            "end": _iso(run[-1][0]),
            "hours": len(run),
            "peak_temp": round(max(v for _, v in run), 1),
            "min_temp": round(min(v for _, v in run), 1),
        }
        for run in runs if len(run) >= min_streak
    ]
    hours_at_or_above = sum(1 for value in values if value >= threshold)
    hours_at_or_below = sum(1 for value in values if value <= threshold)
    expected = len(grid)
    noun = "hot" if hazard == "heat" else "cold"
    evidence = [
        f"Peak temperature reached {max_temp:.1f}°C",
        f"Minimum temperature reached {min_temp:.1f}°C",
        f"Average temperature was {avg_temp:.1f}°C",
        f"Longest {noun} period {triggered_label} {threshold:g}°C: {longest_hours} consecutive hours",
        f"{len(values)} valid hourly observations analyzed",
    ]

    event_type = "HEAT_EVENT" if hazard == "heat" else "COLD_EVENT"
    no_event_type = "NO_HEAT_EVENT" if hazard == "heat" else "NO_COLD_EVENT"
    return {
        "incident": incident,
        "type": event_type if incident else no_event_type,
        "hazard": hazard,
        "severity": severity,
        "max_temp": round(max_temp, 1),
        "avg_temp": round(avg_temp, 1),
        "longest_hot_streak_hours": longest_hours,  # legacy API/model field
        "longest_streak_hours": longest_hours,
        "threshold": threshold,
        "valid_observations": len(values),
        "evidence": evidence,
        "min_temp": round(min_temp, 1),
        "peak_time": _iso(peak_time),
        "min_time": _iso(min_time),
        "hours_at_or_above_threshold": hours_at_or_above,
        "hours_at_or_below_threshold": hours_at_or_below,
        "longest_streak_start": _iso(longest[0][0]) if longest else None,
        "longest_streak_end": _iso(longest[-1][0]) if longest else None,
        "qualifying_streaks": qualifying,
        "missing_observations": expected - len(values),
        "expected_observations": expected,
        "observation_start": _iso(grid[0][0]),
        "observation_end": _iso(grid[-1][0]),
        "series": [
            {"time": _iso(stamp), "temp_c": None if value is None else round(value, 2)}
            for stamp, value in grid
        ],
        "rules": rules,
    }


def detect_heat_incident(weather_data, rules=None):
    """Backward-compatible heat-only detector entry point."""
    return detect_temperature_incident(weather_data, "heat", rules=rules)
