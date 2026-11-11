"""Silence detection and persisted-record restoration with actual HA entities."""

from datetime import timedelta

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.kindle_dash.const import DOMAIN
from custom_components.kindle_dash.diagnostics import async_get_config_entry_diagnostics


def entity_id(hass, entry, platform, key):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")


async def test_entity_metadata_and_initial_values(hass, configured):
    entry, _ = configured
    battery = hass.states.get(entity_id(hass, entry, "sensor", "battery"))
    assert battery.state == "unknown"
    assert battery.attributes["device_class"] == "battery"
    assert battery.attributes["state_class"] == "measurement"
    assert battery.attributes["unit_of_measurement"] == "%"
    assert hass.states.get(entity_id(hass, entry, "sensor", "last_seen")).state == "unknown"
    assert hass.states.get(entity_id(hass, entry, "binary_sensor", "problem")).state == "off"
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 1
    assert devices[0].name == "Kindle dashboard" and devices[0].entry_type is None
    assert len(er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)) == 5


async def test_problem_trips_at_deadline_reschedules_and_restores(hass, configured, freezer):
    entry, client = configured
    await client.get("/api/kindle_dash/test-only-token/image.png?battery=41&charging=1")
    runtime = entry.runtime_data
    first_deadline = runtime.next_expected + timedelta(minutes=120)
    problem_id = entity_id(hass, entry, "binary_sensor", "problem")
    freezer.move_to(first_deadline - timedelta(seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get(problem_id).state == "off"
    freezer.move_to(first_deadline)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get(problem_id).state == "on"
    assert hass.states.get(problem_id).attributes["last_battery"] == 41
    assert hass.states.get(problem_id).attributes["overdue_minutes"] == 120
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert runtime.cancel_deadline is None
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data is not runtime
    assert entry.runtime_data.battery == 41 and entry.runtime_data.charging is True
    assert hass.states.get(problem_id).state == "on"
    await client.get("/api/kindle_dash/test-only-token/image.png?battery=40&charging=0")
    new_deadline = entry.runtime_data.next_expected + timedelta(minutes=120)
    assert new_deadline > first_deadline
    assert hass.states.get(problem_id).state == "off"
    assert hass.states.get(entity_id(hass, entry, "sensor", "battery")).state == "40"
    assert hass.states.get(entity_id(hass, entry, "binary_sensor", "charging")).state == "off"


async def test_earlier_deadline_cancelled_and_future_restored(hass, configured, freezer):
    entry, client = configured
    await client.get("/api/kindle_dash/test-only-token/image.png?battery=70")
    old_deadline = entry.runtime_data.next_expected + timedelta(minutes=120)
    freezer.tick(timedelta(hours=1))
    await client.get("/api/kindle_dash/test-only-token/image.png?battery=69")
    expected = entry.runtime_data.next_expected
    assert await hass.config_entries.async_reload(entry.entry_id)
    assert entry.runtime_data.next_expected == expected
    assert entry.runtime_data.cancel_deadline is not None
    freezer.move_to(old_deadline)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert entry.runtime_data.problem is False


async def test_entity_rename_retains_subscription(hass, configured):
    entry, client = configured
    registry = er.async_get(hass)
    old = entity_id(hass, entry, "sensor", "battery")
    registry.async_update_entity(old, new_entity_id="sensor.kindle_renamed_battery")
    await hass.async_block_till_done()
    await client.get("/api/kindle_dash/test-only-token/image.png?battery=65")
    assert hass.states.get("sensor.kindle_renamed_battery").state == "65"
    assert len(entry.runtime_data.listeners) == 5


async def test_diagnostics_redact_token(hass, configured):
    entry, _ = configured
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["entry"]["data"]["token"] == "**REDACTED**"
    assert entry.data["token"] not in str(diagnostics)


async def test_cold_start_restores_checkin_and_overdue_problem(hass, hass_storage, freezer):
    """Start with disk storage only, without a previous runtime or entity instance."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.kindle_dash.const import DEFAULT_OPTIONS

    freezer.move_to("2026-11-11T12:31:00+00:00")
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="cold-start-entry",
        data={"token": "test-only-cold-start"},
        options=DEFAULT_OPTIONS,
    )
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {
            "battery": 19,
            "charging": False,
            "last_seen": "2026-11-10T18:00:00+00:00",
            "next_expected": "2026-11-10T19:01:00+00:00",
        },
    }
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(hass, entry, "sensor", "battery")).state == "19"
    assert hass.states.get(entity_id(hass, entry, "sensor", "last_seen")).state == (
        "2026-11-10T18:00:00+00:00"
    )
    assert hass.states.get(entity_id(hass, entry, "binary_sensor", "problem")).state == "on"
    assert entry.runtime_data.cancel_deadline is None
