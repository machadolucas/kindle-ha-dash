"""Kindle dashboard: UI configuration and a token-protected pull interface."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .runtime import KindleDashRuntime

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
type KindleDashConfigEntry = ConfigEntry[KindleDashRuntime]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register routes once; views resolve only currently loaded runtime data."""
    from .http import ImageView, StatusView, async_redact_http_logs

    async_redact_http_logs()
    hass.http.register_view(ImageView(hass))
    hass.http.register_view(StatusView(hass))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: KindleDashConfigEntry) -> None:
    """Load a single physical Kindle and its monitoring entities."""
    runtime = entry.runtime_data = KindleDashRuntime(hass, entry)
    await runtime.async_load()
    entry.async_on_unload(runtime.async_close)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: KindleDashConfigEntry) -> None:
    """Unload platforms before HA runs registered cleanup callbacks."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        raise ConfigEntryError(translation_domain=DOMAIN, translation_key="unload_failed")


async def async_remove_entry(hass: HomeAssistant, entry: KindleDashConfigEntry) -> None:
    """Delete only this entry's monitoring record when explicitly removed."""
    from homeassistant.helpers.storage import Store

    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()
