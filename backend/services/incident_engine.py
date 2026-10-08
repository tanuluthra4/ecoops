def detect_heat_incident(weather_data):

    temperatures = weather_data["properties"]["parameter"]["T2M"]

    valid_data = {
        timestamp: value
        for timestamp, value in temperatures.items()
        if value != -999
    }

    if not valid_data:
        return {
            "incident": False,
            "type": "DATA_UNAVAILABLE",
            "severity": "UNKNOWN",
            "max_temp": None,
            "avg_temp": None,
            "evidence": [
                "NASA POWER returned no valid temperature observations."
            ]
        }

    temp_values = list(valid_data.values())

    max_temp = max(temp_values)
    avg_temp = sum(temp_values) / len(temp_values)

    # EcoOps operational heat trigger
    threshold = 35.0

    longest_streak = 0
    current_streak = 0

    for temperature in temp_values:

        if temperature >= threshold:
            current_streak += 1
            longest_streak = max(
                longest_streak,
                current_streak
            )
        else:
            current_streak = 0

    incident = longest_streak >= 4

    if longest_streak >= 8:
        severity = "HIGH"
    elif longest_streak >= 4:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    return {
        "incident": incident,
        "type": "HEAT_EVENT" if incident else "NO_HEAT_EVENT",
        "severity": severity,
        "max_temp": round(max_temp, 1),
        "avg_temp": round(avg_temp, 1),
        "longest_hot_streak_hours": longest_streak,
        "threshold": threshold,
        "valid_observations": len(temp_values),
        "evidence": [
            f"Peak temperature reached {max_temp:.1f}°C",
            f"Average temperature was {avg_temp:.1f}°C",
            f"Longest period above {threshold:.0f}°C: "
            f"{longest_streak} consecutive hours",
            f"{len(temp_values)} valid observations analyzed"
        ]
    }