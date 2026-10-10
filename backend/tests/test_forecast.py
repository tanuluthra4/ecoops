from datetime import datetime, timedelta, timezone

import requests

from services import forecast

INDIA_TZ = timezone(timedelta(hours=5, minutes=30), name="IST")


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self.payload


def make_payload(values):
    start = datetime.now(INDIA_TZ).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    times = [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(len(values))]
    return {"hourly": {"time": times, "temperature_2m": values}}


def setup_function():
    forecast.clear_forecast_cache()


def test_forecast_payload_is_normalized_and_marked_as_forecast(monkeypatch):
    values = [29.0, 36.0, 36.5, 37.0, 38.0, 36.0, 35.5, 30.0]
    monkeypatch.setattr(forecast.requests, "get", lambda *a, **k: FakeResponse(make_payload(values)))
    bundle = forecast.load_forecast_bundle(refresh=True)
    assert bundle["source"]["provider"] == "Open-Meteo"
    assert bundle["source"]["is_forecast"] is True
    assert bundle["source"]["is_live"] is False
    assert len(bundle["data"]["properties"]["parameter"]["T2M"]) == len(values)
    assert list(bundle["data"]["properties"]["parameter"]["T2M"].values()) == values


def test_forecast_failure_returns_unavailable_not_fake_values(monkeypatch):
    monkeypatch.setattr(forecast.requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("offline")))
    bundle = forecast.load_forecast_bundle(refresh=True)
    assert bundle["data"] is None
    assert bundle["source"]["kind"] == "unavailable"
    assert bundle["source"]["is_forecast"] is True


def test_forecast_uses_timeout_and_delhi_timezone(monkeypatch):
    calls = []
    def fake_get(url, params=None, timeout=None):
        calls.append((params, timeout))
        return FakeResponse(make_payload([30.0, 31.0]))
    monkeypatch.setattr(forecast.requests, "get", fake_get)
    forecast.load_forecast_bundle(refresh=True)
    assert calls[0][1] > 0
    assert calls[0][0]["timezone"] == "Asia/Kolkata"
    assert calls[0][0]["forecast_days"] == 7


def test_forecast_discards_hours_before_current_local_hour(monkeypatch):
    current = datetime.now(INDIA_TZ).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    stamps = [(current + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(-3, 4)]
    payload = {"hourly": {"time": stamps, "temperature_2m": [30.0] * len(stamps)}}
    monkeypatch.setattr(forecast.requests, "get", lambda *a, **k: FakeResponse(payload))
    bundle = forecast.load_forecast_bundle(refresh=True)
    series = bundle["data"]["properties"]["parameter"]["T2M"]
    assert len(series) == 4
    assert min(series) == current.strftime("%Y%m%d%H")
