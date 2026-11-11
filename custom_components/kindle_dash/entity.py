"""Common physical Kindle identity and push subscriptions."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription

from . import KindleDashConfigEntry
from .const import DOMAIN


class KindleDashEntity(Entity):
    """One Kindle physical device, not a device registry SERVICE entry."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: KindleDashConfigEntry, description: EntityDescription) -> None:
        self.runtime = entry.runtime_data
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        # entry_type=None denotes hardware; SERVICE would misclassify the Kindle.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Kindle dashboard",
            manufacturer="Amazon",
            model="Kindle Paperwhite 3",
            entry_type=None,
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe; Store was restored atomically before platforms were added."""
        await super().async_added_to_hass()
        self.runtime.listeners.add(self.async_write_ha_state)
        self.async_on_remove(lambda: self.runtime.listeners.discard(self.async_write_ha_state))

    @callback
    def async_entity_id_changed(self, old_entity_id: str) -> None:
        """Opt into HA 2026.11 in-place renames; subscriptions use bound methods."""
        super().async_entity_id_changed(old_entity_id)
