"""Parser regressions for civil-day boundaries, precedence and missing sensors."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.kindle_dash.data import parse_dashboard
from custom_components.kindle_dash.models import Meta

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_real_fixture_merge_keeps_midnight_and_preserves_eur_units() -> None:
    data = parse_dashboard(
        load("states.json"), load("forecast_hourly.json"), load("forecast_daily.json")
    )
    zone = ZoneInfo("Europe/Helsinki")
    today = [
        slot
        for slot in data.prices.slots
        if slot.start.astimezone(zone).date().isoformat() == "2026-11-11"
    ]
    assert len(today) == 96
    assert today[0].start.hour == 0
    assert today[0].buy == 0.19391
    assert data.weather.temperature == 4.16
    assert len(data.weather.hourly) == 48
    assert len(data.weather.daily) == 6
    assert data.dishwasher.periods[0].avg_cost == 0.10392
    official = [slot for slot in data.prices.slots if not slot.forecast]
    forecast = [slot for slot in data.prices.slots if slot.forecast]
    assert min(slot.start for slot in forecast) >= max(slot.end for slot in official)


def test_official_duplicates_win_and_forecasts_never_overlap() -> None:
    states = load("states.json")
    official = states["sensor.nordpool_fi_day_ahead"]["attributes"]
    old = official["data_today"][0]
    official["data_tomorrow"] = [{**old, "buy": 0.01}]
    states["sensor.lvv_price_forecast"]["attributes"]["data_today"].insert(
        0,
        {**old, "buy": -1},
    )
    data = parse_dashboard(states)
    slots = [slot for slot in data.prices.slots if slot.start.isoformat() == old["start"]]
    assert len(slots) == 1
    assert slots[0].buy == 0.01
    assert not slots[0].forecast


@pytest.mark.parametrize("value", ["unknown", "unavailable", None, {}, []])
def test_invalid_state_values_do_not_crash(value: object) -> None:
    states = load("states.json")
    for entity in states.values():
        entity["state"] = value
        entity["attributes"] = None
    data = parse_dashboard(states)
    assert data.weather.temperature is None
    assert data.prices.slots == ()
    assert data.dishwasher.status == "unknown"


def test_bad_rows_nan_and_naive_timestamps_are_ignored() -> None:
    states = load("states.json")
    attrs = states["sensor.nordpool_fi_day_ahead"]["attributes"]
    attrs["data_yesterday"] = [
        None,
        42,
        {"buy": "NaN"},
        {"start": "2026-11-11", "end": "2026-11-12", "buy": 0.2},
    ]
    attrs["data_today"], attrs["data_tomorrow"] = None, []
    states["sensor.lvv_price_forecast"]["state"] = "unavailable"
    states["sensor.outdoor_sensor_temperature"]["state"] = "Infinity"
    data = parse_dashboard(states, {"weather.forecast_home": {"forecast": [None, {}]}})
    assert data.prices.slots == ()
    assert data.weather.temperature == 4.2  # Weather sensor is the measured-value fallback.
    assert data.weather.hourly == ()


def test_options_remap_entities_and_meta_survives() -> None:
    meta = Meta(battery=18, last_seen=datetime.fromisoformat("2026-11-11T12:00:00+02:00"))
    data = parse_dashboard(
        {"sensor.other": {"state": "-4.5"}},
        options={"outdoor_temperature_entity": "sensor.other"},
        meta=meta,
    )
    assert data.weather.temperature == -4.5
    assert data.meta is meta


def test_tomorrow_array_sets_availability_without_binary_sensor() -> None:
    states = load("states.json")
    attrs = states["sensor.nordpool_fi_day_ahead"]["attributes"]
    attrs["data_tomorrow"] = [attrs["data_today"][-1]]
    assert parse_dashboard(states).prices.tomorrow_available


def test_missing_periods_uses_config_window_and_malformed_rationale_is_safe() -> None:
    states = load("states.json")
    attrs = states["sensor.dishwasher_schedule"]["attributes"]
    attrs["periods"] = []
    attrs["rationale"] = {"window_start": [], "window_end": {}}
    data = parse_dashboard(states)
    assert data.dishwasher.window_start == "16:00:00"
    assert data.dishwasher.window_end == "12:00:00"


def test_unknown_schedule_preserves_only_known_window_metadata() -> None:
    states = load("states.json")
    states["sensor.dishwasher_schedule"]["state"] = "unknown"
    states["binary_sensor.dishwasher_running_2"]["state"] = "unknown"
    data = parse_dashboard(states)
    assert data.dishwasher.periods == ()
    assert data.dishwasher.status == "unknown"
    assert data.dishwasher.window_start == "2026-11-11T16:00:00+02:00"
    assert data.dishwasher.window_end == "2026-11-12T12:00:00+02:00"
    states["sensor.dishwasher_schedule"]["state"] = "unavailable"
    assert parse_dashboard(states).dishwasher.window_start is None
