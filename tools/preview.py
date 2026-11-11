#!/usr/bin/env python3
"""Render fixture-based previews without importing or installing Home Assistant.

Example: uv run tools/preview.py --fixtures tests/fixtures \
    --now 2026-11-11T13:40:00+02:00 --all --out out
"""

import argparse
import json
import sys
import types
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from custom_components.kindle_dash.models import DashboardData

# An isolated namespace loads only the pure contract/parser/renderer. In particular
# Python must not execute the HA integration's __init__.py during offline previews.
_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = "_kindle_dash_preview"
if _PACKAGE not in sys.modules:
    package = types.ModuleType(_PACKAGE)
    package.__path__ = [str(_ROOT / "custom_components" / "kindle_dash")]
    sys.modules[_PACKAGE] = package

from importlib import import_module  # noqa: E402

_data = import_module(f"{_PACKAGE}.data")
_models = import_module(f"{_PACKAGE}.models")
_render = import_module(f"{_PACKAGE}.render")
SCENARIOS = (
    "normal",
    "tomorrow_published",
    "no_forecast",
    "negative_prices",
    "price_spike",
    "dishwasher_running",
    "dishwasher_disabled",
    "dishwasher_unknown",
    "all_unavailable",
)


def build_scenario(fixtures: Path, now: datetime, scenario: str) -> DashboardData:
    """Create a scenario from copies; original fixture files are never modified."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone offset")
    states = deepcopy(json.loads((fixtures / "states.json").read_text()))
    hourly = json.loads((fixtures / "forecast_hourly.json").read_text())
    daily = json.loads((fixtures / "forecast_daily.json").read_text())
    metadata = json.loads((fixtures / "meta.json").read_text())
    prices = states["sensor.nordpool_fi_day_ahead"]["attributes"]
    forecast = states["sensor.lvv_price_forecast"]["attributes"]
    dish = states["sensor.dishwasher_schedule"]["attributes"]
    running = states["binary_sensor.dishwasher_running_2"]
    if scenario == "tomorrow_published":
        zone = ZoneInfo(metadata.get("time_zone", "Europe/Helsinki"))
        start, end = _render.day_bounds(now.astimezone(zone), 1)
        prices["data_tomorrow"] = []
        source = forecast["data_today"]
        for index in range(round((end.timestamp() - start.timestamp()) / 900)):
            instant = start.astimezone(UTC) + timedelta(minutes=index * 15)
            prices["data_tomorrow"].append(
                {
                    "start": instant.astimezone(zone).isoformat(),
                    "end": (instant + timedelta(minutes=15)).astimezone(zone).isoformat(),
                    "buy": source[index % len(source)]["buy"],
                }
            )
        prices["tomorrow_valid"] = True
        states["binary_sensor.nordpool_tomorrow_prices_availability"]["state"] = "on"
    elif scenario == "no_forecast":
        states["sensor.lvv_price_forecast"]["state"] = "unavailable"
    elif scenario in {"negative_prices", "price_spike"}:
        for rows in (prices["data_today"], forecast["data_today"][:96]):
            for index, row in enumerate(rows):
                if scenario == "negative_prices" and 12 <= index <= 35:
                    row["buy"] = -0.03 - 0.002 * (index % 4)
                    if "p10" in row:
                        row["p10"], row["p90"] = row["buy"] - 0.03, row["buy"] + 0.03
                elif scenario == "price_spike" and 50 <= index <= 56:
                    row["buy"] = 0.6 + 0.1 * (index % 3)
                    if "p90" in row:
                        row["p90"] = min(0.8, row["buy"] + 0.05)
    elif scenario == "dishwasher_running":
        dish["running"], running["state"] = True, "on"
        dish["remaining_minutes"] = 92
        start = now.astimezone(UTC) - timedelta(minutes=40)
        end = now.astimezone(UTC) + timedelta(minutes=92)
        dish["periods"] = [
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "source": "grid",
                "avg_cost": 0.10392,
            }
        ]
    elif scenario == "dishwasher_disabled":
        dish["enabled"] = False
        dish["periods"] = []
    elif scenario == "dishwasher_unknown":
        states["sensor.dishwasher_schedule"]["state"] = "unknown"
        running["state"] = "unknown"
    elif scenario == "all_unavailable":
        for entity in states.values():
            entity["state"] = "unavailable"
        hourly, daily = {}, {}
    meta = _models.Meta(time_zone=metadata.get("time_zone", "Europe/Helsinki"), battery=83)
    return _data.parse_dashboard(states, hourly, daily, meta=meta)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=_ROOT / "tests" / "fixtures")
    parser.add_argument(
        "--now",
        type=datetime.fromisoformat,
        default=datetime(2026, 11, 11, 13, 40, tzinfo=ZoneInfo("Europe/Helsinki")),
    )
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    parser.add_argument(
        "--next-wake-minutes",
        type=int,
        default=30,
        help="Viewing-window minutes for dishwasher delay rounding (default: 30)",
    )
    parser.add_argument("--all", action="store_true", help="Render all scenarios into --out")
    args = parser.parse_args()
    scenarios = SCENARIOS if args.all else (args.scenario,)
    if args.all or args.out.suffix.lower() != ".png":
        args.out.mkdir(parents=True, exist_ok=True)
    for scenario in scenarios:
        output = args.out / f"{scenario}.png" if args.all or args.out.is_dir() else args.out
        output.parent.mkdir(parents=True, exist_ok=True)
        data = build_scenario(args.fixtures, args.now, scenario)
        output.write_bytes(
            _render.render_dashboard(
                data,
                now=args.now,
                next_wake=args.now + timedelta(minutes=args.next_wake_minutes),
            )
        )
        print(output)


if __name__ == "__main__":
    main()
