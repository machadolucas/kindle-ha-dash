"""Parser regressions for civil-day boundaries, precedence and missing sensors."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.kindle_dash.data import (
    hourly_prices,
    next_hours_prices,
    parse_dashboard,
    six_day_prices,
)
from custom_components.kindle_dash.models import Meta, PriceSlot

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


def price_slots(start: datetime, count: int, *, forecast: bool = False) -> tuple[PriceSlot, ...]:
    """Create consecutive quarters by instant, including DST folds and gaps."""
    return tuple(
        PriceSlot(
            datetime.fromtimestamp(start.timestamp() + index * 900, start.tzinfo),
            datetime.fromtimestamp(start.timestamp() + (index + 1) * 900, start.tzinfo),
            (index + 1) / 100,
            forecast,
        )
        for index in range(count)
    )


def test_next_hours_averages_only_current_and_future_quarters() -> None:
    start = datetime.fromisoformat("2026-11-11T14:00:00+02:00")
    slots = price_slots(start, 28)
    result = next_hours_prices(slots, start.replace(minute=31))
    assert len(result) == 7
    assert result[0].start == start.replace(minute=30)
    assert result[0].end == start.replace(hour=15)
    assert result[0].buy == pytest.approx((0.03 + 0.04) / 2)
    assert result[-1].end == start.replace(hour=20, minute=30)
    assert result[-1].buy == pytest.approx((0.25 + 0.26) / 2)
    assert len(next_hours_prices(slots, start)) == 6


def test_hourly_prices_preserves_missing_hours_and_averages_available_quarters() -> None:
    start = datetime.fromisoformat("2026-11-11T14:00:00+02:00")
    slots = price_slots(start, 12)
    selected = (slots[0], slots[3], slots[8])
    result = hourly_prices(selected, start, start.replace(hour=17))
    assert [slot.start.hour for slot in result] == [14, 16]
    assert [slot.buy for slot in result] == pytest.approx([0.025, 0.09])
    assert hourly_prices(selected, start, start) == ()


def test_mixed_hour_forecast_and_duplicate_official_precedence() -> None:
    start = datetime.fromisoformat("2026-11-11T14:00:00+02:00")
    official = price_slots(start, 4)
    forecast = price_slots(start, 4, forecast=True)
    mixed = hourly_prices((official[0], *forecast), start, official[-1].end)
    assert mixed[0].forecast
    duplicates = tuple(PriceSlot(s.start, s.end, 9, True) for s in official)
    resolved = hourly_prices((*official, *duplicates), start, official[-1].end)
    assert not resolved[0].forecast
    assert resolved[0].buy == pytest.approx(0.025)


def test_parser_forecast_fills_hole_before_last_official_end() -> None:
    states = load("states.json")
    attrs = states["sensor.nordpool_fi_day_ahead"]["attributes"]
    rows = attrs["data_today"][:3]
    attrs.update(data_yesterday=[], data_today=[rows[0], rows[2]], data_tomorrow=[])
    states["sensor.lvv_price_forecast"]["attributes"]["data_today"] = [
        {**row, "buy": 0.5} for row in rows
    ]
    slots = parse_dashboard(states).prices.slots
    assert len(slots) == 3
    assert [slot.forecast for slot in slots] == [False, True, False]
    assert slots[1].buy == 0.5


def test_six_days_includes_prior_array_midnight_and_clips_last_day() -> None:
    data = parse_dashboard(load("states.json"))
    now = datetime(2026, 11, 11, 14, 31, tzinfo=ZoneInfo("Europe/Helsinki"))
    result = six_day_prices(data.prices.slots, now)
    first = result[0]
    assert first.start == now.replace(hour=0, minute=0)
    assert first.end == now.replace(hour=1, minute=0)
    quarters = [s.buy for s in data.prices.slots if first.start <= s.start < first.end]
    assert len(quarters) == 4
    assert first.buy == pytest.approx(sum(quarters) / 4)
    assert all(now.date() <= s.start.date() < now.date() + timedelta(days=6) for s in result)
    assert result[-1].end <= now.replace(hour=0, minute=0) + timedelta(days=6)


@pytest.mark.parametrize(("day", "hours"), [("2026-03-29", 143), ("2026-10-25", 145)])
def test_six_days_uses_civil_days_across_dst(day: str, hours: int) -> None:
    zone = ZoneInfo("Europe/Helsinki")
    start = datetime.fromisoformat(day).replace(tzinfo=zone)
    result = six_day_prices(price_slots(start, hours * 4 + 4), start.replace(hour=12))
    assert len(result) == hours
    assert result[0].start == start
    assert result[-1].end == start + timedelta(days=6)
    assert all(s.end.timestamp() - s.start.timestamp() == 3600 for s in result)
    first_day_hours = [s.start.hour for s in result if s.start.date() == start.date()]
    assert first_day_hours.count(3) == (0 if hours == 143 else 2)
    assert all(s.buy == pytest.approx((4 * i + 2.5) / 100) for i, s in enumerate(result))


def test_overlapping_forecast_is_clipped_around_official_interval() -> None:
    start = datetime.fromisoformat("2026-11-11T14:00:00+02:00")
    official = PriceSlot(start.replace(minute=15), start.replace(minute=45), 0.1)
    forecast = PriceSlot(start, start.replace(hour=15), 0.4, True)
    # Within official coverage, overlapping forecast data cannot change the
    # value or classification even when the source interval starts earlier.
    result = hourly_prices((forecast, official), official.start, official.end)
    assert len(result) == 1
    assert result[0].buy == 0.1
    assert not result[0].forecast
    result = hourly_prices((forecast, official), start, forecast.end)
    assert result[0].forecast
    assert result[0].buy == pytest.approx((0.4 + 0.1 + 0.4) / 3)
