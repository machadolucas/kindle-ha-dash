"""Charging and exactly scheduled silence detection."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import KindleDashConfigEntry
from .entity import KindleDashEntity


@dataclass(frozen=True, kw_only=True)
class KindleBinaryDescription(BinarySensorEntityDescription):
    """A boolean field of the shared runtime."""


SENSORS = (
    KindleBinaryDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
    KindleBinaryDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KindleDashConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add both push entities."""
    async_add_entities(KindleBinarySensor(entry, description) for description in SENSORS)


class KindleBinarySensor(KindleDashEntity, BinarySensorEntity, RestoreEntity):
    """Monitoring booleans derived from the atomically restored check-in record."""

    @property
    def is_on(self) -> bool | None:
        """Charging is unknown until reported; problem is off before first check-in."""
        return getattr(self.runtime, self.entity_description.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Give useful diagnostic context at the last state change."""
        if self.entity_description.key != "problem":
            return None
        expected = self.runtime.next_expected
        overdue = max(0, (dt_util.utcnow() - expected).total_seconds() / 60) if expected else 0
        return {"overdue_minutes": round(overdue), "last_battery": self.runtime.battery}
