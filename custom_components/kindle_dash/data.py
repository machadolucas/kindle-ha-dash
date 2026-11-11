"""Convert serialized Home Assistant values to an immutable, HA-free contract."""

from dataclasses import replace
from datetime import datetime, timedelta
from math import isfinite
from typing import Any

from .const import DEFAULT_OPTIONS
from .models import (
    DashboardData,
    Dishwasher,
    DishwasherPeriod,
    Forecast,
    Meta,
    Prices,
    PriceSlot,
    Weather,
)

_UNAVAILABLE = {"unknown", "unavailable", "none", ""}


def number(value: Any) -> float | None:
    """Accept finite numeric strings without manufacturing zero for missing data."""
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError):
        return None


def timestamp(value: Any) -> datetime | None:
    """Require an explicit offset; ambiguous local timestamps are not trustworthy."""
    if isinstance(value, datetime):
        return value if value.tzinfo and value.utcoffset() is not None else None
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo and result.utcoffset() is not None else None
    except ValueError:
        return None


def _mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> list:
    return value if isinstance(value, list) else []


def _forecasts(response: dict | None, entity: str) -> tuple[Forecast, ...]:
    forecasts = []
    for raw in _rows(_mapping(_mapping(response).get(entity)).get("forecast")):
        row = _mapping(raw)
        time = timestamp(row.get("datetime"))
        if time:
            forecasts.append(
                Forecast(
                    time=time,
                    condition=str(row.get("condition") or "unknown"),
                    temperature=number(row.get("temperature")),
                    low=number(row.get("templow")),
                    precipitation=number(row.get("precipitation")) or 0,
                )
            )
    return tuple(sorted(forecasts, key=lambda entry: entry.time))


def _price(raw: Any, *, forecast: bool = False) -> PriceSlot | None:
    row = _mapping(raw)
    start, end, buy = timestamp(row.get("start")), timestamp(row.get("end")), number(row.get("buy"))
    if start is None or end is None or buy is None or end.timestamp() <= start.timestamp():
        return None
    p10, p90 = number(row.get("p10")), number(row.get("p90"))
    if p10 is not None and p90 is not None and p10 > p90:
        p10, p90 = p90, p10
    return PriceSlot(start, end, buy, forecast, p10, p90)


def _resolved_prices(slots: tuple[PriceSlot, ...]) -> tuple[PriceSlot, ...]:
    """Deduplicate instants and retain forecasts only outside official intervals."""
    official = {slot.start.timestamp(): slot for slot in slots if not slot.forecast}
    forecasts = {slot.start.timestamp(): slot for slot in slots if slot.forecast}
    result = list(official.values())
    for slot in forecasts.values():
        pieces = [(slot.start.timestamp(), slot.end.timestamp())]
        for known in official.values():
            left, right = known.start.timestamp(), known.end.timestamp()
            remaining = []
            for start, end in pieces:
                if right <= start or left >= end:
                    remaining.append((start, end))
                else:
                    if start < left:
                        remaining.append((start, left))
                    if right < end:
                        remaining.append((right, end))
            pieces = remaining
            if not pieces:
                break
        result.extend(
            replace(
                slot,
                start=datetime.fromtimestamp(start, slot.start.tzinfo),
                end=datetime.fromtimestamp(end, slot.start.tzinfo),
            )
            for start, end in pieces
        )
    return tuple(sorted(result, key=lambda slot: slot.start.timestamp()))


def hourly_prices(
    slots: tuple[PriceSlot, ...], start: datetime, end: datetime
) -> tuple[PriceSlot, ...]:
    """Average present source prices into clipped local clock hours, in EUR/kWh.

    Missing hours remain absent. Timestamp iteration preserves both occurrences
    of a repeated autumn hour and skips the nonexistent spring hour.
    """
    start_at, end_at = start.timestamp(), end.timestamp()
    hour_at = start.replace(minute=0, second=0, microsecond=0).timestamp()
    resolved = _resolved_prices(slots)
    result = []
    while hour_at < end_at:
        left, right = max(hour_at, start_at), min(hour_at + 3600, end_at)
        contributors = [
            slot
            for slot in resolved
            if slot.start.timestamp() < right and slot.end.timestamp() > left
        ]
        if contributors and left < right:
            result.append(
                PriceSlot(
                    datetime.fromtimestamp(left, start.tzinfo),
                    datetime.fromtimestamp(right, start.tzinfo),
                    sum(slot.buy for slot in contributors) / len(contributors),
                    any(slot.forecast for slot in contributors),
                )
            )
        hour_at += 3600
    return tuple(result)


def next_hours_prices(slots: tuple[PriceSlot, ...], now: datetime) -> tuple[PriceSlot, ...]:
    """Return 24 elapsed quarter-hour slots beginning at the current quarter."""
    start_at = (now.timestamp() // 900) * 900
    resolved = _resolved_prices(slots)
    result = []
    for index in range(24):
        left, right = start_at + index * 900, start_at + (index + 1) * 900
        contributors = []
        for slot in resolved:
            overlap = min(right, slot.end.timestamp()) - max(left, slot.start.timestamp())
            if overlap > 0:
                contributors.append((slot, overlap))
        if contributors:
            total = sum(overlap for _, overlap in contributors)
            result.append(
                PriceSlot(
                    datetime.fromtimestamp(left, now.tzinfo),
                    datetime.fromtimestamp(right, now.tzinfo),
                    sum(slot.buy * overlap for slot, overlap in contributors) / total,
                    any(slot.forecast for slot, _ in contributors),
                )
            )
    return tuple(result)


def six_day_prices(slots: tuple[PriceSlot, ...], now: datetime) -> tuple[PriceSlot, ...]:
    """Return today's civil midnight through midnight six local dates later."""
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return hourly_prices(slots, start, start + timedelta(days=6))


def parse_dashboard(
    states: dict,
    hourly: dict | None = None,
    daily: dict | None = None,
    *,
    options: dict | None = None,
    meta: Meta | None = None,
) -> DashboardData:
    """Parse fixture/API dictionaries, skipping malformed rows and unavailable entities.

    Official market arrays overlap civil days. Merge them by instant first, with
    newer arrays winning duplicate starts. Forecasts fill gaps and extend the
    official horizon; they never replace or overlap an official interval.
    """
    opts = {**DEFAULT_OPTIONS, **(options or {})}

    def entity(key: str) -> dict:
        result = _mapping(states.get(opts[key]))
        return {} if str(result.get("state", "")).lower() in _UNAVAILABLE else result

    def attrs(key: str) -> dict:
        return _mapping(entity(key).get("attributes"))

    weather_attrs = attrs("weather_entity")
    temp = number(entity("outdoor_temperature_entity").get("state"))
    weather = Weather(
        condition=str(entity("weather_entity").get("state") or "unknown"),
        temperature=temp if temp is not None else number(weather_attrs.get("temperature")),
        wind_speed=number(weather_attrs.get("wind_speed")),
        wind_unit=str(weather_attrs.get("wind_speed_unit") or "m/s"),
        wind_bearing=number(weather_attrs.get("wind_bearing")),
        indoor_temperature=number(entity("indoor_temperature_entity").get("state")),
        hourly=_forecasts(hourly, opts["weather_entity"]),
        daily=_forecasts(daily, opts["weather_entity"]),
    )
    price_attrs = attrs("prices_entity")
    official: dict[float, PriceSlot] = {}
    for key in ("data_yesterday", "data_today", "data_tomorrow"):
        for raw in _rows(price_attrs.get(key)):
            slot = _price(raw)
            if slot:
                official[slot.start.timestamp()] = slot
    slots = list(official.values())
    forecast_attrs = attrs("price_forecast_entity")
    if not forecast_attrs.get("stale", False):
        for raw in _rows(forecast_attrs.get("data_today")):
            slot = _price(raw, forecast=True)
            if slot:
                slots.append(slot)
    availability = entity("tomorrow_available_entity").get("state") == "on" or bool(
        _rows(price_attrs.get("data_tomorrow"))
    )
    prices = Prices(_resolved_prices(tuple(slots)), availability)
    schedule = entity("dishwasher_entity")
    dish_attrs = attrs("dishwasher_entity")
    running_entity = entity("dishwasher_running_entity")
    running_attrs = attrs("dishwasher_running_entity")
    periods = []
    for raw in _rows(dish_attrs.get("periods")):
        row = _mapping(raw)
        start, end = timestamp(row.get("start")), timestamp(row.get("end"))
        if start and end and end > start:
            periods.append(
                DishwasherPeriod(
                    start,
                    end,
                    str(row.get("source") or "unknown"),
                    number(row.get("avg_cost")),
                )
            )
    # Unknown scheduling state invalidates operational data, while static window
    # metadata remains useful. Unavailable entities contribute no metadata.
    raw_schedule = _mapping(states.get(opts["dishwasher_entity"]))
    static_attrs = (
        _mapping(raw_schedule.get("attributes"))
        if raw_schedule.get("state") == "unknown"
        else dish_attrs
    )
    rationale = _mapping(static_attrs.get("rationale"))
    config = _mapping(static_attrs.get("config"))

    def window(key: str, fallback: str) -> str | None:
        value = rationale.get(key)
        if not isinstance(value, str):
            value = config.get(fallback)
        return value if isinstance(value, str) else None

    dishwasher = Dishwasher(
        periods=tuple(sorted(periods, key=lambda period: period.start)),
        next_start=timestamp(running_attrs.get("next_start")) or timestamp(schedule.get("state")),
        running=running_entity.get("state") == "on" or dish_attrs.get("running") is True,
        enabled=dish_attrs.get("enabled") is not False,
        status=str(dish_attrs.get("status") or "unknown"),
        target_minutes=number(dish_attrs.get("target_minutes")),
        remaining_minutes=number(dish_attrs.get("remaining_minutes")),
        window_start=window("window_start", "earliest"),
        window_end=window("window_end", "deadline"),
    )
    return DashboardData(weather, prices, dishwasher, meta or Meta())
