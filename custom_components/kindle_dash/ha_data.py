"""Thin HA reading layer; parsing and rendering live in independent modules."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .data import parse_dashboard
from .models import DashboardData, Meta
from .runtime import KindleDashRuntime

_LOGGER = logging.getLogger(__name__)


async def async_dashboard_data(
    hass: HomeAssistant,
    runtime: KindleDashRuntime,
    battery: int | None = None,
) -> DashboardData:
    """Fetch supported forecasts through the response action, never legacy attrs."""
    options = runtime.options
    weather = options["weather_entity"]

    async def forecast(kind: str) -> dict[str, Any]:
        if not weather or not hass.services.has_service("weather", "get_forecasts"):
            return {}
        try:
            async with asyncio.timeout(10):
                response = await hass.services.async_call(
                    "weather",
                    "get_forecasts",
                    {"entity_id": weather, "type": kind},
                    blocking=True,
                    return_response=True,
                )
                return response or {}
        except (HomeAssistantError, TimeoutError):
            _LOGGER.warning("Weather %s forecast unavailable", kind)
            return {}

    hourly, daily = await asyncio.gather(forecast("hourly"), forecast("daily"))
    states = {
        entity_id: {"state": state.state, "attributes": dict(state.attributes)}
        for key, entity_id in options.items()
        if key.endswith("_entity") and entity_id and (state := hass.states.get(entity_id))
    }
    return parse_dashboard(
        states,
        hourly,
        daily,
        options=options,
        meta=Meta(
            battery=battery if battery is not None else runtime.battery,
            last_seen=runtime.last_seen,
            time_zone=hass.config.time_zone,
        ),
    )
