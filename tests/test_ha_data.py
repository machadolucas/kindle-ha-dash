"""Verify forecast response actions and options are passed through to pure parsing."""

import json
from pathlib import Path

from homeassistant.core import SupportsResponse

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
