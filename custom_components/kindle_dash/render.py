"""Deterministic Pillow dashboard: no network, Home Assistant, or system fonts."""

from datetime import UTC, datetime, time, timedelta
from functools import lru_cache
from io import BytesIO
from math import ceil, cos, floor, pi, sin
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image, ImageDraw, ImageFont

from .data import timestamp
from .models import DashboardData, PriceSlot

_FONT_DIR = Path(__file__).parent / "fonts"


@lru_cache(maxsize=32)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        str(_FONT_DIR / f"NotoSans-{'Bold' if bold else 'Regular'}.ttf"), size
    )


def _text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    value: str,
    size: int = 24,
    *,
    bold: bool = False,
    anchor: str = "lt",
    fill: int = 0,
) -> None:
    draw.text(xy, value, font=_font(size, bold), fill=fill, anchor=anchor)


def _message(draw: ImageDraw.ImageDraw, xy: tuple[float, float], value: str, size: int) -> None:
    """Keep missing-data messages readable over the chart grid."""
    bounds = draw.textbbox(xy, value, font=_font(size), anchor="mm")
    draw.rectangle((bounds[0] - 6, bounds[1] - 4, bounds[2] + 6, bounds[3] + 4), fill=255)
    _text(draw, xy, value, size, anchor="mm")


def _fmt(value: float | None, suffix: str = "", digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}{suffix}"


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Helsinki")


def day_bounds(now: datetime, offset: int = 0) -> tuple[datetime, datetime]:
    """Civil midnight boundaries preserve the timezone's 23/24/25 hour days."""
    day = now.date() + timedelta(days=offset)
    return datetime.combine(day, time(), now.tzinfo), datetime.combine(
        day + timedelta(days=1),
        time(),
        now.tzinfo,
    )


def chart_limits(slots: tuple[PriceSlot, ...]) -> tuple[int, int]:
    """Shared cent/kWh range: zero, 10-cent ticks, and forecast uncertainty."""
    values = [0.0]
    for slot in slots:
        values.append(slot.buy * 100)
        if slot.forecast:
            values.extend(value * 100 for value in (slot.p10, slot.p90) if value is not None)
    low, high = floor(min(values) / 10) * 10, ceil(max(20, *values) / 10) * 10
    return low, max(high, low + 10)


def weather_icon(
    draw: ImageDraw.ImageDraw,
    condition: str,
    x: float,
    y: float,
    size: int,
    *,
    night: bool = False,
) -> None:
    """Draw HA conditions as high-contrast geometric icons, without icon fonts."""

    def box(a: float, b: float, c: float, d: float) -> tuple[float, float, float, float]:
        return x + a * size, y + b * size, x + c * size, y + d * size

    stroke = max(2, size // 25)
    if condition in {"unknown", "unavailable", "exceptional"}:
        draw.ellipse(box(0.12, 0.1, 0.88, 0.86), outline=0, width=stroke)
        _text(
            draw,
            (x + size / 2, y + size * 0.48),
            "!" if condition == "exceptional" else "?",
            max(22, int(size * 0.58)),
            bold=True,
            anchor="mm",
        )
        return
    clear = condition in {"sunny", "clear-night"}
    partly = condition in {"partlycloudy", "partly-cloudy-night"}
    if clear or partly:
        if condition == "clear-night" or night:
            draw.ellipse(box(0.17, 0.08, 0.72, 0.65), fill=0)
            draw.ellipse(box(0.34, 0.02, 0.82, 0.51), fill=255)
        else:
            draw.ellipse(box(0.28, 0.19, 0.63, 0.54), outline=0, width=stroke)
            for angle in range(0, 360, 45):
                angle_r = angle * pi / 180
                draw.line(
                    (
                        x + size * (0.455 + cos(angle_r) * 0.24),
                        y + size * (0.365 + sin(angle_r) * 0.24),
                        x + size * (0.455 + cos(angle_r) * 0.32),
                        y + size * (0.365 + sin(angle_r) * 0.32),
                    ),
                    fill=0,
                    width=stroke,
                )
        if clear:
            return
    if condition in {"windy", "windy-variant"}:
        for index in range(3):
            draw.arc(
                box(0.15, 0.14 + index * 0.2, 0.9, 0.4 + index * 0.2),
                190,
                350,
                fill=0,
                width=stroke,
            )
            draw.line(
                (
                    x + 0.12 * size,
                    y + (0.36 + index * 0.18) * size,
                    x + 0.7 * size,
                    y + (0.36 + index * 0.18) * size,
                ),
                fill=0,
                width=stroke,
            )
        return
    if condition == "fog":
        for index in range(4):
            draw.line(
                box(0.12, 0.22 + index * 0.16, 0.86, 0.22 + index * 0.16), fill=0, width=stroke
            )
        return
    # A single cloud silhouette retains detail even in the six hourly columns.
    draw.ellipse(box(0.12, 0.35, 0.51, 0.72), fill=255, outline=0, width=stroke)
    draw.ellipse(box(0.33, 0.23, 0.76, 0.72), fill=255, outline=0, width=stroke)
    draw.ellipse(box(0.57, 0.39, 0.94, 0.72), fill=255, outline=0, width=stroke)
    draw.rectangle(box(0.3, 0.48, 0.77, 0.7), fill=255)
    draw.line(box(0.28, 0.71, 0.78, 0.71), fill=0, width=stroke)
    rainy = condition in {"rainy", "pouring", "snowy-rainy", "lightning-rainy"}
    snowy = condition in {"snowy", "snowy-rainy", "hail"}
    if rainy:
        for index in range(3 if condition == "pouring" else 2):
            a = 0.28 + index * 0.23
            draw.line(box(a + 0.05, 0.78, a, 0.94), fill=0, width=stroke)
    if snowy:
        for a in (0.3, 0.7):
            draw.line(box(a - 0.06, 0.86, a + 0.06, 0.86), fill=0, width=stroke)
            draw.line(box(a, 0.8, a, 0.93), fill=0, width=stroke)
    if condition in {"lightning", "lightning-rainy"}:
        points = [(0.52, 0.7), (0.39, 0.86), (0.52, 0.86), (0.44, 1.0), (0.67, 0.79), (0.54, 0.79)]
        draw.polygon([(x + a * size, y + b * size) for a, b in points], fill=0)


def _weather(draw: ImageDraw.ImageDraw, data: DashboardData, now: datetime) -> None:
    weather = data.weather
    weather_icon(draw, weather.condition, 33, 102, 92, night=now.hour < 7 or now.hour > 17)
    _text(draw, (130, 104), _fmt(weather.temperature, "°"), 66, bold=True)
    _text(draw, (34, 199), f"Humidity {_fmt(weather.humidity, '%', 0)}", 23)
    bearing = (
        ""
        if weather.wind_bearing is None
        else (
            " " + ("N", "NE", "E", "SE", "S", "SW", "W", "NW")[round(weather.wind_bearing / 45) % 8]
        )
    )
    _text(draw, (34, 231), f"Wind {_fmt(weather.wind_speed)} {weather.wind_unit}{bearing}", 22)
    _text(draw, (34, 263), f"Inside {_fmt(weather.indoor_temperature, '°')}", 24, bold=True)
    hourly = [entry for entry in weather.hourly if entry.time >= now][:6]
    if not hourly:
        _text(draw, (430, 143), "Hourly forecast unavailable", 25)
    for index, entry in enumerate(hourly):
        x = 402 + index * 109
        local = entry.time.astimezone(now.tzinfo)
        _text(draw, (x + 44, 105), local.strftime("%H:%M"), 23, anchor="mt")
        weather_icon(draw, entry.condition, x + 9, 138, 70, night=local.hour < 7 or local.hour > 17)
        _text(draw, (x + 44, 219), _fmt(entry.temperature, "°"), 25, bold=True, anchor="mt")
        if entry.precipitation > 0:
            _text(draw, (x + 44, 254), f"{entry.precipitation:g} mm", 22, anchor="mt")
    daily = [
        entry for entry in weather.daily if entry.time.astimezone(now.tzinfo).date() >= now.date()
    ][:3]
    for index, entry in enumerate(daily):
        x = 34 + index * 338
        weather_icon(draw, entry.condition, x, 302, 45)
        label = entry.time.astimezone(now.tzinfo).strftime("%a")
        _text(draw, (x + 54, 305), label, 23, bold=True)
        _text(draw, (x + 115, 305), f"{_fmt(entry.temperature, '°')}/{_fmt(entry.low, '°')}", 23)
    draw.line((32, 365, 1040, 365), fill=0, width=2)


def _relative(delta: float) -> str:
    minutes = max(0, round(delta / 60))
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins:02d}m" if hours else f"{mins} min"


def _dishwasher(draw: ImageDraw.ImageDraw, data: DashboardData, now: datetime) -> None:
    dish = data.dishwasher
    _text(draw, (48, 383), "DISHWASHER", 25, bold=True)
    upcoming = [period for period in dish.periods if period.end > now]
    period = upcoming[0] if upcoming else None
    active = next((entry for entry in upcoming if entry.start <= now < entry.end), None)
    if not dish.enabled:
        title, detail = "Scheduling off", "Schedule disabled"
        period = None
    elif dish.running or active:
        period = active or period
        title = "Run now"
        detail = (
            f"Cheap window until {period.end.astimezone(now.tzinfo):%H:%M}"
            if period
            else "Cheap window end unavailable"
        )
        if dish.remaining_minutes is not None:
            detail += f"  ·  {dish.remaining_minutes:g} min remaining"
    elif period:
        local_start = period.start.astimezone(now.tzinfo)
        day = local_start.strftime(" %a") if local_start.date() != now.date() else ""
        title = f"Start at {local_start:%H:%M}{day}"
        detail = (
            f"In {_relative((period.start - now).total_seconds())}"
            f"  ·  Ends {period.end.astimezone(now.tzinfo):%H:%M}"
        )
    else:
        title, detail = "No schedule yet", "Waiting for a scheduled period"
    title_size = 75
    while draw.textlength(title, font=_font(title_size, True)) > 970 and title_size > 64:
        title_size -= 1
    _text(draw, (48, 417), title, title_size, bold=True)
    _text(draw, (49, 508), detail, 28)
    cost = (
        f"Average {period.avg_cost * 100:.1f} c/kWh"
        if period and period.avg_cost is not None
        else ""
    )

    def clock(value: str | None) -> str | None:
        parsed = timestamp(value)
        if parsed:
            return parsed.astimezone(now.tzinfo).strftime("%H:%M")
        try:
            return time.fromisoformat(value).strftime("%H:%M") if value else None
        except ValueError:
            return None

    start, end = clock(dish.window_start), clock(dish.window_end)
    window = f"Window {start}–{end}" if start and end else ""  # noqa: RUF001
    _text(draw, (49, 550), cost, 23)
    _text(draw, (1023, 550), window, 23, anchor="rt")
    draw.rectangle((32, 375, 1040, 587), outline=0, width=5)


def _tier(value: float) -> int:
    return 221 if value < 8 else 153 if value < 16 else 68 if value < 25 else 0


def _rotated(image: Image.Image, xy: tuple[int, int], value: str) -> None:
    font = _font(22)
    bounds = font.getbbox(value)
    patch = Image.new("L", (bounds[2] + 2, bounds[3] - bounds[1] + 3), 255)
    ImageDraw.Draw(patch).text((1, -bounds[1]), value, font=font, fill=0)
    patch = patch.rotate(90, expand=True)
    image.paste(patch, xy)


def _chart(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    data: DashboardData,
    now: datetime,
    title: str,
    start: datetime,
    end: datetime,
    top: int,
    height: int,
    limits: tuple[int, int],
    *,
    quarter_labels: bool = False,
    current: bool = False,
) -> None:
    start_ts, end_ts = start.timestamp(), end.timestamp()
    prices_fresh = any(slot.end.timestamp() > now.timestamp() for slot in data.prices.slots)
    slots = tuple(
        slot
        for slot in data.prices.slots
        if prices_fresh and slot.end.timestamp() > start_ts and slot.start.timestamp() < end_ts
    )
    forecast = any(slot.forecast for slot in slots)
    heading = title
    caption = "c/kWh · official" if slots else "c/kWh"
    if quarter_labels:
        heading = "Next 6 hours · c/kWh"
        current_slot = next((slot for slot in slots if slot.start <= now < slot.end), None)
        caption = f"now {current_slot.buy * 100:.1f}" if current_slot else "now —"
    elif title == "Tomorrow":
        if forecast:
            heading = "Tomorrow · forecast"
        caption = "c/kWh · official" if data.prices.tomorrow_available else "official ~14:00"
    _text(draw, (34, top), heading, 29, bold=True)
    _text(draw, (1038, top + 3), caption, 24, bold=quarter_labels, anchor="rt")
    left, right = 88, 1038
    chart_top = top + 49
    bottom = top + height - (112 if quarter_labels else 47)
    low, high = limits

    def xp(value: datetime) -> float:
        return left + (value.timestamp() - start_ts) / (end_ts - start_ts) * (right - left)

    def yp(value: float) -> float:
        return bottom - (value - low) / (high - low) * (bottom - chart_top)

    tick_count = (high - low) // 10
    # At the supported fixture ranges the 22px font has a 16px digit bbox,
    # allowing every 10-cent label; thin labels only for extreme arbitrary data.
    skip = max(1, ceil(tick_count / 9))
    for tick in range(low, high + 1, 10):
        yy = yp(tick)
        draw.line((left, yy, right, yy), fill=204, width=2)
        if tick in {0, high, low} or (tick - low) % (10 * skip) == 0:
            _text(draw, (left - 12, yy), str(tick), 22, anchor="rm")
    zero = yp(0)
    x0: float
    x1: float
    xx: float
    for slot in slots:
        x0, x1 = max(left, int(xp(slot.start))), min(right, int(xp(slot.end)) - 2)
        x1 = max(x0, x1)
        yy = yp(slot.buy * 100)
        y0, y1 = sorted((yy, zero))
        y1 = max(y0 + 1, y1)
        rect = (x0, y0, x1, y1)
        if slot.forecast:
            draw.rectangle(rect, fill=255, outline=0, width=2)
            for xx in range(int(x0) - int(y1 - y0), int(x1) + 1, 7):
                a, b = max(x0, xx), min(x1, xx + (y1 - y0))
                if b > a:
                    draw.line((a, y1 - (a - xx), b, y1 - (b - xx)), fill=102, width=2)
            if slot.p10 is not None and slot.p90 is not None:
                cx = (x0 + x1) / 2
                lo, hi = yp(slot.p10 * 100), yp(slot.p90 * 100)
                draw.line((cx, lo, cx, hi), fill=0, width=2)
                draw.line((cx - 2, lo, cx + 2, lo), fill=0, width=2)
                draw.line((cx - 2, hi, cx + 2, hi), fill=0, width=2)
        elif slot.buy < 0:
            draw.rectangle(rect, fill=255, outline=0, width=2)
            for xx in range(int(x0) + 2, int(x1), 5):
                for yy_dot in range(int(y0) + 3, int(y1), 5):
                    draw.rectangle((xx, yy_dot, xx + 1, yy_dot + 1), fill=0)
        else:
            draw.rectangle(rect, fill=_tier(slot.buy * 100), outline=0, width=2)
        if quarter_labels:
            _rotated(image, (round((x0 + x1) / 2) - 10, bottom + 20), f"{slot.buy * 100:.1f}")
    draw.line((left, zero, right, zero), fill=0, width=2)
    # Dishwasher periods occupy a dedicated band, separate from prices and time labels.
    for period in data.dishwasher.periods:
        x0, x1 = max(left, xp(period.start)), min(right, xp(period.end))
        if x1 > x0:
            draw.line((x0, bottom + 8, x1, bottom + 8), fill=0, width=7)
            tag_x = min(x0 + 5, right - 43)
            if current and abs(tag_x + 18 - xp(now)) < 35:
                tag_x = min(right - 43, max(left, x1 - 43))
            draw.rectangle((tag_x - 3, bottom - 3, tag_x + 38, bottom + 20), fill=255)
            _text(draw, (tag_x, bottom + 8), "DW", 22, bold=True, anchor="lm")
    if current and start_ts <= now.timestamp() < end_ts:
        xx = xp(now)
        draw.polygon(((xx, bottom + 12), (xx - 7, bottom + 24), (xx + 7, bottom + 24)), fill=0)
    if not slots:
        _message(draw, ((left + right) / 2, (chart_top + bottom) / 2), "Price data unavailable", 28)
    if slots and max(slot.end.timestamp() for slot in slots) < (start_ts + end_ts) / 2:
        last = max(slot.end for slot in slots)
        center = (max(left, xp(last)) + right) / 2
        _message(
            draw,
            (center, (chart_top + bottom) / 2),
            f"No prices after {last.astimezone(now.tzinfo):%H:%M}",
            26,
        )
    if quarter_labels:
        local_hour = start.astimezone(now.tzinfo).replace(minute=0, second=0, microsecond=0)
        hour_ts = local_hour.timestamp()
        if hour_ts < start_ts:
            hour_ts += 3600
        while hour_ts < end_ts:
            moment = datetime.fromtimestamp(hour_ts, now.tzinfo)
            _text(draw, (xp(moment), top + height - 27), moment.strftime("%H:%M"), 22, anchor="mt")
            hour_ts += 3600
    else:
        duration_h = round((end_ts - start_ts) / 3600)
        for index in range(duration_h + 1):
            moment = datetime.fromtimestamp(start_ts + index * 3600, now.tzinfo)
            xx = left + index / duration_h * (right - left)
            if moment.hour % 3 == 0 or index == duration_h:
                _text(
                    draw,
                    (xx, bottom + 27),
                    moment.strftime("%H"),
                    22,
                    anchor="lt" if index == 0 else "rt" if index == duration_h else "mt",
                )
        # Only real local peaks qualify. Keep the highest candidate in each
        # civil hour, then let larger peaks claim nearby labels first.
        groups: dict[tuple[int, int, float | None], list[int]] = {}
        for index, slot in enumerate(slots):
            local = slot.start.astimezone(now.tzinfo)
            offset = local.utcoffset()
            groups.setdefault(
                (local.day, local.hour, offset.total_seconds() if offset is not None else None), []
            ).append(index)
        candidates = []
        for indices in groups.values():
            index = max(indices, key=lambda candidate: slots[candidate].buy)
            value = slots[index].buy
            previous = slots[index - 1].buy if index else float("-inf")
            following = slots[index + 1].buy if index + 1 < len(slots) else float("-inf")
            if value >= previous and value >= following and (value > previous or value > following):
                candidates.append(index)
        accepted: list[tuple[int, tuple[float, float, float, float], str]] = []
        for index in sorted(candidates, key=lambda item: (-slots[item].buy, item)):
            if any(abs(index - other) <= 2 for other, _, _ in accepted):
                continue
            peak = slots[index]
            label = f"{peak.buy * 100:.1f}"
            tw = draw.textlength(label, font=_font(22))
            xx = max(left, min(right - tw, xp(peak.start) - tw / 2))
            cap = max(peak.buy, peak.p90) if peak.forecast and peak.p90 is not None else peak.buy
            yy = max(chart_top - 1, yp(cap * 100) - 27)
            bounds = (xx - 4, yy - 2, xx + tw + 4, yy + 25)
            if any(
                bounds[0] < other[2]
                and bounds[2] > other[0]
                and bounds[1] < other[3]
                and bounds[3] > other[1]
                for _, other, _ in accepted
            ):
                continue
            accepted.append((index, bounds, label))
        for _, bounds, label in sorted(accepted):
            draw.rectangle(bounds, fill=255)
            _text(draw, (bounds[0] + 4, bounds[1] + 2), label, 22)


def render_dashboard(
    data: DashboardData,
    *,
    now: datetime,
    width: int = 1072,
    height: int = 1448,
) -> bytes:
    """Return an optimized 16-level grayscale PNG; caller supplies the clock."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if width < 1 or height < 1:
        raise ValueError("Image dimensions must be positive")
    now = now.astimezone(_zone(data.meta.time_zone))
    image = Image.new("L", (1072, 1448), 255)
    draw = ImageDraw.Draw(image)
    _text(draw, (32, 32), now.strftime("%A %d %B"), 30, bold=True)
    battery = "" if data.meta.battery is None else f"  ·  {data.meta.battery}%"
    _text(draw, (990 if battery else 1040, 34), f"Updated {now:%H:%M}{battery}", 24, anchor="rt")
    if data.meta.battery is not None:
        draw.rectangle((1004, 36, 1035, 55), outline=0, width=2)
        draw.rectangle((1036, 42, 1040, 49), fill=0)
        charge = max(0, min(100, data.meta.battery))
        if charge:
            draw.rectangle((1008, 40, 1008 + 23 * charge / 100, 51), fill=0)
    draw.line((32, 85, 1040, 85), fill=0, width=2)
    _weather(draw, data, now)
    _dishwasher(draw, data, now)
    today_start, today_end = day_bounds(now)
    tomorrow_start, tomorrow_end = day_bounds(now, 1)
    # UTC arithmetic: six actual hours, including a DST change.
    next_start = datetime.fromtimestamp(floor(now.timestamp() / 900) * 900, UTC)
    next_end = next_start + timedelta(hours=6)
    prices_fresh = any(slot.end.timestamp() > now.timestamp() for slot in data.prices.slots)
    relevant = tuple(
        slot
        for slot in data.prices.slots
        if prices_fresh and slot.end > today_start and slot.start < max(tomorrow_end, next_end)
    )
    limits = chart_limits(relevant)
    _chart(
        image,
        draw,
        data,
        now,
        "Next 6 hours",
        next_start,
        next_end,
        605,
        300,
        limits,
        quarter_labels=True,
    )
    _chart(image, draw, data, now, "Today", today_start, today_end, 923, 233, limits, current=True)
    _chart(image, draw, data, now, "Tomorrow", tomorrow_start, tomorrow_end, 1180, 233, limits)
    if image.size != (width, height):
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    image = image.point([round(value / 17) * 17 for value in range(256)])
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
