"""Visual transport, timeline and scenario invariants."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image, ImageDraw

from custom_components.kindle_dash.models import Dishwasher, DishwasherPeriod, PriceSlot
from custom_components.kindle_dash.render import chart_limits, day_bounds, weather_icon
from tools.preview import SCENARIOS, _render, build_scenario

NOW = datetime.fromisoformat("2026-11-11T14:31:00+02:00")
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenarios_produce_deterministic_16_level_portrait_png(scenario: str) -> None:
    data = build_scenario(FIXTURES, NOW, scenario)
    result = _render.render_dashboard(data, now=NOW)
    image = Image.open(BytesIO(result))
    assert image.format == "PNG"
    assert image.size == (1072, 1448)
    assert image.mode == "L"
    assert set(image.tobytes()) <= set(range(0, 256, 17))
    assert result == _render.render_dashboard(data, now=NOW)


@pytest.mark.parametrize(
    ("date", "hours"), [("2026-03-29", 23), ("2026-10-25", 25), ("2026-11-11", 24)]
)
def test_chart_uses_civil_day_duration_across_dst(date: str, hours: int) -> None:
    now = datetime.fromisoformat(date).replace(tzinfo=ZoneInfo("Europe/Helsinki"))
    start, end = day_bounds(now)
    assert (end.timestamp() - start.timestamp()) / 3600 == hours
    assert start.hour == end.hour == 0


def test_chart_scale_includes_negative_prices_but_ignores_uncertainty() -> None:
    slot = PriceSlot(NOW, NOW.replace(hour=14), -0.031, True, -0.15, 0.47)
    assert chart_limits((slot,)) == (-10, 20)
    assert chart_limits(()) == (0, 20)


def test_all_weather_conditions_and_night_variants_have_visible_icons() -> None:
    conditions = (
        "clear-night",
        "cloudy",
        "exceptional",
        "fog",
        "hail",
        "lightning",
        "lightning-rainy",
        "partlycloudy",
        "pouring",
        "rainy",
        "snowy",
        "snowy-rainy",
        "sunny",
        "windy",
        "windy-variant",
        "unknown",
    )
    for condition in conditions:
        for night in (False, True):
            image = Image.new("L", (110, 110), 255)
            weather_icon(ImageDraw.Draw(image), condition, 5, 5, 90, night=night)
            assert image.getextrema() == (0, 255)


def test_naive_clock_is_rejected_and_requested_dimensions_are_honored() -> None:
    data = build_scenario(FIXTURES, NOW, "normal")
    with pytest.raises(ValueError, match="timezone-aware"):
        _render.render_dashboard(data, now=datetime(2026, 1, 1))
    image = Image.open(BytesIO(_render.render_dashboard(data, now=NOW, width=536, height=724)))
    assert image.size == (536, 724)


def test_scenario_generation_never_mutates_fixture_files() -> None:
    before = {path: path.read_bytes() for path in FIXTURES.glob("*.json")}
    for scenario in SCENARIOS:
        build_scenario(FIXTURES, NOW.astimezone(UTC), scenario)
    assert {path: path.read_bytes() for path in before} == before


def test_published_scenario_covers_tomorrow_civil_day_with_official_prices() -> None:
    data = build_scenario(FIXTURES, NOW, "tomorrow_published")
    zone = ZoneInfo("Europe/Helsinki")
    tomorrow = [
        slot
        for slot in data.prices.slots
        if slot.start.astimezone(zone).date().isoformat() == "2026-11-12"
    ]
    assert len(tomorrow) == 96
    assert not any(slot.forecast for slot in tomorrow)
    assert tomorrow[0].start.astimezone(zone).hour == 0
    assert tomorrow[-1].end.astimezone(zone).hour == 0


def test_official_slot_ignores_unused_forecast_uncertainty() -> None:
    slot = PriceSlot(NOW, NOW.replace(hour=14), 0.12, False, -1, 2)
    assert chart_limits((slot,)) == (0, 20)


@pytest.fixture
def drawn_text(monkeypatch):
    """Record semantic labels while retaining real glyph rendering and metrics."""
    calls = []
    original = _render._text

    def record(draw, xy, value, size=30, *, bold=True, anchor="lt", fill=0):
        bounds = draw.textbbox(xy, value, font=_render._font(size, bold), anchor=anchor)
        calls.append((xy, value, size, bold, bounds))
        original(draw, xy, value, size, bold=bold, anchor=anchor, fill=fill)

    monkeypatch.setattr(_render, "_text", record)
    return calls


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("battery", [None, 0, 9, 24, 25, 100])
def test_header_reserved_corner_readable_fonts_and_text_bounds(scenario, battery, drawn_text):
    data = build_scenario(FIXTURES, NOW, scenario)
    data = replace(data, meta=replace(data.meta, battery=battery))
    image = Image.open(BytesIO(_render.render_dashboard(data, now=NOW)))
    assert image.crop((942, 0, 1072, 70)).getextrema() == (255, 255)
    labels = [call[1] for call in drawn_text]
    assert "Wed 11 Nov · 14:31" in labels
    battery_labels = [value for value in labels if value.endswith("%")]
    assert battery_labels == ([f"{battery}%"] if battery is not None and battery < 25 else [])
    for _, value, size, bold, (left, top, right, bottom) in drawn_text:
        assert size >= 30, value
        assert bold, value
        assert 0 <= left <= right <= 1072, (value, left, right)
        assert 0 <= top <= bottom <= 1448, (value, top, bottom)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "In 0 min"),
        (30, "In 1 min"),
        (59 * 60, "In 59 min"),
        (3600, "In 1 h"),
        (7200, "In 2 h"),
        (65 * 60, "In 1 h 5 min"),
    ],
)
def test_delay_uses_hours_and_minutes(seconds, expected):
    assert _render.format_delay(seconds) == expected


@pytest.mark.parametrize(
    ("delay", "headline", "detail"),
    [
        (timedelta(minutes=45), "In 45 min", "start 15:16 · ends 17:16 · 12.0 c/kWh"),
        (timedelta(hours=2), "In 2 h", "start 16:31 · ends 18:31 · 12.0 c/kWh"),
        (timedelta(hours=2, minutes=10), "In 2 h 10 min", "start 16:41 · ends 18:41 · 12.0 c/kWh"),
        (timedelta(hours=13), "In 13 h", "start 03:31 Thu · ends 05:31 · 12.0 c/kWh"),
    ],
)
def test_dishwasher_future_start_detail(delay, headline, detail):
    start = NOW + delay
    dish = Dishwasher(
        periods=(DishwasherPeriod(start, start + timedelta(hours=2), "official", 0.12),)
    )
    assert _render.dishwasher_summary(dish, NOW) == (headline, detail)


@pytest.mark.parametrize(
    ("dish", "expected"),
    [
        (Dishwasher(enabled=False), ("Scheduling off", "")),
        (Dishwasher(status="unknown"), ("No schedule yet", "")),
        (Dishwasher(running=True), ("Run now", "until —")),
        (Dishwasher(running=True, remaining_minutes=41), ("Run now", "until 15:12")),
        (
            Dishwasher(
                periods=(
                    DishwasherPeriod(
                        NOW - timedelta(minutes=5), NOW + timedelta(minutes=41), "official"
                    ),
                )
            ),
            ("Run now", "until 15:12"),
        ),
    ],
)
def test_dishwasher_operational_states(dish, expected):
    assert _render.dishwasher_summary(dish, NOW) == expected


def test_two_chart_headings_hour_labels_live_price_and_daily_means(drawn_text):
    from custom_components.kindle_dash.data import six_day_prices

    data = build_scenario(FIXTURES, NOW, "normal")
    _render.render_dashboard(data, now=NOW)
    labels = [call[1] for call in drawn_text]
    assert "Next 6 hours" in labels
    assert "Next 6 days · c/kWh" in labels
    assert "now 46.6 c/kWh" in labels
    assert [value for (x, y), value, *_ in drawn_text if y == 939] == [
        str(h) for h in range(14, 21)
    ]
    assert [value for (x, y), value, *_ in drawn_text if y == 1340] == [
        "Wed",
        "Thu",
        "Fri",
        "Sat",
        "Sun",
        "Mon",
    ]
    hourly = six_day_prices(data.prices.slots, NOW)
    expected = []
    for offset in range(6):
        day = (NOW + timedelta(days=offset)).date()
        values = [slot.buy * 100 for slot in hourly if slot.start.date() == day]
        average = sum(values) / len(values) if values else None
        expected.append(
            "—" if average is None else f"{average:.0f}" if average >= 10 else f"{average:.1f}"
        )
    assert [value for (x, y), value, *_ in drawn_text if y == 1388] == expected
    assert not any(value in {"DW", "Window", "Today", "Tomorrow"} for value in labels)


def test_no_prices_message_in_both_charts(drawn_text):
    from tools.preview import _models

    data = build_scenario(FIXTURES, NOW, "normal")
    data = replace(data, prices=_models.Prices())
    _render.render_dashboard(data, now=NOW)
    labels = [call[1] for call in drawn_text]
    assert labels.count("No prices yet") == 2
    assert "now — c/kWh" in labels


def test_expired_prices_leave_near_term_empty_but_preserve_daily_history(drawn_text):
    from tools.preview import _models

    data = build_scenario(FIXTURES, NOW, "normal")
    expired = _models.PriceSlot(
        NOW.replace(hour=12, minute=0), NOW.replace(hour=13, minute=0), 0.79
    )
    data = replace(data, prices=_models.Prices((expired,), False))
    _render.render_dashboard(data, now=NOW)
    labels = [call[1] for call in drawn_text]
    assert labels.count("No prices yet") == 1
    assert "now — c/kWh" in labels
    assert next(value for (x, y), value, *_ in drawn_text if y == 1388) == "79"


@pytest.mark.parametrize(
    ("buy", "interior"), [(-0.01, 255), (0.04, 221), (0.12, 153), (0.20, 68), (0.30, 0)]
)
def test_official_price_tiers_have_black_outline_and_expected_fill(buy, interior):
    image = Image.new("L", (100, 100), 255)
    slot = PriceSlot(NOW, NOW + timedelta(hours=1), buy)
    _render._bar(ImageDraw.Draw(image), (10, 10, 90, 90), slot, width=3)
    assert image.getpixel((50, 50)) == interior
    assert image.getpixel((10, 50)) == 0
    assert image.getpixel((50, 10)) == 0


def test_forecast_bar_has_distinct_fill_and_cap():
    image = Image.new("L", (100, 100), 255)
    slot = PriceSlot(NOW, NOW + timedelta(hours=1), 0.3, True)
    _render._bar(ImageDraw.Draw(image), (10, 10, 90, 90), slot)
    assert image.getpixel((50, 50)) == 204
    assert image.getpixel((50, 10)) == 68


def test_hourly_numeric_labels_have_white_background(drawn_text):
    data = build_scenario(FIXTURES, NOW, "normal")
    image = Image.open(BytesIO(_render.render_dashboard(data, now=NOW)))
    values = [call for call in drawn_text if call[0][1] == 716]
    assert len(values) == 7
    for _, _, _, _, (left, top, right, bottom) in values:
        assert image.getpixel((int(left) - 3, int(top) + 3)) == 255
        assert image.getpixel((int(right) + 3, int(bottom) - 3)) == 255


def test_running_uses_remaining_time_instead_of_future_schedule_end():
    future = DishwasherPeriod(NOW + timedelta(hours=1), NOW + timedelta(hours=3), "official")
    dish = Dishwasher(running=True, remaining_minutes=41, periods=(future,))
    assert _render.dishwasher_summary(dish, NOW) == ("Run now", "until 15:12")
