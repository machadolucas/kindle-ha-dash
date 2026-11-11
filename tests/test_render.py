"""Visual transport, timeline and scenario invariants."""

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image, ImageDraw

from custom_components.kindle_dash.models import PriceSlot
from custom_components.kindle_dash.render import chart_limits, day_bounds, weather_icon
from tools.preview import SCENARIOS, _render, build_scenario

NOW = datetime.fromisoformat("2026-11-11T13:40:00+02:00")
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


def test_chart_scale_includes_negative_prices_and_uncertainty() -> None:
    slot = PriceSlot(NOW, NOW.replace(hour=14), -0.031, True, -0.15, 0.47)
    assert chart_limits((slot,)) == (-20, 50)
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


@pytest.mark.parametrize(
    ("scenario", "headline"),
    [
        ("normal", "Start at 03:15 Thu"),
        ("dishwasher_running", "Run now"),
        ("dishwasher_disabled", "Scheduling off"),
        ("dishwasher_unknown", "No schedule yet"),
    ],
)
def test_dishwasher_visible_action_semantics(monkeypatch, scenario: str, headline: str) -> None:
    labels = []
    monkeypatch.setattr(
        _render, "_text", lambda draw, xy, value, *args, **kwargs: labels.append(value)
    )
    image = Image.new("L", (1072, 1448), 255)
    _render._dishwasher(ImageDraw.Draw(image), build_scenario(FIXTURES, NOW, scenario), NOW)
    assert headline in labels


def test_active_period_is_run_now_even_without_running_sensor(monkeypatch) -> None:
    from dataclasses import replace

    labels = []
    monkeypatch.setattr(
        _render, "_text", lambda draw, xy, value, *args, **kwargs: labels.append(value)
    )
    data = build_scenario(FIXTURES, NOW, "dishwasher_running")
    data = replace(data, dishwasher=replace(data.dishwasher, running=False, status="unknown"))
    image = Image.new("L", (1072, 1448), 255)
    _render._dishwasher(ImageDraw.Draw(image), data, NOW)
    assert "Run now" in labels
    assert any(label.startswith("Cheap window until 15:12") for label in labels)


def test_chart_labels_use_live_price_full_hours_and_publication_hint(monkeypatch) -> None:
    from datetime import timedelta

    now = datetime.fromisoformat("2026-11-11T14:31:00+02:00")
    data = build_scenario(FIXTURES, now, "normal")
    labels = []
    monkeypatch.setattr(
        _render, "_text", lambda draw, xy, value, *args, **kwargs: labels.append((xy, value))
    )
    image = Image.new("L", (1072, 1448), 255)
    start = now.replace(minute=30, second=0)
    _render._chart(
        image,
        ImageDraw.Draw(image),
        data,
        now,
        "Next 6 hours",
        start,
        start + timedelta(hours=6),
        605,
        300,
        (0, 60),
        quarter_labels=True,
    )
    assert "now 46.6" in [value for _, value in labels]
    assert [value for xy, value in labels if xy[1] == 878] == [
        "15:00",
        "16:00",
        "17:00",
        "18:00",
        "19:00",
        "20:00",
    ]
    labels.clear()
    start, end = _render.day_bounds(now, 1)
    _render._chart(
        image, ImageDraw.Draw(image), data, now, "Tomorrow", start, end, 1180, 233, (0, 60)
    )
    assert "Tomorrow · forecast" in [value for _, value in labels]
    assert "official ~14:00" in [value for _, value in labels]
    assert [value for xy, value in labels if xy[1] == 1393] == [
        "00",
        "03",
        "06",
        "09",
        "12",
        "15",
        "18",
        "21",
        "00",
    ]


def test_expired_price_horizon_hides_old_prices_in_all_charts(monkeypatch) -> None:
    from dataclasses import replace
    from datetime import timedelta

    from tools.preview import _models

    now = datetime.fromisoformat("2026-11-11T14:31:00+02:00")
    data = build_scenario(FIXTURES, now, "normal")
    expired = _models.PriceSlot(now - timedelta(hours=1), now, 0.79)
    data = replace(data, prices=_models.Prices((expired,), False))
    labels = []
    monkeypatch.setattr(
        _render, "_text", lambda draw, xy, value, *args, **kwargs: labels.append(value)
    )
    _render.render_dashboard(data, now=now)
    assert labels.count("Price data unavailable") == 3
    assert "79.0" not in labels
    assert "now —" in labels
