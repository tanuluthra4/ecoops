"""Heat-incident detection from hourly temperature observations.

Operational rule (EcoOps demonstration setting, not a meteorological
heatwave definition): an incident exists when at least `min_streak_hours`
consecutive hourly readings are at or above `threshold_c`.

Missing hours (-999 sentinel, non-numeric values, absent timestamps) are
excluded from statistics AND break a streak, so two hot stretches separated
by a data gap are never counted as one continuous run.
"""

import math
from datetime import datetime, timedelta

from config import HEAT_RULES

SENTINEL = -999


def _is_valid_reading(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if math.isnan(value) or math.isinf(value):
        return False
    return value != SENTINEL


def _parse_hour(key):
    try:
        return datetime.strptime(str(key), "%Y%m%d%H")
    except ValueError:
        return None


def _extract_hourly_grid(weather_data):
    """List of (datetime, value or None) for every hour first..last."""
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
    stamp = min(readings)
    last = max(readings)
    while stamp <= last:
        grid.append((stamp, readings.get(stamp)))
        stamp += timedelta(hours=1)
    return grid


def _iso(stamp):
    return stamp.strftime("%Y-%m-%dT%H:00")


def _unavailable(rules, message):
    return {
        "incident": False,
        "type": "DATA_UNAVAILABLE",
        "severity": "UNKNOWN",
        "max_temp": None,
        "avg_temp": None,
        "longest_hot_streak_hours": 0,
        "threshold": rules["threshold_c"],
        "valid_observations": 0,
        "evidence": [message],
        "min_temp": None,
        "peak_time": None,
        "hours_at_or_above_threshold": 0,
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


def detect_heat_incident(weather_data, rules=None):
    rules = dict(rules or HEAT_RULES)
    threshold = rules["threshold_c"]
    min_streak = rules["min_streak_hours"]
    high_streak = rules["high_streak_hours"]

    grid = _extract_hourly_grid(weather_data)
    valid = [(stamp, value) for stamp, value in grid if value is not None]

    if not valid:
        return _unavailable(
            rules, "NASA POWER returned no valid temperature observations."
        )

    values = [value for _, value in valid]
    max_temp = max(values)
    min_temp = min(values)
    avg_temp = sum(values) / len(values)
    peak_time = next(stamp for stamp, value in valid if value == max_temp)

    runs = []
    current = []
    for stamp, value in grid:
        if value is not None and value >= threshold:
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
    if longest_hours >= high_streak:
        severity = "HIGH"
    elif longest_hours >= min_streak:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    qualifying = [
        {
            "start": _iso(run[0][0]),
            "end": _iso(run[-1][0]),
            "hours": len(run),
            "peak_temp": round(max(v for _, v in run), 1),
        }
        for run in runs
        if len(run) >= min_streak
    ]

    hours_at_or_above = sum(1 for value in values if value >= threshold)
    expected = len(grid)

    evidence = [
        f"Peak temperature reached {max_temp:.1f}°C",
        f"Average temperature was {avg_temp:.1f}°C",
        f"Longest period above {threshold:.0f}°C: "
        f"{longest_hours} consecutive hours",
        f"{len(values)} valid observations analyzed",
    ]

    return {
        "incident": incident,
        "type": "HEAT_EVENT" if incident else "NO_HEAT_EVENT",
        "severity": severity,
        "max_temp": round(max_temp, 1),
        "avg_temp": round(avg_temp, 1),
        "longest_hot_streak_hours": longest_hours,
        "threshold": threshold,
        "valid_observations": len(values),
        "evidence": evidence,
        "min_temp": round(min_temp, 1),
        "peak_time": _iso(peak_time),
        "hours_at_or_above_threshold": hours_at_or_above,
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
        "rules": dict(rules),
    }
