"""NASA POWER access: retrieval, a saved local copy, and data provenance.

The demonstration uses a fixed historical window, so the finished data does
not change. The first successful retrieval is saved to data/demo_incident.json
and reused afterwards, which lets the demo run offline.

Nothing here ever invents data. If NASA POWER cannot be reached and there is
no saved copy, the bundle reports kind="unavailable" and callers must show an
error state.
"""

import json
import logging
from datetime import datetime, timezone

import requests

import config
from config import DEMO_LOCATION, DEMO_WINDOW, NASA_TIMEOUT_SECONDS

logger = logging.getLogger("ecoops.nasa_power")

BASE_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
PARAMETERS = "T2M,RH2M"

# Per NASA POWER documentation, the hourly API defaults to Local Solar Time
# when no time-standard parameter is sent. We do not send one (this keeps the
# prototype's behaviour), so timestamps are LST unless the response header
# says otherwise.
DEFAULT_TIME_STANDARD = "LST"

_memory_cache = {}


def _has_temperature_series(data):
    try:
        return isinstance(data["properties"]["parameter"]["T2M"], dict)
    except (KeyError, TypeError):
        return False


def get_weather_data(
    lat=DEMO_LOCATION["lat"],
    lon=DEMO_LOCATION["lon"],
    start=DEMO_WINDOW["start"],
    end=DEMO_WINDOW["end"],
):
    """Fetch hourly weather data from NASA POWER. Default: Delhi.

    Returns the parsed JSON, or None on any failure. Never raises.
    """
    params = {
        "parameters": PARAMETERS,
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "start": start,
        "end": end,
        "format": "JSON",
    }

    try:
        response = requests.get(
            BASE_URL, params=params, timeout=NASA_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("NASA POWER request failed: %s", exc)
        return None

    if not _has_temperature_series(data):
        logger.warning("NASA POWER response had no properties.parameter.T2M")
        return None

    return data


def _same_request(meta, lat, lon, start, end):
    try:
        return (
            round(float(meta["lat"]), 4) == round(float(lat), 4)
            and round(float(meta["lon"]), 4) == round(float(lon), 4)
            and str(meta["start"]) == str(start)
            and str(meta["end"]) == str(end)
        )
    except (KeyError, TypeError, ValueError):
        return False


def _read_saved(lat, lon, start, end):
    try:
        with open(config.DATA_FILE, encoding="utf-8") as handle:
            saved = json.load(handle)
        meta = saved["meta"]
        data = saved["nasa_power_response"]
    except (OSError, ValueError, KeyError, TypeError):
        return None

    if not _has_temperature_series(data) or not _same_request(
        meta, lat, lon, start, end
    ):
        return None
    return data, meta


def _write_saved(data, lat, lon, start, end, retrieved_at):
    payload = {
        "meta": {
            "provider": "NASA POWER",
            "retrieved_at": retrieved_at,
            "lat": lat,
            "lon": lon,
            "start": start,
            "end": end,
            "parameters": PARAMETERS,
            "synthetic": False,
        },
        "nasa_power_response": data,
    }
    try:
        config.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(config.DATA_FILE, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    except OSError as exc:
        logger.warning("Could not save NASA POWER copy: %s", exc)


def _source_info(kind, lat, lon, start, end, data=None, retrieved_at=None,
                 synthetic=False, note=""):
    header = {}
    if isinstance(data, dict) and isinstance(data.get("header"), dict):
        header = data["header"]

    reported = header.get("time_standard")
    return {
        "kind": kind,
        "provider": "NASA POWER",
        "dataset": "Hourly point data, T2M (air temperature at 2 m, degrees C)",
        "location": {"lat": lat, "lon": lon},
        "window": {"start": start, "end": end},
        "retrieved_at": retrieved_at,
        "time_standard": reported or DEFAULT_TIME_STANDARD,
        "time_standard_origin": "response header" if reported else "NASA POWER documentation default",
        "synthetic": bool(synthetic),
        "is_live": False,
        "note": note,
    }


def load_weather_bundle(
    lat=DEMO_LOCATION["lat"],
    lon=DEMO_LOCATION["lon"],
    start=DEMO_WINDOW["start"],
    end=DEMO_WINDOW["end"],
    refresh=False,
):
    """Return {"data": <NASA JSON or None>, "source": <provenance dict>}.

    Order: memory -> saved local copy -> NASA POWER request.
    refresh=True skips memory and the saved copy and asks NASA POWER again
    (falling back to the saved copy if the request fails).
    """
    key = (round(lat, 4), round(lon, 4), str(start), str(end))

    if not refresh and key in _memory_cache:
        return _memory_cache[key]

    bundle = None

    if not refresh:
        saved = _read_saved(lat, lon, start, end)
        if saved:
            data, meta = saved
            bundle = {
                "data": data,
                "source": _source_info(
                    "saved_copy", lat, lon, start, end, data,
                    retrieved_at=meta.get("retrieved_at"),
                    synthetic=meta.get("synthetic", False),
                    note="Saved copy of an earlier NASA POWER response. "
                         "Historical data, not a live observation.",
                ),
            }

    if bundle is None:
        data = get_weather_data(lat, lon, start, end)
        if data is not None:
            retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            _write_saved(data, lat, lon, start, end, retrieved_at)
            bundle = {
                "data": data,
                "source": _source_info(
                    "retrieved", lat, lon, start, end, data,
                    retrieved_at=retrieved_at,
                    note="Retrieved from NASA POWER just now. The window is "
                         "historical, so this is not a live observation.",
                ),
            }

    if bundle is None and refresh:
        saved = _read_saved(lat, lon, start, end)
        if saved:
            data, meta = saved
            bundle = {
                "data": data,
                "source": _source_info(
                    "saved_copy", lat, lon, start, end, data,
                    retrieved_at=meta.get("retrieved_at"),
                    synthetic=meta.get("synthetic", False),
                    note="NASA POWER could not be reached, so the saved copy "
                         "is shown. Historical data, not a live observation.",
                ),
            }

    if bundle is None:
        return {
            "data": None,
            "source": _source_info(
                "unavailable", lat, lon, start, end,
                note="NASA POWER could not be reached and no saved copy "
                     "exists. Run `python scripts/fetch_demo_data.py` once "
                     "while online to create one.",
            ),
        }

    _memory_cache[key] = bundle
    return bundle


def clear_memory_cache():
    _memory_cache.clear()
