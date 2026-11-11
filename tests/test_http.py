"""Exercise the real HA routes with an unauthenticated loopback client."""

import logging
from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image

BASE = "/api/kindle_dash/test-only-token"


async def test_image_contract_preview_and_full_refresh(hass, configured):
    entry, client = configured
    runtime = entry.runtime_data
    response = await client.get(f"{BASE}/image.png?battery=83&charging=0&preview=1")
    assert response.status == 200
    assert response.content_type == "image/png"
    assert response.headers["Cache-Control"] == "no-store"
    assert int(response.headers["X-Sleep-Seconds"]) >= 120
    assert response.headers["X-Full-Refresh"] == "0"
    assert runtime.last_seen is None
    assert runtime.requests == 0
    image = Image.open(BytesIO(await response.read()))
    assert image.mode == "L" and image.size == (1072, 1448)
    assert not image.info.get("interlace")
    cadence = []
    for _ in range(8):
        response = await client.get(f"{BASE}/image.png?battery=82&charging=1&client=pytest")
        assert response.status == 200
        cadence.append(response.headers["X-Full-Refresh"])
    assert cadence == ["1", "0", "0", "1", "0", "0", "0", "1"]
    assert runtime.battery == 82 and runtime.charging is True
    status = await client.get(f"{BASE}/status.json")
    data = await status.json()
    assert data["battery"] == 82 and data["last_seen"] and data["next_expected"]
    assert data["schedule"] and "test-only-token" not in str(data)
    assert runtime.requests == 8
    assert (await client.get(f"{BASE}/image.png")).status == 200
    assert runtime.requests == 9


@pytest.mark.parametrize(
    "path",
    [
        "/api/kindle_dash/wrong/image.png",
        "/api/kindle_dash/wrong/status.json",
        "/api/kindle_dash/image.png",
        "/api/kindle_dash//status.json",
        "/api/kindle_dash/ä/image.png",
    ],
)
async def test_unknown_and_missing_tokens_return_404(configured, path):
    _, client = configured
    assert (await client.get(path)).status == 404


@pytest.mark.parametrize(
    "query",
    [
        "battery=-1",
        "battery=101",
        "battery=x",
        "battery=10.5",
        "charging=2",
        "preview=yes",
        "client=" + "x" * 129,
    ],
)
async def test_invalid_query_does_not_mutate_checkin(configured, query):
    entry, client = configured
    assert (await client.get(f"{BASE}/image.png?{query}")).status == 400
    assert entry.runtime_data.last_seen is None
    assert entry.runtime_data.requests == 0


async def test_render_failure_still_returns_error_png(configured, caplog):
    entry, client = configured
    with patch(
        "custom_components.kindle_dash.http.render_dashboard", side_effect=RuntimeError("test")
    ):
        response = await client.get(f"{BASE}/image.png?battery=20")
    assert response.status == 200
    assert response.headers["X-Sleep-Seconds"] == "300"
    assert entry.runtime_data.next_expected - entry.runtime_data.last_seen == __import__(
        "datetime"
    ).timedelta(minutes=5)
    image = Image.open(BytesIO(await response.read()))
    assert image.mode == "L" and image.size == (1072, 1448)
    assert image.getextrema() == (0, 255)
    assert "Unable to render" in caplog.text
    assert "test-only-token" not in caplog.text


async def test_view_debug_logging_redacts_even_wrong_tokens(configured, caplog):
    _, client = configured
    with caplog.at_level(logging.DEBUG, logger="homeassistant.helpers.http"):
        await client.get(f"{BASE}/status.json")
        await client.get("/api/kindle_dash/invalid-secret/status.json")
    assert "[redacted]" in caplog.text
    assert "test-only-token" not in caplog.text and "invalid-secret" not in caplog.text


async def test_unload_denies_token_and_reload_resets_full_refresh(hass, configured):
    entry, client = configured
    await client.get(f"{BASE}/image.png?battery=50")
    old = entry.runtime_data
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert old.cancel_deadline is None
    assert (await client.get(f"{BASE}/image.png")).status == 404
    assert await hass.config_entries.async_setup(entry.entry_id)
    response = await client.get(f"{BASE}/image.png")
    assert response.headers["X-Full-Refresh"] == "1"
    assert entry.runtime_data.battery == 50


async def test_empty_battery_is_still_a_check_in(configured):
    """A Kindle that cannot read its gauge must not look dead."""
    entry, client = configured
    response = await client.get(f"{BASE}/image.png?battery=&charging=&client=t")
    assert response.status == 200
    assert entry.runtime_data.last_seen is not None
    assert entry.runtime_data.battery is None
