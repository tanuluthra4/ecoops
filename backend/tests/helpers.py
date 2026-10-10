"""Test fixtures only. The values built here are synthetic and exist solely
to exercise the code; they are never used by the application."""

from datetime import datetime, timedelta


def make_weather(values, start="2025-05-01 00"):
    """Build a NASA-POWER-shaped payload from a list of hourly values.

    Use None for a missing hour (written as the -999 sentinel).
    """
    stamp = datetime.strptime(start, "%Y-%m-%d %H")
    series = {}
    for value in values:
        series[stamp.strftime("%Y%m%d%H")] = -999 if value is None else value
        stamp += timedelta(hours=1)
    return {"properties": {"parameter": {"T2M": series}}}


def bundle_for(values):
    return {
        "data": make_weather(values),
        "source": {
            "kind": "saved_copy",
            "provider": "NASA POWER",
            "synthetic": True,
            "is_live": False,
            "time_standard": "LST",
        },
    }


COOL = 30.0
HOT = 38.0
