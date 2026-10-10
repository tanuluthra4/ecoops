import json

import pytest
import requests

from helpers import HOT, make_weather
from services import nasa_power


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(nasa_power.config, "DATA_FILE", tmp_path / "saved.json")
    nasa_power.clear_memory_cache()
    yield
    nasa_power.clear_memory_cache()


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def patch_get(monkeypatch, behaviour):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append({"url": url, "params": params, "timeout": timeout})
        if isinstance(behaviour, Exception):
            raise behaviour
        return behaviour

    monkeypatch.setattr(nasa_power.requests, "get", fake_get)
    return calls


def test_request_uses_a_timeout(monkeypatch):
    calls = patch_get(monkeypatch, FakeResponse(make_weather([HOT])))
    assert nasa_power.get_weather_data() is not None
    assert calls[0]["timeout"] and calls[0]["timeout"] > 0


@pytest.mark.parametrize("behaviour", [
    requests.Timeout("slow"),
    requests.ConnectionError("down"),
    FakeResponse({}, status=500),
    FakeResponse(ValueError("not json")),
    FakeResponse({"properties": {}}),
])
def test_failures_return_none_instead_of_raising(monkeypatch, behaviour):
    patch_get(monkeypatch, behaviour)
    assert nasa_power.get_weather_data() is None


def test_unreachable_without_saved_copy_is_unavailable_never_invented(monkeypatch):
    patch_get(monkeypatch, requests.ConnectionError("down"))
    bundle = nasa_power.load_weather_bundle()
    assert bundle["data"] is None
    assert bundle["source"]["kind"] == "unavailable"
    assert "fetch_demo_data" in bundle["source"]["note"]


def test_successful_retrieval_is_saved_and_reused_offline(monkeypatch):
    calls = patch_get(monkeypatch, FakeResponse(make_weather([HOT] * 4)))
    first = nasa_power.load_weather_bundle()
    assert first["source"]["kind"] == "retrieved"
    assert first["source"]["is_live"] is False
    assert len(calls) == 1

    # New process: memory empty, network gone, saved copy still works.
    nasa_power.clear_memory_cache()
    patch_get(monkeypatch, requests.ConnectionError("offline"))
    second = nasa_power.load_weather_bundle()
    assert second["source"]["kind"] == "saved_copy"
    assert second["data"] == first["data"]


def test_dataset_is_fetched_only_once_per_process(monkeypatch):
    calls = patch_get(monkeypatch, FakeResponse(make_weather([HOT] * 4)))
    nasa_power.load_weather_bundle()
    nasa_power.load_weather_bundle()
    nasa_power.load_weather_bundle()
    assert len(calls) == 1


def test_saved_copy_for_a_different_request_is_ignored(monkeypatch, tmp_path):
    saved = {
        "meta": {"lat": 1.0, "lon": 2.0, "start": "20250101", "end": "20250102"},
        "nasa_power_response": make_weather([HOT] * 4),
    }
    (tmp_path / "saved.json").write_text(json.dumps(saved), encoding="utf-8")
    patch_get(monkeypatch, requests.ConnectionError("down"))
    assert nasa_power.load_weather_bundle()["source"]["kind"] == "unavailable"


def test_corrupt_saved_file_is_ignored(monkeypatch, tmp_path):
    (tmp_path / "saved.json").write_text("{not json", encoding="utf-8")
    patch_get(monkeypatch, requests.ConnectionError("down"))
    assert nasa_power.load_weather_bundle()["source"]["kind"] == "unavailable"


def test_refresh_failure_falls_back_to_saved_copy(monkeypatch):
    patch_get(monkeypatch, FakeResponse(make_weather([HOT] * 4)))
    nasa_power.load_weather_bundle()
    nasa_power.clear_memory_cache()

    patch_get(monkeypatch, requests.Timeout("slow"))
    bundle = nasa_power.load_weather_bundle(refresh=True)
    assert bundle["source"]["kind"] == "saved_copy"
    assert "could not be reached" in bundle["source"]["note"]


def test_time_standard_defaults_to_documented_lst_when_header_missing(monkeypatch):
    patch_get(monkeypatch, FakeResponse(make_weather([HOT] * 4)))
    source = nasa_power.load_weather_bundle()["source"]
    assert source["time_standard"] == "LST"
    assert "documentation" in source["time_standard_origin"]


def test_time_standard_comes_from_header_when_present(monkeypatch):
    payload = make_weather([HOT] * 4)
    payload["header"] = {"time_standard": "UTC"}
    patch_get(monkeypatch, FakeResponse(payload))
    source = nasa_power.load_weather_bundle()["source"]
    assert source["time_standard"] == "UTC"
    assert source["time_standard_origin"] == "response header"
