"""Visual transport, timeline and scenario invariants."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from itertools import pairwise
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
            minimum, maximum = image.getextrema()
            assert maximum == 255
            assert (minimum == 0) == (condition in {"unknown", "exceptional"})


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
@pytest.mark.parametrize("battery", [None, 0, 9, 24, 25, 83, 100])
def test_header_reserved_corner_readable_fonts_and_text_bounds(scenario, battery, drawn_text):
    data = build_scenario(FIXTURES, NOW, scenario)
    data = replace(data, meta=replace(data.meta, battery=battery))
    image = Image.open(BytesIO(_render.render_dashboard(data, now=NOW)))
    # Nothing is drawn right of the header rule.
    assert image.crop((1046, 0, 1072, 70)).getextrema() == (255, 255)
    labels = [call[1] for call in drawn_text]
    assert "Wed 11 Nov · 14:31" in labels
    battery_labels = [value for value in labels if value.endswith("%")]
    assert battery_labels == ([f"{battery}%"] if battery is not None else [])
    header_right = image.crop((700, 0, 1072, 70))
    assert set(header_right.get_flattened_data()) == ({136, 255} if battery is not None else {255})
    if battery is not None:
        label = next(call for call in drawn_text if call[1] == f"{battery}%")
        left, _, right, _ = label[4]
        assert right <= 1044
        assert image.crop((700, 20, left - 8, 70)).getextrema() == (136, 255)
    for _, value, size, bold, (left, top, right, bottom) in drawn_text:
        assert size >= 30, value
        assert bold, value
        assert 0 <= left <= right <= 1072, (value, left, right)
        assert 0 <= top <= bottom <= 1448, (value, top, bottom)


def test_battery_glyph_fill_tracks_charge_level(drawn_text):
    data = build_scenario(FIXTURES, NOW, "normal")
    levels = (0, 25, 50, 75, 100)
    ink = []
    for level in levels:
        data = replace(data, meta=replace(data.meta, battery=level))
        image = Image.open(BytesIO(_render.render_dashboard(data, now=NOW)))
        label = next(call for call in drawn_text if call[1] == f"{level}%")
        glyph = image.crop((700, 20, label[4][0] - 8, 70))
        ink.append(sum(pixel == 136 for pixel in glyph.get_flattened_data()))
    assert all(a < b for a, b in pairwise(ink))
    for level, pixels in zip(levels, ink, strict=True):
        assert (pixels - ink[0]) / (ink[-1] - ink[0]) == pytest.approx(level / 100, abs=0.04)


@pytest.mark.parametrize("scenario", ["normal", "all_unavailable"])
def test_indoor_reading_groups_with_outdoor_above_dishwasher(scenario, drawn_text):
    data = build_scenario(FIXTURES, NOW, scenario)
    image = Image.open(BytesIO(_render.render_dashboard(data, now=NOW)))
    outdoor_value = "—" if data.weather.temperature is None else f"{data.weather.temperature:.1f}°"
    outdoor = next(call for call in drawn_text if call[1] == outdoor_value and call[2] > 54)
    indoor = next(call for call in drawn_text if call[2] == 54)
    assert indoor[1] == (
        "—"
        if data.weather.indoor_temperature is None
        else f"{data.weather.indoor_temperature:.1f}°"
    )
    assert not any(call[1].startswith("Inside") for call in drawn_text)
    card_top = next(y for y in range(330, 500) if image.getpixel((536, y)) == 136)
    house_area = image.crop((outdoor[4][0], outdoor[4][3], indoor[4][0], card_top))
    house_bounds = house_area.point(lambda gray: 255 if gray == 136 else 0).getbbox()
    assert house_bounds is not None
    assert house_bounds[0] == 0  # The group shares the outdoor value's left edge.
    assert 45 <= house_bounds[3] - house_bounds[1] <= 50
    house_top = outdoor[4][3] + house_bounds[1]
    house_bottom = outdoor[4][3] + house_bounds[3]
    # A missing value's dash is shorter than the normal numeric line box.
    outdoor_line_bottom = outdoor[0][1] + _render._font(outdoor[2]).getbbox("0°", anchor="lt")[3]
    reading_gap = min(house_top, indoor[4][1]) - outdoor_line_bottom
    card_gap = card_top - max(house_bottom, indoor[4][3])
    assert 0 < reading_gap <= 20
    assert card_gap >= 2 * reading_gap
    assert set(image.crop(indoor[4]).get_flattened_data()) == {0, 255}


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "Start now"),
        (30, "Start now"),
        (59 * 60, "In 1 h"),
        (3600, "In 1 h"),
        (7200, "In 2 h"),
        (65 * 60, "In 1 h"),
    ],
)
def test_delay_rounds_to_nearest_hour(seconds, expected):
    assert _render.format_delay(seconds) == expected


@pytest.mark.parametrize(
    ("delay", "headline", "detail"),
    [
        (timedelta(minutes=45), "In 1 h", ("start 15:16", "ends 17:16", "12.0 c/kWh")),
        (timedelta(hours=2), "In 2 h", ("start 16:31", "ends 18:31", "12.0 c/kWh")),
        (timedelta(hours=2, minutes=10), "In 2 h", ("start 16:41", "ends 18:41", "12.0 c/kWh")),
        (timedelta(hours=13), "In 13 h", ("start 03:31 Thu", "ends 05:31", "12.0 c/kWh")),
    ],
)
def test_dishwasher_future_start_detail(delay, headline, detail):
    start = NOW + delay
    dish = Dishwasher(
        periods=(DishwasherPeriod(start, start + timedelta(hours=2), "official", 0.12),)
    )
    assert _render.dishwasher_summary(dish, NOW) == (headline, detail)


@pytest.mark.parametrize(
    ("start_delay", "expected"),
    [
        (timedelta(hours=11, minutes=40), "In 11 h"),
        (timedelta(hours=12, minutes=50), "In 13 h"),
        (timedelta(minutes=20), "Start now"),
    ],
)
def test_dishwasher_brief_e_default_wake_window(start_delay, expected):
    start = NOW + start_delay
    dish = Dishwasher(periods=(DishwasherPeriod(start, start + timedelta(hours=2), "official"),))
    assert _render.dishwasher_summary(dish, NOW)[0] == expected


@pytest.mark.parametrize(
    ("start_delay", "expected"),
    [
        (timedelta(minutes=45), "In 1 h"),  # 30-minute midpoint rounds half up.
        (timedelta(hours=2, minutes=45), "In 3 h"),
    ],
)
def test_dishwasher_brief_e_rounds_midpoint_delays_half_up(start_delay, expected):
    start = NOW + start_delay
    dish = Dishwasher(periods=(DishwasherPeriod(start, start + timedelta(hours=1), "official"),))
    assert _render.dishwasher_summary(dish, NOW)[0] == expected


def test_dishwasher_brief_e_custom_wake_windows_and_default_equivalence():
    start = NOW + timedelta(minutes=45)
    dish = Dishwasher(periods=(DishwasherPeriod(start, start + timedelta(hours=1), "official"),))
    assert _render.dishwasher_summary(dish, NOW, None) == _render.dishwasher_summary(
        dish, NOW, NOW + timedelta(minutes=30)
    )
    assert _render.dishwasher_summary(dish, NOW, NOW + timedelta(minutes=60))[0] == "Start now"
    later = replace(
        dish,
        periods=(
            DishwasherPeriod(NOW + timedelta(minutes=75), NOW + timedelta(hours=2), "official"),
        ),
    )
    assert _render.dishwasher_summary(later, NOW, NOW + timedelta(minutes=60))[0] == "In 1 h"


def test_renderer_none_wake_matches_explicit_thirty_minute_default():
    data = build_scenario(FIXTURES, NOW, "normal")
    assert _render.render_dashboard(data, now=NOW) == _render.render_dashboard(
        data, now=NOW, next_wake=NOW + timedelta(minutes=30)
    )


def test_key_text_uses_crisp_black_and_white_pixels(drawn_text):
    data = build_scenario(FIXTURES, NOW, "normal")
    image = Image.open(BytesIO(_render.render_dashboard(data, now=NOW)))
    for _, value, _, _, box in drawn_text:
        if not value.endswith("%"):
            assert set(image.crop(box).get_flattened_data()) <= {0, 255}


@pytest.mark.parametrize(
    ("dish", "expected"),
    [
        (Dishwasher(enabled=False), ("Scheduling off", ())),
        (Dishwasher(status="unknown"), ("No schedule yet", ())),
        (Dishwasher(running=True), ("Run now", ())),
        (Dishwasher(running=True, remaining_minutes=41), ("Run now", ("until 15:12",))),
        (
            Dishwasher(
                periods=(
                    DishwasherPeriod(
                        NOW - timedelta(minutes=5), NOW + timedelta(minutes=41), "official"
                    ),
                )
            ),
            ("Run now", ("until 15:12",)),
        ),
    ],
)
def test_dishwasher_operational_states(dish, expected):
    assert _render.dishwasher_summary(dish, NOW) == expected


@pytest.mark.parametrize(
    "scenario",
    (
        *SCENARIOS,
        "start_now",
        "future_without_price",
        "running_without_price",
        "running_without_end",
    ),
)
def test_dishwasher_columns_fit_compact_rounded_card(scenario, drawn_text, monkeypatch):
    data = build_scenario(FIXTURES, NOW, scenario if scenario in SCENARIOS else "normal")
    expected_title = "In 12 h"
    expected_lines = ("start 03:15 Thu", "ends 06:00", "10.4 c/kWh")
    if scenario == "start_now":
        start = NOW + timedelta(minutes=20)
        data = replace(
            data,
            dishwasher=Dishwasher(
                periods=(DishwasherPeriod(start, start + timedelta(hours=2), avg_cost=0.104),)
            ),
        )
        expected_title = "Start now"
        expected_lines = ("start 14:51", "ends 16:51", "10.4 c/kWh")
    elif scenario == "future_without_price":
        data = replace(
            data,
            dishwasher=replace(
                data.dishwasher,
                periods=tuple(replace(period, avg_cost=None) for period in data.dishwasher.periods),
            ),
        )
        expected_lines = expected_lines[:2]
    elif scenario in {"running_without_price", "running_without_end"}:
        dish = Dishwasher(running=True)
        if scenario == "running_without_price":
            dish = replace(
                dish,
                periods=(
                    DishwasherPeriod(NOW - timedelta(minutes=5), NOW + timedelta(minutes=41)),
                ),
            )
        data = replace(data, dishwasher=dish)
        expected_title = "Run now"
        expected_lines = ("until 15:12",) if scenario == "running_without_price" else ()
    elif scenario == "dishwasher_running":
        expected_title, expected_lines = "Run now", ("until 16:03", "10.4 c/kWh")
    elif scenario == "dishwasher_disabled":
        expected_title, expected_lines = "Scheduling off", ()
    elif scenario in {"dishwasher_unknown", "all_unavailable"}:
        expected_title, expected_lines = "No schedule yet", ()

    cards = []
    original = ImageDraw.ImageDraw.rounded_rectangle

    def record_card(draw, xy, *args, **kwargs):
        if xy[2] - xy[0] > 900:
            cards.append((xy, kwargs))
        original(draw, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "rounded_rectangle", record_card)
    image = Image.new("L", (1072, 1448), 255)
    draw = ImageDraw.Draw(image)
    draw.fontmode = "1"
    _render._dishwasher(draw, data, NOW, None)
    assert len(cards) == 1
    (left, top, right, bottom), style = cards[0]
    assert bottom - top <= 170
    assert 14 <= style["radius"] <= 18
    assert style["outline"] == 136 and style["width"] == 2
    assert image.getpixel((left, top)) == 255
    assert image.getpixel((left + style["radius"], top)) == 136
    caption, headline, *details = drawn_text
    assert caption[1] == "DISHWASHER" and caption[4][3] < headline[4][1]
    assert headline[1] == expected_title
    if expected_title in {"Scheduling off", "No schedule yet"}:
        assert 30 < headline[2] < 110
    else:
        assert headline[2] == 116
    # Long states also respect the reserved right column when its data is absent.
    assert headline[4][2] <= 732
    assert tuple(call[1] for call in details) == expected_lines
    for _, value, size, bold, bounds in drawn_text:
        assert size >= 30 and bold
        assert left < bounds[0] < bounds[2] < right, value
        assert top < bounds[1] < bounds[3] < bottom, value
        assert set(image.crop(bounds).get_flattened_data()) <= {0, 255}, value
    for _, value, size, bold, bounds in details:
        assert size >= 36 and bold
        assert bounds[2] == pytest.approx(right - 20, abs=1), value
        assert bounds[0] - headline[4][2] >= 24, value
    if details:
        detail_center = (details[0][4][1] + details[-1][4][3]) / 2
        headline_center = (headline[4][1] + headline[4][3]) / 2
        assert detail_center == pytest.approx(headline_center, abs=1)
        for previous, following in pairwise(details):
            assert previous[4][3] < following[4][1]
    # The filled appliance is 95 px tall, before the caption/headline column.
    icon = image.crop((left + 20, top + 10, caption[4][0] - 20, bottom - 10))
    ink = icon.point(lambda gray: 255 if gray != 255 else 0).getbbox()
    assert ink is not None and 80 <= ink[3] - ink[1] <= 100
    assert {85, 136, 153, 204, 221} <= set(icon.get_flattened_data())


def test_two_chart_headings_hour_labels_live_price_and_daily_means(drawn_text):
    from custom_components.kindle_dash.data import six_day_prices

    data = build_scenario(FIXTURES, NOW, "normal")
    _render.render_dashboard(data, now=NOW)
    labels = [call[1] for call in drawn_text]
    assert "Next 6 hours" in labels
    assert "Next 6 days · c/kWh" in labels
    assert "now 46.6 c/kWh" in labels
    assert [value for (x, y), value, *_ in drawn_text if y == 945] == [
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
def test_official_price_tiers_have_gray_outline_and_expected_fill(buy, interior):
    image = Image.new("L", (100, 100), 255)
    slot = PriceSlot(NOW, NOW + timedelta(hours=1), buy)
    _render._bar(ImageDraw.Draw(image), (10, 10, 90, 90), slot, width=3)
    assert image.getpixel((50, 50)) == interior
    assert image.getpixel((10, 50)) == 68
    assert image.getpixel((50, 10)) == 68


def test_forecast_bar_has_distinct_fill_and_cap():
    image = Image.new("L", (100, 100), 255)
    slot = PriceSlot(NOW, NOW + timedelta(hours=1), 0.3, True)
    _render._bar(ImageDraw.Draw(image), (10, 10, 90, 90), slot)
    assert image.getpixel((50, 50)) == 204
    assert image.getpixel((50, 10)) == 68


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_quarter_chart_labels_fit_cells_and_bars_tile_for_every_scenario(scenario, monkeypatch):
    data = build_scenario(FIXTURES, NOW, scenario)
    _assert_quarter_chart_geometry(data, monkeypatch, expect_24=scenario != "all_unavailable")


def test_quarter_chart_labels_fit_mixed_tiers_zero_negative_and_spike(monkeypatch):
    from tools.preview import _models

    data = build_scenario(FIXTURES, NOW, "normal")
    start = (NOW.timestamp() // 900) * 900
    values = (-0.03, 0.0, 0.04, 0.12, 0.20, 0.30, 0.75) * 4
    slots = tuple(
        PriceSlot(
            datetime.fromtimestamp(start + index * 900, NOW.tzinfo),
            datetime.fromtimestamp(start + (index + 1) * 900, NOW.tzinfo),
            value,
            index % 2 == 1,
        )
        for index, value in enumerate(values)
    )
    data = replace(data, prices=_models.Prices(slots, True))
    _assert_quarter_chart_geometry(data, monkeypatch, expect_24=True)


def _assert_quarter_chart_geometry(data, monkeypatch, *, expect_24):
    verticals = []
    quarter_bars = []
    original_vertical = _render._vertical_text
    original_bar = _render._bar

    def capture_vertical(draw, center, bottom, value, size=32):
        font = _render._font(size)
        bounds = font.getbbox(value, anchor="lt")
        verticals.append((center, bottom, value, size, bounds))
        original_vertical(draw, center, bottom, value, size)

    def capture_bar(draw, rect, slot, *, width=1):
        if len(quarter_bars) < 24:
            quarter_bars.append(rect)
        original_bar(draw, rect, slot, width=width)

    monkeypatch.setattr(_render, "_vertical_text", capture_vertical)
    monkeypatch.setattr(_render, "_bar", capture_bar)
    _render.render_dashboard(data, now=NOW)

    expected_count = 24 if expect_24 else 0
    assert len(verticals) == expected_count
    assert len(quarter_bars) >= expected_count
    if not expect_24:
        return
    assert len(quarter_bars) == 24
    for (_, _, right, _), next_rect in pairwise(quarter_bars):
        assert right + 1 == next_rect[0]
    chart_left, chart_right = 28, 1044
    for index, ((x0, y0, x1, _), (center, bottom, value, size, bounds)) in enumerate(
        zip(quarter_bars, verticals, strict=True)
    ):
        assert size >= 32
        label_left = round(center - (bounds[3] - bounds[1]) / 2)
        label_right = label_left + bounds[3] - bounds[1]
        label_top = round(bottom - (bounds[2] - bounds[0]))
        assert x0 <= label_left < label_right <= x1 + 1, value
        assert chart_left <= label_left and label_right <= chart_right
        assert 622 <= label_top < bottom < y0, (value, label_top, bottom, y0)
        assert x0 == chart_left + round(index * (chart_right - chart_left) / 24)


def test_running_uses_remaining_time_instead_of_future_schedule_end():
    future = DishwasherPeriod(NOW + timedelta(hours=1), NOW + timedelta(hours=3), "official")
    dish = Dishwasher(running=True, remaining_minutes=41, periods=(future,))
    assert _render.dishwasher_summary(dish, NOW) == ("Run now", ("until 15:12",))
