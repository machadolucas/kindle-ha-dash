from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.kindle_dash.schedule import Period, next_wake, parse_schedule


def test_parse_fills_uncovered_time_with_default_interval() -> None:
    assert parse_schedule("08:00-12:00 30", default_interval=45) == (
        Period(0, 480, 45),
        Period(480, 720, 30),
        Period(720, 1440, 45),
    )


@pytest.mark.parametrize("schedule", ["00:00-00:00 60", "00:00-24:00 60"])
def test_parse_accepts_midnight_to_midnight_as_whole_day(schedule: str) -> None:
    assert parse_schedule(schedule) == (Period(0, 1440, 60),)


def test_parse_keeps_wrapped_period_and_fills_its_gap() -> None:
    assert parse_schedule("22:00-06:00 75") == (
        Period(360, 1320, 60),
        Period(1320, 360, 75),
    )


@pytest.mark.parametrize(
    ("schedule", "message"),
    [
        ("08:00 to 12:00 30", "expected"),
        ("08:00-12:00", "interval_minutes"),
        ("25:00-12:00 30", "clock time"),
        ("08:00-12:00 4", "interval"),
        ("08:00-12:00 721", "interval"),
        ("08:00-08:00 30", "same time"),
        ("08:00-12:00 30\n11:00-13:00 30", "overlap"),
        ("22:00-06:00 60\n05:00-08:00 60", "overlap"),
    ],
)
def test_parse_rejects_invalid_schedule(schedule: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_schedule(schedule)


def test_next_wake_requires_strict_minimum_gap_and_applies_offset() -> None:
    periods = (Period(0, 1440, 60),)
    now = datetime(2026, 1, 1, 8, 0, tzinfo=ZoneInfo("Europe/Helsinki"))
    # 08:02 is exactly the minimum gap, so the next candidate is 09:01.
    assert next_wake(now, periods, offset_seconds=60, min_gap=120) == datetime(
        2026, 1, 1, 9, 1, tzinfo=ZoneInfo("Europe/Helsinki")
    )


def test_wrapped_period_grid_remains_anchored_across_midnight() -> None:
    periods = parse_schedule("22:00-06:00 75")
    now = datetime(2026, 1, 2, 0, 10, tzinfo=ZoneInfo("Europe/Helsinki"))
    wake = next_wake(now, periods, offset_seconds=0, min_gap=0)
    assert wake == datetime(2026, 1, 2, 0, 30, tzinfo=ZoneInfo("Europe/Helsinki"))


def test_offset_past_period_end_uses_next_period_start() -> None:
    periods = parse_schedule("08:00-09:00 30\n09:00-00:00 60")
    now = datetime(2026, 1, 1, 8, 46, tzinfo=ZoneInfo("Europe/Helsinki"))
    wake = next_wake(now, periods, offset_seconds=45 * 60, min_gap=0)
    assert wake == datetime(2026, 1, 1, 9, 45, tzinfo=ZoneInfo("Europe/Helsinki"))


def test_spring_gap_skips_nonexistent_wall_times() -> None:
    periods = (Period(120, 300, 30),)
    now = datetime(2026, 3, 29, 2, 45, tzinfo=ZoneInfo("Europe/Helsinki"))
    wake = next_wake(now, periods, offset_seconds=0, min_gap=120)
    assert wake == datetime(2026, 3, 29, 4, 0, tzinfo=ZoneInfo("Europe/Helsinki"))


def test_autumn_fold_returns_both_repeated_hour_occurrences_in_epoch_order() -> None:
    zone = ZoneInfo("Europe/Helsinki")
    periods = (Period(180, 240, 30),)
    before_first = datetime(2026, 10, 25, 2, 50, tzinfo=zone)
    first = next_wake(before_first, periods, offset_seconds=0, min_gap=0)
    assert first == datetime(2026, 10, 25, 3, 0, tzinfo=zone, fold=0)

    # 03:40 in the first fold is followed in absolute time by 03:00 in the
    # second fold, even though its wall-clock label sorts earlier.
    late_first_fold = datetime(2026, 10, 25, 3, 40, tzinfo=zone, fold=0)
    second = next_wake(late_first_fold, periods, offset_seconds=0, min_gap=0)
    assert second == datetime(2026, 10, 25, 3, 0, tzinfo=zone, fold=1)
    assert first.astimezone(UTC) < second.astimezone(UTC)
