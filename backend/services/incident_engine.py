def detect_heat_incident(weather_data):

    temperatures = (
        weather_data["properties"]["parameter"]["T2M"]
    )

    # NASA POWER uses -999 as a missing-data value
    temp_values = [
        value for value in temperatures.values()
        if value != -999
    ]

    print("VALID TEMPERATURE DATA:")
    for timestamp, temperature in temperatures.items():
        if temperature != -999:
            print(timestamp, temperature)

    if not temp_values:
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

    max_temp = max(temp_values)
    avg_temp = sum(temp_values) / len(temp_values)

    incident = False
    severity = "LOW"

    if max_temp >= 42:
        incident = True
        severity = "HIGH"
    elif max_temp >= 38:
        incident = True
        severity = "MEDIUM"

    return {
        "incident": incident,
        "type": "EXTREME_HEAT" if incident else "NO_HEAT_INCIDENT",
        "severity": severity,
        "max_temp": round(max_temp, 1),
        "avg_temp": round(avg_temp, 1),
        "valid_observations": len(temp_values),
        "evidence": [
            f"Peak temperature reached {max_temp:.1f}°C",
            f"Average temperature {avg_temp:.1f}°C",
            f"{len(temp_values)} valid observations analyzed"
        ]
    }