"""The fixed Kindle HTTP contract; no HA auth is available on the reader."""

from __future__ import annotations

import hmac
import logging
import re
from functools import partial
from io import BytesIO
from typing import TYPE_CHECKING

from aiohttp import web
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.http import HomeAssistantView
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .ha_data import async_dashboard_data
from .render import render_dashboard

if TYPE_CHECKING:
    from .runtime import KindleDashRuntime

_LOGGER = logging.getLogger(__name__)
_TOKEN_PATH = re.compile(r"(/api/kindle_dash/)[^/\s?]+(/(?:image\.png|status\.json))")


class _RedactPath(logging.Filter):
    """HA's own view debug logger includes paths; redact these bearer paths too."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _TOKEN_PATH.sub(r"\1[redacted]\2", message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        return True


@callback
def async_redact_http_logs() -> None:
    """Do not put a bearer credential into HA/aiohttp request logs."""
    for name in (
        "homeassistant.helpers.http",
        "homeassistant.components.http.view",
        "aiohttp.access",
    ):
        logger = logging.getLogger(name)
        if not any(isinstance(item, _RedactPath) for item in logger.filters):
            logger.addFilter(_RedactPath())


def render_error() -> bytes:
    """Last-resort PNG: independent of data and bundled font availability."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("L", (1072, 1448), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=36)
    draw.rectangle((32, 32, 1040, 1416), outline=0, width=6)
    draw.multiline_text(
        (70, 100),
        "Dashboard temporarily unavailable\n\nRetrying in 5 minutes.",
        fill=0,
        font=font,
        spacing=24,
    )
    output = BytesIO()
    image.point([round(value / 17) * 17 for value in range(256)]).save(output, "PNG", interlace=0)
    return output.getvalue()


class _KindleView(HomeAssistantView):
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def runtime(self, token: str) -> KindleDashRuntime:
        """Constant-time credential comparison, loaded entries only."""
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            valid = hmac.compare_digest(
                str(entry.data.get("token", "")).encode("utf-8"),
                token.encode("utf-8"),
            )
            if valid and entry.state is ConfigEntryState.LOADED:
                return entry.runtime_data
        raise web.HTTPNotFound


class ImageView(_KindleView):
    """Render on demand in the executor; previews never mutate monitoring state."""

    url = "/api/kindle_dash/{token}/image.png"
    name = "api:kindle_dash:image"

    async def get(self, request: web.Request, token: str) -> web.Response:
        """Return one grayscale portrait and absolute-time sleep instructions."""
        runtime = self.runtime(token)
        query = request.query
        battery = None
        charging = None
        # The Kindle sends empty values when it cannot read its gauge; that is
        # still a check-in, just without a battery reading.
        is_kindle = "battery" in query or "client" in query
        if query.get("battery"):
            value = query["battery"]
            if (
                len(value) > 3
                or not value.isascii()
                or not value.isdigit()
                or not 0 <= int(value) <= 100
            ):
                raise web.HTTPBadRequest(text="battery must be an integer in 0..100")
            battery = int(value)
        if query.get("charging"):
            if query["charging"] not in ("0", "1"):
                raise web.HTTPBadRequest(text="charging must be 0 or 1")
            charging = query["charging"] == "1"
        if "preview" in query and query["preview"] not in ("0", "1"):
            raise web.HTTPBadRequest(text="preview must be 0 or 1")
        if "client" in query and (
            len(query["client"]) > 128 or any(ord(c) < 32 for c in query["client"])
        ):
            raise web.HTTPBadRequest(text="client must contain at most 128 printable characters")
        preview = query.get("preview") == "1"
        async with runtime.lock:
            now = dt_util.utcnow()
            wake = runtime.wake_at(now)
            sleep = max(60, round((dt_util.as_utc(wake) - now).total_seconds()))
            try:
                data = await async_dashboard_data(self.hass, runtime, battery)
                local_now = now.astimezone(dt_util.get_time_zone(self.hass.config.time_zone))
                body = await self.hass.async_add_executor_job(
                    partial(render_dashboard, data, now=local_now),
                )
            except Exception:  # A valid error PNG is part of the wire contract.
                _LOGGER.exception("Unable to render Kindle dashboard")
                body = await self.hass.async_add_executor_job(render_error)
                sleep = 300
            full = False
            if not preview:
                runtime.requests += 1
                full = (
                    runtime.requests == 1
                    or runtime.requests % int(runtime.options["full_refresh_every"]) == 0
                )
                if is_kindle:
                    await runtime.async_check_in(now, battery, charging, sleep)
            return web.Response(
                body=body,
                content_type="image/png",
                headers={
                    "X-Sleep-Seconds": str(sleep),
                    "X-Full-Refresh": str(int(full)),
                    "Cache-Control": "no-store",
                },
            )


class StatusView(_KindleView):
    """Debug snapshot without touching the cadence or monitoring state."""

    url = "/api/kindle_dash/{token}/status.json"
    name = "api:kindle_dash:status"

    async def get(self, request: web.Request, token: str) -> web.Response:
        """Return only monitoring and scheduling information, never the token."""
        runtime = self.runtime(token)
        return self.json(
            {
                **runtime.snapshot(),
                "problem": runtime.problem,
                "schedule": runtime.options["schedule"],
                "default_interval": runtime.options["default_interval"],
                "next_wake": runtime.wake_at(dt_util.utcnow()).isoformat(),
            },
            headers={"Cache-Control": "no-store"},
        )
