"""Immutable renderer contract; deliberately independent of Home Assistant."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Forecast:
    time: datetime
    condition: str = "unknown"
    temperature: float | None = None
    low: float | None = None
    precipitation: float = 0


@dataclass(frozen=True)
class Weather:
    condition: str = "unknown"
    temperature: float | None = None
    humidity: float | None = None
    wind_speed: float | None = None
    wind_unit: str = "m/s"
    wind_bearing: float | None = None
    indoor_temperature: float | None = None
    hourly: tuple[Forecast, ...] = ()
    daily: tuple[Forecast, ...] = ()


@dataclass(frozen=True)
class PriceSlot:
    start: datetime
    end: datetime
    buy: float  # EUR/kWh, convert only for presentation
    forecast: bool = False
    p10: float | None = None
    p90: float | None = None


@dataclass(frozen=True)
class Prices:
    slots: tuple[PriceSlot, ...] = ()
    tomorrow_available: bool = False


@dataclass(frozen=True)
class DishwasherPeriod:
    start: datetime
    end: datetime
    source: str = "unknown"
    avg_cost: float | None = None  # EUR/kWh


@dataclass(frozen=True)
class Dishwasher:
    periods: tuple[DishwasherPeriod, ...] = ()
    next_start: datetime | None = None
    running: bool = False
    enabled: bool = True
    status: str = "unknown"
    target_minutes: float | None = None
    remaining_minutes: float | None = None
    window_start: str | None = None
    window_end: str | None = None


@dataclass(frozen=True)
class Meta:
    battery: int | None = None
    last_seen: datetime | None = None
    time_zone: str = "Europe/Helsinki"


@dataclass(frozen=True)
class DashboardData:
    weather: Weather = Weather()
    prices: Prices = Prices()
    dishwasher: Dishwasher = Dishwasher()
    meta: Meta = Meta()
