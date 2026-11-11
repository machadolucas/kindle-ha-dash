"""Test HA 2026.11 while the published custom-component plugin catches up.

0.13.375 targets 2026.10.4. Load HA before the plugin's respx import so
httpx2 aliases are installed, and provide its removed, unused logger test helper.
The integration itself receives no compatibility patches or mocked HA APIs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import homeassistant  # noqa: F401 -- installs HA's httpx2 aliases before respx
import pytest
from homeassistant.components import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _unused_old_logger_helper(*args: object) -> None:
    raise AssertionError("Old plugin logger helper is unsupported on HA 2026.11")


# This import-only adapter is never exercised by these integration tests.
if not hasattr(logger, "_clear_logger_overwrites"):
    logger._clear_logger_overwrites = _unused_old_logger_helper

pytest_plugins = ["pytest_homeassistant_custom_component.plugins"]


@pytest.fixture(autouse=True)
def custom_integration(enable_custom_integrations):
    """All HA tests may load this repository's custom integration."""
    yield


@pytest.fixture
async def configured(hass, hass_client_no_auth, freezer):
    """An isolated HA core and loopback client; never a real HA/device connection."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.kindle_dash.const import DEFAULT_OPTIONS, DOMAIN

    freezer.move_to("2026-11-11T12:31:00+00:00")
    await hass.config.async_set_time_zone("Europe/Helsinki")
    entry = MockConfigEntry(
        domain=DOMAIN, data={"token": "test-only-token"}, options=DEFAULT_OPTIONS
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()
    return entry, client
