"""Deterministic, distance-readable Pillow dashboard; no HA or network imports."""

from datetime import datetime, time, timedelta
from functools import lru_cache
from io import BytesIO
from math import ceil, cos, floor, pi, sin
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image, ImageDraw, ImageFont

from .data import next_hours_prices, six_day_prices
from .models import DashboardData, Dishwasher, PriceSlot

_FONT_DIR = Path(__file__).parent / "fonts"


@lru_cache(maxsize=32)
def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        str(_FONT_DIR / f"NotoSans-{'Bold' if bold else 'Regular'}.ttf"), size
    )


def _text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    value: str,
    size: int = 30,
    *,
    bold: bool = True,
    anchor: str = "lt",
    fill: int = 0,
) -> None:
    draw.text(xy, value, font=_font(size, bold), fill=fill, anchor=anchor)


def _fit(draw: ImageDraw.ImageDraw, value: str, size: int, width: int) -> int:
    """Fit exceptional long values without ever shrinking below the reading floor."""
    while size > 30 and draw.textlength(value, font=_font(size)) > width:
        size -= 1
    return size


def _message(draw: ImageDraw.ImageDraw, xy: tuple[float, float], value: str) -> None:
    bounds = draw.textbbox(xy, value, font=_font(40), anchor="mm")
    draw.rectangle((bounds[0] - 8, bounds[1] - 6, bounds[2] + 8, bounds[3] + 6), fill=255)
    _text(draw, xy, value, 40, anchor="mm")


def _fmt(value: float | None, suffix: str = "", digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}{suffix}"


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        return ZoneInfo("Europe/Helsinki")


def day_bounds(now: datetime, offset: int = 0) -> tuple[datetime, datetime]:
    """Civil midnight boundaries preserve the timezone's 23/24/25 hour days."""
    day = now.date() + timedelta(days=offset)
    return datetime.combine(day, time(), now.tzinfo), datetime.combine(
        day + timedelta(days=1), time(), now.tzinfo
    )


def chart_limits(slots: tuple[PriceSlot, ...]) -> tuple[int, int]:
    """Only displayed prices set the scale; uncertainty is not plotted."""
    values = [slot.buy * 100 for slot in slots]
    return floor(min([0, *values]) / 10) * 10, ceil(max([20, *values]) / 10) * 10


def weather_icon(
    draw: ImageDraw.ImageDraw,
    condition: str,
    x: float,
    y: float,
    size: int,
    *,
    night: bool = False,
) -> None:
    """Draw solid silhouettes in the reader's 16-level gray palette."""

    def box(a: float, b: float, c: float, d: float) -> tuple[float, float, float, float]:
        return x + a * size, y + b * size, x + c * size, y + d * size

    stroke = max(3, size // 22)
    if condition in {"unknown", "unavailable", "exceptional"}:
        draw.ellipse(box(0.12, 0.1, 0.88, 0.86), fill=221, outline=136, width=stroke)
        _text(
            draw,
            (x + size / 2, y + size * 0.48),
            "!" if condition == "exceptional" else "?",
            max(30, int(size * 0.58)),
            bold=True,
            anchor="mm",
        )
        return
    clear = condition in {"sunny", "clear-night"}
    partly = condition in {"partlycloudy", "partly-cloudy-night"}
    if clear or partly:
        if condition == "clear-night" or night:
            draw.ellipse(box(0.17, 0.08, 0.72, 0.65), fill=119)
            draw.ellipse(box(0.34, 0.02, 0.82, 0.51), fill=255)
        else:
            for angle in range(0, 360, 45):
                angle_r = angle * pi / 180
                draw.line(
                    (
                        x + size * (0.455 + cos(angle_r) * 0.24),
                        y + size * (0.365 + sin(angle_r) * 0.24),
                        x + size * (0.455 + cos(angle_r) * 0.32),
                        y + size * (0.365 + sin(angle_r) * 0.32),
                    ),
                    fill=187,
                    width=stroke * 2,
                )
            draw.ellipse(box(0.28, 0.19, 0.63, 0.54), fill=119)
        if clear:
            return
    if condition in {"windy", "windy-variant"}:
        for index in range(3):
            yy = 0.28 + index * 0.26
            draw.arc(
                box(0.56, yy - 0.20, 0.88, yy),
                270,
                90,
                fill=136,
                width=stroke * 2,
            )
            draw.line(
                box(0.12, yy - stroke / size, 0.72, yy - stroke / size),
                fill=136,
                width=stroke * 2,
            )
        return
    if condition == "fog":
        for index in range(4):
            draw.line(
                box(0.12, 0.22 + index * 0.16, 0.86, 0.22 + index * 0.16),
                fill=153,
                width=stroke * 2,
            )
        return
    # Union the lobes before filling the inset: no internal circle outlines.
    lobes = ((0.12, 0.35, 0.51, 0.72), (0.33, 0.23, 0.76, 0.72), (0.57, 0.39, 0.94, 0.72))
    for lobe in lobes:
        draw.ellipse(box(*lobe), fill=136)
    draw.rectangle(box(0.3, 0.48, 0.77, 0.72), fill=136)
    inset = stroke / size
    for a, b, c, d in lobes:
        draw.ellipse(box(a + inset, b + inset, c - inset, d - inset), fill=204)
    draw.rectangle(box(0.3, 0.48, 0.77, 0.72 - inset), fill=204)
    rainy = condition in {"rainy", "pouring", "snowy-rainy", "lightning-rainy"}
    snowy = condition in {"snowy", "snowy-rainy", "hail"}
    if rainy:
        for index in range(3 if condition == "pouring" else 2):
            a = 0.28 + index * 0.23
            draw.line(box(a + 0.05, 0.78, a, 0.94), fill=85, width=stroke)
    if snowy:
        for a in (0.3, 0.7):
            draw.line(box(a - 0.06, 0.86, a + 0.06, 0.86), fill=85, width=stroke)
            draw.line(box(a, 0.8, a, 0.93), fill=85, width=stroke)
    if condition in {"lightning", "lightning-rainy"}:
        points = [(0.52, 0.7), (0.39, 0.86), (0.52, 0.86), (0.44, 1.0), (0.67, 0.79), (0.54, 0.79)]
        draw.polygon([(x + a * size, y + b * size) for a, b in points], fill=85)


def _weather(draw: ImageDraw.ImageDraw, data: DashboardData, now: datetime) -> None:
    weather = data.weather
    weather_icon(draw, weather.condition, 24, 100, 183, night=now.hour < 7 or now.hour > 17)
    temperature = _fmt(weather.temperature, "°")
    size = _fit(draw, temperature, 104, 300)
    _text(draw, (217, 148), temperature, size)
    _text(draw, (28, 291), f"Inside {_fmt(weather.indoor_temperature, '°')}", 54)
    # Clock-hour targets three hours apart, rather than four adjacent forecasts.
    first = now.replace(minute=0, second=0, microsecond=0).timestamp() + 3 * 3600
    for index in range(4):
        target = datetime.fromtimestamp(first + index * 3 * 3600, now.tzinfo)
        entry = next(
            (entry for entry in weather.hourly if entry.time.timestamp() == target.timestamp()),
            None,
        )
        x = 566 + index * 136
        _text(draw, (x, 111), target.strftime("%H:%M"), 34, anchor="mt")
        weather_icon(
            draw,
            entry.condition if entry else "unknown",
            x - 60,
            156,
            120,
            night=target.hour < 7 or target.hour > 17,
        )
        _text(draw, (x, 291), _fmt(entry.temperature if entry else None, "°"), 44, anchor="mt")


def format_delay(seconds: float) -> str:
    """Round a midpoint-relative delay to the timer's whole hours, half up."""
    hours = floor(max(0, seconds) / 3600 + 0.5)
    return f"In {hours} h" if hours else "Start now"


def dishwasher_summary(
    dish: Dishwasher, now: datetime, next_wake: datetime | None = None
) -> tuple[str, str]:
    """Pure operational copy, shared by the renderer and semantic tests."""
    upcoming = sorted(
        (period for period in dish.periods if period.end.timestamp() > now.timestamp()),
        key=lambda period: period.start.timestamp(),
    )
    active = next(
        (period for period in upcoming if period.start.timestamp() <= now.timestamp()), None
    )
    period = active or next(iter(upcoming), None)
    if not dish.enabled:
        return "Scheduling off", ""
    if dish.running or active:
        if active:
            end = active.end.astimezone(now.tzinfo).strftime("%H:%M")
        elif dish.remaining_minutes is not None:
            end = datetime.fromtimestamp(
                now.timestamp() + max(0, dish.remaining_minutes) * 60, now.tzinfo
            ).strftime("%H:%M")
        else:
            end = "—"
        return "Run now", f"until {end}"
    if not period:
        return "No schedule yet", ""
    start = period.start.astimezone(now.tzinfo)
    day = start.strftime(" %a") if start.date() != now.date() else ""
    detail = f"start {start:%H:%M}{day} · ends {period.end.astimezone(now.tzinfo):%H:%M}"
    if period.avg_cost is not None:
        detail += f" · {period.avg_cost * 100:.1f} c/kWh"
    wake_at = next_wake.timestamp() if next_wake is not None else now.timestamp() + 1800
    view_mid = (now.timestamp() + wake_at) / 2
    return format_delay(period.start.timestamp() - view_mid), detail


def _dishwasher(
    draw: ImageDraw.ImageDraw, data: DashboardData, now: datetime, next_wake: datetime | None
) -> None:
    draw.rectangle((28, 354, 1044, 578), outline=68, width=5)
    _text(draw, (48, 372), "DISHWASHER", 32)
    title, detail = dishwasher_summary(data.dishwasher, now, next_wake)
    _text(draw, (48, 410), title, _fit(draw, title, 110, 976))
    _text(draw, (48, 532), detail, _fit(draw, detail, 44, 976))


def _tier(value: float) -> int:
    if value < 0:
        return 255
    return 221 if value < 8 else 153 if value < 16 else 68 if value < 25 else 0


def _price_label(value: float) -> str:
    return f"{value:.0f}" if value >= 10 else f"{value:.1f}"


def _bar(
    draw: ImageDraw.ImageDraw,
    rect: tuple[float, float, float, float],
    slot: PriceSlot,
    *,
    width: int = 1,
) -> None:
    if slot.forecast:
        draw.rectangle(rect, fill=204)
        cap = rect[3] if slot.buy < 0 else rect[1]
        draw.line((rect[0], cap, rect[2], cap), fill=68, width=2)
    else:
        draw.rectangle(rect, fill=_tier(slot.buy * 100), outline=68, width=width)


def _vertical_text(
    draw: ImageDraw.ImageDraw, center: float, bottom: float, value: str, size: int = 32
) -> None:
    """Place a crisp black 90-degree label in its own quarter-hour column."""
    bounds = _font(size).getbbox(value, anchor="lt")
    mask = Image.new("1", (bounds[2] - bounds[0], bounds[3] - bounds[1]))
    ImageDraw.Draw(mask).text((0, 0), value, font=_font(size), fill=1, anchor="lt")
    mask = mask.rotate(90, expand=True)
    draw.bitmap((round(center - mask.width / 2), round(bottom - mask.height)), mask, fill=0)


def _six_hours(draw: ImageDraw.ImageDraw, data: DashboardData, now: datetime) -> None:
    slots = next_hours_prices(data.prices.slots, now)
    current = next(
        (
            slot
            for slot in data.prices.slots
            if slot.start.timestamp() <= now.timestamp() < slot.end.timestamp()
        ),
        None,
    )
    _text(draw, (28, 606), "Next 6 hours", 40)
    caption = f"now {_fmt(current.buy * 100 if current else None)} c/kWh"
    _text(draw, (1044, 606), caption, 40, anchor="rt")
    left, right, top, bottom = 28, 1044, 752, 928
    low, high = chart_limits(slots)

    def yp(value: float) -> float:
        return bottom - (value - low) / (high - low) * (bottom - top)

    for tick in range(low, high + 1, 10):
        draw.line((left, yp(tick), right, yp(tick)), fill=221, width=2)
    zero = yp(0)
    start_ts = floor(now.timestamp() / 900) * 900
    by_start = {slot.start.timestamp(): slot for slot in slots}
    for index in range(24):
        instant = start_ts + index * 900
        slot = by_start.get(instant)
        # Integer, half-open extents tile all 1,016 pixels with no empty gutter.
        x0 = left + round(index * (right - left) / 24)
        x1 = left + round((index + 1) * (right - left) / 24)
        center = (x0 + x1) / 2
        if slot:
            yy = yp(slot.buy * 100)
            y0, y1 = sorted((yy, zero))
            _bar(
                draw,
                (x0, y0, x1 - 1, max(y0 + 2, y1)),
                slot,
            )
            # The separator occupies bar pixels, rather than creating a gap.
            draw.line((x1 - 2, y0, x1 - 2, max(y0 + 2, y1)), fill=221, width=2)
            _vertical_text(draw, center, y0 - 8, _price_label(slot.buy * 100))
        local = datetime.fromtimestamp(instant, now.tzinfo)
        if index == 0 or local.minute == 0:
            _text(draw, (center, 945), local.strftime("%H"), 34, anchor="mt")
    draw.line((left, zero, right, zero), fill=68, width=3)
    if not slots:
        _message(draw, ((left + right) / 2, (top + bottom) / 2), "No prices yet")


def _six_days(draw: ImageDraw.ImageDraw, data: DashboardData, now: datetime) -> None:
    slots = six_day_prices(data.prices.slots, now)
    start, _ = day_bounds(now)
    _, end = day_bounds(now, 5)
    _text(draw, (28, 994), "Next 6 days · c/kWh", 40)
    draw.rectangle((729, 1005, 750, 1026), fill=0)
    _text(draw, (760, 1001), "official", 30)
    draw.rectangle((892, 1005, 913, 1026), fill=204)
    draw.line((892, 1005, 913, 1005), fill=68, width=2)
    _text(draw, (923, 1001), "forecast", 30)
    left, right, top, bottom = 88, 1044, 1080, 1315
    start_ts, end_ts = start.timestamp(), end.timestamp()
    low, high = chart_limits(slots)

    def xp(instant: datetime) -> float:
        return left + (instant.timestamp() - start_ts) / (end_ts - start_ts) * (right - left)

    def yp(value: float) -> float:
        return bottom - (value - low) / (high - low) * (bottom - top)

    step = 10 if high - low <= 60 else 20
    for tick in range(ceil(low / step) * step, high + 1, step):
        yy = yp(tick)
        draw.line((left, yy, right, yy), fill=221, width=2)
        _text(draw, (left - 12, yy), str(tick), 30, anchor="rm")
    zero = yp(0)
    for slot in slots:
        x0, x1 = xp(slot.start), xp(slot.end) - 1
        y0, y1 = sorted((yp(slot.buy * 100), zero))
        _bar(draw, (x0, y0, max(x0, x1), max(y0 + 1, y1)), slot)
    draw.line((left, zero, right, zero), fill=68, width=2)
    for offset in range(7):
        day_start, day_end = day_bounds(now, offset)
        xx = xp(day_start)
        draw.line((xx, top, xx, bottom + 9), fill=68, width=4)
        if offset == 6:
            continue
        center = (xx + xp(day_end)) / 2
        _text(draw, (center, 1340), day_start.strftime("%a"), 36, anchor="mt")
        values = [
            slot.buy * 100
            for slot in slots
            if day_start.timestamp() <= slot.start.timestamp() < day_end.timestamp()
        ]
        label = _price_label(sum(values) / len(values)) if values else "—"
        _text(draw, (center, 1388), label, 34, anchor="mt")
    # A white halo makes the full-height black line visible over every price tier.
    xx = xp(now)
    draw.line((xx, top, xx, bottom), fill=255, width=12)
    draw.line((xx, top, xx, bottom), fill=0, width=4)
    draw.polygon(((xx - 18, top - 31), (xx + 18, top - 31), (xx, top - 3)), fill=0)
    if not slots:
        _message(draw, ((left + right) / 2, (top + bottom) / 2), "No prices yet")


def render_dashboard(
    data: DashboardData,
    *,
    now: datetime,
    next_wake: datetime | None = None,
    width: int = 1072,
    height: int = 1448,
) -> bytes:
    """Return an optimized 16-level grayscale PNG; caller supplies the clock."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if next_wake is not None and (next_wake.tzinfo is None or next_wake.utcoffset() is None):
        raise ValueError("next_wake must be timezone-aware")
    if width < 1 or height < 1:
        raise ValueError("Image dimensions must be positive")
    now = now.astimezone(_zone(data.meta.time_zone))
    image = Image.new("L", (1072, 1448), 255)
    draw = ImageDraw.Draw(image)
    draw.fontmode = "1"
    _text(draw, (28, 28), f"{now:%a %d %b} · {now:%H:%M}", 44)
    if data.meta.battery is not None and data.meta.battery < 25:
        _text(draw, (922, 34), f"{data.meta.battery}%", 34, anchor="rt")
    draw.line((28, 88, 1044, 88), fill=68, width=3)
    _weather(draw, data, now)
    _dishwasher(draw, data, now, next_wake)
    _six_hours(draw, data, now)
    _six_days(draw, data, now)
    if image.size != (width, height):
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    image = image.point([round(value / 17) * 17 for value in range(256)])
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
