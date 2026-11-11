"""Real flow manager tests including token rotation and automatic reload."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kindle_dash.const import DEFAULT_OPTIONS, DOMAIN


async def test_ui_setup_and_single_instance(hass):
    with patch("custom_components.kindle_dash.async_setup_entry", return_value=None):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        assert result["type"] is FlowResultType.FORM
        assert "outdoor_humidity_entity" not in result["data_schema"].schema
        result = await hass.config_entries.flow.async_configure(result["flow_id"], DEFAULT_OPTIONS)
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert len(result["data"]["token"]) >= 43
        assert result["options"]["weather_entity"] == "weather.forecast_home"
        await hass.async_block_till_done()
        second = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        assert second["type"] is FlowResultType.ABORT
        assert second["reason"] == "single_instance_allowed"


async def test_invalid_options_have_translated_error(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    invalid = {**DEFAULT_OPTIONS, "schedule": "08:00-12:00 30\n11:00-13:00 30"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], invalid)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_options"}
    assert "overlap" in result["description_placeholders"]["error"]


async def test_options_show_readonly_token_rotate_and_reload(hass, configured):
    entry, _ = configured
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"]["token"] == entry.data["token"]
    assert result["description_placeholders"]["image_path"].endswith("/image.png")
    old_token = entry.data["token"]
    with patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock) as reload:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {**DEFAULT_OPTIONS, "regenerate_token": True},
        )
        await hass.async_block_till_done()
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert entry.data["token"] != old_token
        reload.assert_awaited_once_with(entry.entry_id)
        assert not entry.update_listeners


async def test_options_reject_schedule_without_changing_token(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={"token": "test-only"}, options=DEFAULT_OPTIONS)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**DEFAULT_OPTIONS, "schedule": "broken", "regenerate_token": True},
    )
    assert result["errors"] == {"base": "invalid_options"}
    assert entry.data["token"] == "test-only"


async def test_stale_humidity_option_is_dropped_after_usable_options_flow(hass):
    legacy_options = {
        **DEFAULT_OPTIONS,
        "outdoor_humidity_entity": "sensor.old_humidity",
        "token_generation": 7,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"token": "test-only"},
        options=legacy_options,
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert "outdoor_humidity_entity" not in result["data_schema"].schema

    invalid = {**DEFAULT_OPTIONS, "schedule": "broken"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], invalid)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_options"}
    assert "outdoor_humidity_entity" not in result["data_schema"].schema

    with patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock) as reload:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {**DEFAULT_OPTIONS, "default_interval": 45, "regenerate_token": False},
        )
        await hass.async_block_till_done()
        reload.assert_awaited_once_with(entry.entry_id)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "outdoor_humidity_entity" not in result["data"]
    assert result["data"]["token_generation"] == 7
    assert result["data"]["schedule"] == DEFAULT_OPTIONS["schedule"]
    assert result["data"]["default_interval"] == 45
    assert entry.options == result["data"]
    assert entry.data["token"] == "test-only"
