"""Forecast feed for proactive EcoOps risk screening.

Open-Meteo forecast values are model forecasts, not observations or official
warnings. The service never fabricates data; unavailable forecasts return an
explicit unavailable bundle so the UI can offer historical replay separately.
"""
from datetime import datetime, timezone, timedelta
import logging
import time

import requests
import os

from config import DEMO_LOCATION, NASA_TIMEOUT_SECONDS

logger = logging.getLogger("ecoops.forecast")
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEZONE = "Asia/Kolkata"
# India uses UTC+05:30 year-round. A fixed offset avoids depending on the
# system IANA timezone database, which is often absent in Windows Python installs.
INDIA_TZ = timezone(timedelta(hours=5, minutes=30), name="IST")
FORECAST_DAYS = 7
_cache = {}
CACHE_SECONDS = 3600

RATE_LIMIT_COOLDOWN_SECONDS = 300
_last_rate_limit_at = 0.0


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



def _parse_hourly_series(entries, time_format, time_key, temp_key):
    """Convert provider hourly readings to EcoOps' YYYYMMDDHH grid."""
    series = {}
    current_hour = datetime.now(INDIA_TZ).replace(
        minute=0, second=0, microsecond=0
    ).replace(tzinfo=None)

    for entry in entries:
        try:
            stamp = datetime.strptime(entry[time_key], time_format)
            if stamp < current_hour:
                continue

            value = entry.get(temp_key)
            key = stamp.strftime("%Y%m%d%H")
            series[key] = (
                value
                if isinstance(value, (int, float))
                and not isinstance(value, bool)
                else -999
            )
        except (KeyError, TypeError, ValueError):
            continue

    if not series:
        raise ValueError("No usable future hourly temperatures returned.")

    return series


def load_forecast_bundle(refresh=False):
    """Load Open-Meteo forecast, falling back to WeatherAPI if needed."""
    now_mono = time.monotonic()

    if (
        not refresh
        and "bundle" in _cache
        and now_mono - _cache["at"] < CACHE_SECONDS
    ):
        return _cache["bundle"]

    provider = "Open-Meteo"
    dataset = (
        "Hourly 2 m air-temperature forecast; "
        "apparent temperature and relative humidity also requested"
    )

    open_meteo_params = {
        "latitude": DEMO_LOCATION["lat"],
        "longitude": DEMO_LOCATION["lon"],
        "hourly": (
            "temperature_2m,apparent_temperature,"
            "relative_humidity_2m"
        ),
        "forecast_days": FORECAST_DAYS,
        "timezone": TIMEZONE,
        "temperature_unit": "celsius",
    }

    try:
        # Primary provider: Open-Meteo
        try:
            response = requests.get(
                FORECAST_URL,
                params=open_meteo_params,
                timeout=NASA_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            hourly = payload.get("hourly", {})
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])

            if not times or len(times) != len(temps):
                raise ValueError(
                    "Open-Meteo returned an incomplete hourly series."
                )

            entries = [
                {"time": stamp, "temperature": temp}
                for stamp, temp in zip(times, temps)
            ]

            series = _parse_hourly_series(
                entries,
                "%Y-%m-%dT%H:%M",
                "time",
                "temperature",
            )

        except (
            requests.RequestException,
            ValueError,
            TypeError,
            KeyError,
        ) as primary_error:
            logger.warning(
                "Open-Meteo failed; trying WeatherAPI fallback: %s",
                primary_error,
            )

            # Secondary provider: WeatherAPI
            api_key = os.getenv("WEATHERAPI_KEY")
            if not api_key:
                raise RuntimeError(
                    "WEATHERAPI_KEY is not configured."
                ) from primary_error

            fallback_response = requests.get(
                "https://api.weatherapi.com/v1/forecast.json",
                params={
                    "key": api_key,
                    "q": (
                        f'{DEMO_LOCATION["lat"]},'
                        f'{DEMO_LOCATION["lon"]}'
                    ),
                    "days": 3,
                    "aqi": "no",
                    "alerts": "no",
                },
                timeout=NASA_TIMEOUT_SECONDS,
            )
            fallback_response.raise_for_status()
            fallback_payload = fallback_response.json()

            forecast_days = fallback_payload.get(
                "forecast", {}
            ).get("forecastday", [])

            fallback_entries = [
                hour
                for day in forecast_days
                for hour in day.get("hour", [])
            ]

            series = _parse_hourly_series(
                fallback_entries,
                "%Y-%m-%d %H:%M",
                "time",
                "temp_c",
            )

            provider = "WeatherAPI.com"
            dataset = "Hourly 2 m air-temperature forecast"

            logger.info(
                "WeatherAPI fallback succeeded with %d hourly readings.",
                len(series),
            )

        retrieved_at = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        start, end = min(series), max(series)

        data = {"properties": {"parameter": {"T2M": series}}}

        if provider == "Open-Meteo":
            note = (
                "Open-Meteo forecast model output. These are predictions, "
                "not observed temperatures or an official warning."
            )
        else:
            note = (
                "Open-Meteo was unavailable; hourly forecast retrieved "
                "from WeatherAPI.com. These are predictions, not observed "
                "temperatures or an official warning. The fallback provides "
                "up to three forecast days on this configuration."
            )

        source = {
            "kind": "forecast",
            "provider": provider,
            "dataset": dataset,
            "location": {
                "name": DEMO_LOCATION["name"],
                "lat": DEMO_LOCATION["lat"],
                "lon": DEMO_LOCATION["lon"],
            },
            "window": {
                "start": datetime.strptime(
                    start, "%Y%m%d%H"
                ).strftime("%Y-%m-%d %H:00"),
                "end": datetime.strptime(
                    end, "%Y%m%d%H"
                ).strftime("%Y-%m-%d %H:00"),
            },
            "retrieved_at": retrieved_at,
            "time_standard": "IST (Asia/Kolkata)",
            "synthetic": False,
            "is_live": False,
            "is_forecast": True,
            "note": note,
            "forecast_days": (
                FORECAST_DAYS if provider == "Open-Meteo" else 3
            ),
        }

        bundle = {"data": data, "source": source}
        _cache["at"] = time.monotonic()
        _cache["bundle"] = bundle
        return bundle

    except (
        requests.RequestException,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
    ) as exc:
        logger.error("All forecast providers failed: %s", exc)

        unavailable = _unavailable_source(
            "Open-Meteo and WeatherAPI could not provide a usable forecast. "
            "Check provider availability and the WEATHERAPI_KEY setting. "
            "No forecast values were invented."
        )
        unavailable["provider"] = "Open-Meteo + WeatherAPI.com"

        return {"data": None, "source": unavailable}
