"""One atomic persisted check-in record and its silence deadline."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DEFAULT_OPTIONS, DOMAIN
from .schedule import next_wake, parse_schedule

if TYPE_CHECKING:
    from . import KindleDashConfigEntry


class KindleDashRuntime:
    """Shared monitoring state; a Store avoids restore ordering between entities."""

    def __init__(self, hass: HomeAssistant, entry: KindleDashConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.options: dict[str, Any] = {**DEFAULT_OPTIONS, **entry.options}
        self.periods = parse_schedule(self.options["schedule"], self.options["default_interval"])
        self.store: Store[dict[str, Any]] = Store(
            hass,
            1,
            f"{DOMAIN}.{entry.entry_id}",
            private=True,
            atomic_writes=True,
            serialize_in_event_loop=False,
        )
        self.battery: int | None = None
        self.charging: bool | None = None
        self.last_seen: datetime | None = None
        self.next_expected: datetime | None = None
        self.problem = False
        self.requests = 0
        self.lock = asyncio.Lock()
        self.listeners: set[Callable[[], None]] = set()
        self.cancel_deadline: Callable[[], None] | None = None

    async def async_load(self) -> None:
        """Restore before adding entities, including an already overdue deadline."""
        if data := await self.store.async_load():
            battery = data.get("battery")
            if isinstance(battery, int) and not isinstance(battery, bool) and 0 <= battery <= 100:
                self.battery = battery
            if isinstance(data.get("charging"), bool):
                self.charging = data["charging"]
            for key in ("last_seen", "next_expected"):
                if isinstance(value := data.get(key), str):
                    parsed = dt_util.parse_datetime(value)
                    if parsed is not None and parsed.tzinfo is not None:
                        setattr(self, key, dt_util.as_utc(parsed))
        self.async_schedule_deadline()

    def snapshot(self) -> dict[str, Any]:
        """Return an independent, thread-safe storage snapshot (no token)."""
        return {
            "battery": self.battery,
            "charging": self.charging,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "next_expected": self.next_expected.isoformat() if self.next_expected else None,
        }

    def wake_at(self, now: datetime) -> datetime:
        """Choose the next wake on the configured local wall-time grid."""
        local = now.astimezone(dt_util.get_time_zone(self.hass.config.time_zone))
        return next_wake(local, self.periods, int(self.options["offset_seconds"]))

    async def async_check_in(
        self,
        now: datetime,
        battery: int | None,
        charging: bool | None,
        sleep_seconds: int,
    ) -> None:
        """Commit the record together, then re-arm the exact silence deadline."""
        if battery is not None:
            self.battery = battery
        if charging is not None:
            self.charging = charging
        self.last_seen = dt_util.as_utc(now)
        self.next_expected = self.last_seen + timedelta(seconds=sleep_seconds)
        self.async_schedule_deadline()
        self.async_notify()
        await self.store.async_save(self.snapshot())

    @callback
    def async_notify(self) -> None:
        """Push changes without polling."""
        for listener in tuple(self.listeners):
            listener()

    @callback
    def async_schedule_deadline(self) -> None:
        """Cancel the previous timer, restore overdue state or arm the next timer."""
        if self.cancel_deadline is not None:
            self.cancel_deadline()
            self.cancel_deadline = None
        self.problem = False
        if self.last_seen is None or self.next_expected is None:
            return
        deadline = self.next_expected + timedelta(minutes=self.options["grace_minutes"])
        if dt_util.utcnow() >= deadline:
            self.problem = True
        else:
            self.cancel_deadline = async_track_point_in_utc_time(
                self.hass,
                self._async_overdue,
                deadline,
            )

    @callback
    def _async_overdue(self, now: datetime) -> None:
        """The Kindle can stay silent forever; no polling/check-in is required."""
        self.cancel_deadline = None
        self.problem = True
        self.async_notify()

    @callback
    def async_close(self) -> None:
        """Cancel all entry-owned callbacks."""
        if self.cancel_deadline is not None:
            self.cancel_deadline()
            self.cancel_deadline = None
        self.listeners.clear()
