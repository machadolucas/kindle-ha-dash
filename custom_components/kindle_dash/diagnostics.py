"""Export diagnostics without bearer tokens or token-bearing paths."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import KindleDashConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: KindleDashConfigEntry,
) -> dict[str, Any]:
    """Monitoring state contains no credential or client-provided string."""
    return {
        "entry": async_redact_data(
            {"data": dict(entry.data), "options": dict(entry.options)}, {"token"}
        ),
        "monitoring": entry.runtime_data.snapshot(),
        "problem": entry.runtime_data.problem,
    }
