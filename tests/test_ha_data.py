"""Verify forecast response actions and options are passed through to pure parsing."""

import json
from pathlib import Path
from unittest.mock import patch

from homeassistant.core import SupportsResponse

from custom_components.kindle_dash import ha_data
from custom_components.kindle_dash.ha_data import async_dashboard_data


async def test_forecasts_use_response_service_and_configured_sources(hass, configured):
    entry, _ = configured
    fixtures = Path(__file__).parent / "fixtures"
    states = json.loads((fixtures / "states.json").read_text())
    for entity_id, state in states.items():
        hass.states.async_set(entity_id, state["state"], state["attributes"])
    calls = []

    async def forecasts(call):
        assert call.return_response is True
        calls.append(call.data)
        return json.loads((fixtures / f"forecast_{call.data['type']}.json").read_text())

    hass.services.async_register(
        "weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY
    )
    data = await async_dashboard_data(hass, entry.runtime_data, 34)
    assert {call["type"] for call in calls} == {"hourly", "daily"}
    assert all(call["entity_id"] == "weather.forecast_home" for call in calls)
    assert data.weather.temperature == 4.16 and len(data.weather.hourly) == 48
    assert data.meta.battery == 34


async def test_stale_humidity_entity_is_not_collected_or_read_from_weather(
    hass, configured, monkeypatch
):
    entry, _ = configured
    entry.runtime_data.options["outdoor_humidity_entity"] = "sensor.old_humidity"
    fixtures = Path(__file__).parent / "fixtures"
    states = json.loads((fixtures / "states.json").read_text())
    states["weather.forecast_home"]["attributes"]["humidity"] = 93
    for entity_id, state in states.items():
        hass.states.async_set(entity_id, state["state"], state["attributes"])

    async def forecasts(call):
        return {}

    hass.services.async_register(
        "weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY
    )
    state_get = type(hass.states).get
    requested = []

    def tracked_get(machine, entity_id):
        requested.append(entity_id)
        return state_get(machine, entity_id)

    original_parse = ha_data.parse_dashboard

    class NoWeatherHumidity(dict):
        def get(self, key, default=None):
            assert key != "humidity", "weather humidity must not be read"
            return super().get(key, default)

    def guarded_parse(state_values, *args, **kwargs):
        state_values["weather.forecast_home"]["attributes"] = NoWeatherHumidity(
            state_values["weather.forecast_home"]["attributes"]
        )
        return original_parse(state_values, *args, **kwargs)

    monkeypatch.setattr(type(hass.states), "get", tracked_get)
    with patch.object(ha_data, "parse_dashboard", side_effect=guarded_parse):
        await async_dashboard_data(hass, entry.runtime_data)

    assert "sensor.old_humidity" not in requested
