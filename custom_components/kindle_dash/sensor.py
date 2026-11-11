"""Persistent Kindle monitoring sensors."""

from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KindleDashConfigEntry
from .entity import KindleDashEntity


@dataclass(frozen=True, kw_only=True)
class KindleSensorDescription(SensorEntityDescription):
    """A field of the atomic check-in record."""


SENSORS = (
    KindleSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    KindleSensorDescription(
        key="last_seen",
        translation_key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    KindleSensorDescription(
        key="next_expected",
        translation_key="next_expected",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KindleDashConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Expose the already restored monitoring record."""
    async_add_entities(KindleSensor(entry, description) for description in SENSORS)


class KindleSensor(KindleDashEntity, RestoreSensor):
    """Store is authoritative so entity restore ordering cannot lose the deadline."""

    @property
    def native_value(self) -> int | datetime | None:
        """Return the native persistent value."""
        return getattr(self.runtime, self.entity_description.key)
