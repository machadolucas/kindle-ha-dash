"""Pure Python helpers for parsing and evaluating refresh schedules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Period:
    """A wall-clock schedule period; end 1440 means midnight at day end."""

    start_minutes: int
    end_minutes: int
    interval_minutes: int


_LINE = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})\s+(\d+)$")
_DAY_MINUTES = 24 * 60


def _clock_minutes(hour_text: str, minute_text: str, *, is_end: bool) -> int:
    hour = int(hour_text)
    minute = int(minute_text)
    if minute > 59 or hour > 23:
        if is_end and hour == 24 and minute == 0:
            return _DAY_MINUTES
        raise ValueError(f"invalid clock time {hour_text}:{minute_text}")
    if is_end and hour == 0 and minute == 0:
        return _DAY_MINUTES
    return hour * 60 + minute


def parse_schedule(text: str, default_interval: int = 60) -> tuple[Period, ...]:
    """Parse schedule lines and fill any uncovered wall-clock ranges."""
    if not isinstance(default_interval, int) or isinstance(default_interval, bool):
        raise ValueError("default interval must be an integer from 5 to 720 minutes")
    if not 5 <= default_interval <= 720:
        raise ValueError("default interval must be between 5 and 720 minutes")

    periods: list[Period] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _LINE.fullmatch(line)
        if match is None:
            raise ValueError(f"line {line_number}: expected 'HH:MM-HH:MM interval_minutes'")
        start = _clock_minutes(match[1], match[2], is_end=False)
        end = _clock_minutes(match[3], match[4], is_end=True)
        interval = int(match[5]) if match[5] is not None else default_interval
        if not 5 <= interval <= 720:
            raise ValueError(f"line {line_number}: interval must be between 5 and 720 minutes")
        duration = (
            _DAY_MINUTES if start == 0 and end == _DAY_MINUTES else (end - start) % _DAY_MINUTES
        )
        if duration == 0:
            raise ValueError(f"line {line_number}: start and end must not be the same time")
        periods.append(Period(start, end, interval))

    # Expand wrapped periods to a day-based representation for overlap checks and gaps.
    occupied: list[tuple[int, int, Period]] = []
    for period in periods:
        end = period.end_minutes
        if end == _DAY_MINUTES or end > period.start_minutes:
            occupied.append((period.start_minutes, end, period))
        else:
            occupied.append((period.start_minutes, _DAY_MINUTES, period))
            occupied.append((0, end, period))
    occupied.sort(key=lambda item: (item[0], item[1]))

    for previous, current in pairwise(occupied):
        if current[0] < previous[1]:
            raise ValueError("schedule periods overlap")

    filled: list[Period] = periods.copy()
    cursor = 0
    for start, end, _period in occupied:
        if start > cursor:
            filled.append(Period(cursor, start, default_interval))
        cursor = max(cursor, end)
    if cursor < _DAY_MINUTES:
        filled.append(Period(cursor, _DAY_MINUTES, default_interval))

    return tuple(sorted(filled, key=lambda period: period.start_minutes))


def _valid_wall_instants(wall_time: datetime, zone: ZoneInfo) -> tuple[datetime, ...]:
    """Return real instants for a local wall time, including both folds."""
    instants: list[datetime] = []
    for fold in (0, 1):
        candidate = wall_time.replace(tzinfo=zone, fold=fold)
        round_trip = candidate.astimezone(UTC).astimezone(zone)
        if round_trip.replace(tzinfo=None) == wall_time and round_trip.fold == fold:
            instants.append(candidate)
    return tuple(instants)


def next_wake(
    now_local: datetime,
    periods: tuple[Period, ...],
    offset_seconds: int = 60,
    min_gap: int = 120,
) -> datetime:
    """Find the earliest scheduled wake strictly beyond the absolute minimum gap."""
    if now_local.tzinfo is None or now_local.utcoffset() is None:
        raise ValueError("now_local must be timezone-aware")
    if not periods:
        raise ValueError("periods must not be empty")
    zone = now_local.tzinfo
    if not isinstance(zone, ZoneInfo):
        # ZoneInfo is required to identify and validate local DST folds/gaps.
        raise ValueError("now_local must use a ZoneInfo timezone")
    if offset_seconds < 0 or min_gap < 0:
        raise ValueError("offset_seconds and min_gap must be non-negative")

    threshold = now_local.astimezone(UTC) + timedelta(seconds=min_gap)
    local_today = now_local.date()
    candidates: list[datetime] = []

    for day_offset in range(-1, 5):
        schedule_date = local_today + timedelta(days=day_offset)
        for period in periods:
            duration = (period.end_minutes - period.start_minutes) % _DAY_MINUTES
            if duration == 0:
                duration = _DAY_MINUTES
            period_start = datetime.combine(
                schedule_date,
                time(period.start_minutes // 60, period.start_minutes % 60),
            )
            end_absolute_minute = period.start_minutes + duration
            period_end = datetime.combine(
                schedule_date + timedelta(days=end_absolute_minute // _DAY_MINUTES),
                time(
                    (end_absolute_minute % _DAY_MINUTES) // 60,
                    end_absolute_minute % 60,
                ),
            )
            elapsed = 0
            while elapsed < duration:
                absolute_minute = period.start_minutes + elapsed
                wall_date = schedule_date + timedelta(days=absolute_minute // _DAY_MINUTES)
                minute_of_day = absolute_minute % _DAY_MINUTES
                wall_time = datetime.combine(
                    wall_date,
                    time(minute_of_day // 60, minute_of_day % 60),
                )
                for instant in _valid_wall_instants(wall_time, zone):
                    shifted = instant.astimezone(UTC) + timedelta(seconds=offset_seconds)
                    shifted_local = shifted.astimezone(zone)
                    shifted_wall = shifted_local.replace(tzinfo=None)
                    if shifted > threshold and period_start <= shifted_wall < period_end:
                        candidates.append(shifted_local)
                elapsed += period.interval_minutes

    if not candidates:
        raise ValueError("schedule has no valid wake time in the next several days")
    return min(candidates, key=lambda candidate: candidate.astimezone(UTC))
