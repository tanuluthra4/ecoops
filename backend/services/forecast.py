"""Forecast feed for proactive EcoOps risk screening.

Open-Meteo forecast values are model forecasts, not observations or official
warnings. The service never fabricates data; unavailable forecasts return an
explicit unavailable bundle so the UI can offer historical replay separately.
"""
from datetime import datetime, timezone, timedelta
import logging
import time

import requests

from config import DEMO_LOCATION, NASA_TIMEOUT_SECONDS

logger = logging.getLogger("ecoops.forecast")
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEZONE = "Asia/Kolkata"
# India uses UTC+05:30 year-round. A fixed offset avoids depending on the
# system IANA timezone database, which is often absent in Windows Python installs.
INDIA_TZ = timezone(timedelta(hours=5, minutes=30), name="IST")
FORECAST_DAYS = 7
_cache = {}
CACHE_SECONDS = 600


def clear_forecast_cache():
    _cache.clear()


def _unavailable_source(note):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "kind": "unavailable", "provider": "Open-Meteo", "dataset": "Hourly forecast temperature at 2 m",
        "location": {"name": DEMO_LOCATION["name"], "lat": DEMO_LOCATION["lat"], "lon": DEMO_LOCATION["lon"]},
        "window": {"start": None, "end": None}, "retrieved_at": now,
        "time_standard": "IST (Asia/Kolkata)", "synthetic": False,
        "is_live": False, "is_forecast": True, "note": note,
    }


def load_forecast_bundle(refresh=False):
    """Return a forecast in the detector's expected hourly-grid format."""
    now_mono = time.monotonic()
    if not refresh and "bundle" in _cache and now_mono - _cache["at"] < CACHE_SECONDS:
        return _cache["bundle"]

    params = {
        "latitude": DEMO_LOCATION["lat"],
        "longitude": DEMO_LOCATION["lon"],
        "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m",
        "forecast_days": FORECAST_DAYS,
        "timezone": TIMEZONE,
        "temperature_unit": "celsius",
    }
    try:
        response = requests.get(FORECAST_URL, params=params, timeout=NASA_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
        hourly = payload.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        if not times or len(times) != len(temps):
            raise ValueError("Forecast response did not contain a complete hourly temperature series.")
        series = {}
        # Open-Meteo can include earlier hours from the current calendar day.
        # Keep the current hour onward so the product screens upcoming risk,
        # rather than treating already-past hours as a future forecast.
        current_hour = datetime.now(INDIA_TZ).replace(minute=0, second=0, microsecond=0)
        for stamp, value in zip(times, temps):
            try:
                local_stamp = datetime.strptime(stamp, "%Y-%m-%dT%H:%M")
                if local_stamp < current_hour.replace(tzinfo=None):
                    continue
                key = local_stamp.strftime("%Y%m%d%H")
                series[key] = value if isinstance(value, (int, float)) and not isinstance(value, bool) else -999
            except (TypeError, ValueError):
                continue
        if not series:
            raise ValueError("Forecast response contained no usable hourly timestamps.")
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        logger.warning("Open-Meteo forecast request failed: %s", exc)
        return {"data": None, "source": _unavailable_source(
            "Could not retrieve a usable Open-Meteo forecast. Check the internet connection and retry, or switch to historical replay. No forecast values were invented."
        )}

    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    start, end = min(series), max(series)
    data = {"properties": {"parameter": {"T2M": series}}}
    source = {
        "kind": "forecast", "provider": "Open-Meteo",
        "dataset": "Hourly 2 m air-temperature forecast; apparent temperature and relative humidity also requested",
        "location": {"name": DEMO_LOCATION["name"], "lat": DEMO_LOCATION["lat"], "lon": DEMO_LOCATION["lon"]},
        "window": {"start": datetime.strptime(start, "%Y%m%d%H").strftime("%Y-%m-%d %H:00"),
                   "end": datetime.strptime(end, "%Y%m%d%H").strftime("%Y-%m-%d %H:00")},
        "retrieved_at": retrieved_at, "time_standard": "IST (Asia/Kolkata)",
        "synthetic": False, "is_live": False, "is_forecast": True,
        "note": "Forecast model output retrieved this session. These are predictions, not observed temperatures or an official warning. Forecasts can change.",
        "forecast_days": FORECAST_DAYS,
    }
    bundle = {"data": data, "source": source}
    _cache["at"] = now_mono
    _cache["bundle"] = bundle
    return bundle
