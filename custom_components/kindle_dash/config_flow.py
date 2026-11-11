"""UI-only configuration using HA's current selector and reload APIs."""

from __future__ import annotations

import secrets
from typing import Any

import probatio
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DEFAULT_ENTITIES, DEFAULT_OPTIONS, DOMAIN
from .schedule import parse_schedule

_LIMITS = {
    "default_interval": (5, 720),
    "offset_seconds": (0, 900),
    "full_refresh_every": (1, 100),
    "grace_minutes": (0, 1440),
}


def options_schema(values: dict[str, Any], *, options: bool = False) -> probatio.Schema:
    """Use domain-filtered entities, numeric controls, and multiline schedules."""
    fields: dict[Any, Any] = {}
    for key in DEFAULT_ENTITIES:
        domain = (
            "weather"
            if key == "weather_entity"
            else (
                "binary_sensor"
                if key in ("tomorrow_available_entity", "dishwasher_running_entity")
                else "sensor"
            )
        )
        # Optional selections can be cleared; sources missing from HA are tolerated.
        fields[probatio.Optional(key, description={"suggested_value": values.get(key)})] = (
            selector.EntitySelector(selector.EntitySelectorConfig(filter={"domain": domain}))
        )
    fields[probatio.Required("schedule", default=values["schedule"])] = selector.TextSelector(
        selector.TextSelectorConfig(multiline=True),
    )
    for key, (minimum, maximum) in _LIMITS.items():
        fields[probatio.Required(key, default=values[key])] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=minimum,
                max=maximum,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
            ),
        )
    if options:
        fields[probatio.Optional("regenerate_token", default=False)] = selector.BooleanSelector()
    return probatio.Schema(fields)


def validated_options(user_input: dict[str, Any]) -> dict[str, Any]:
    """Reject invalid schedules and bounds with a translated form error."""
    values = {
        **DEFAULT_OPTIONS,
        **{key: value for key, value in user_input.items() if key in DEFAULT_OPTIONS},
    }
    # Omitted optional selectors mean the user cleared them, not reset to default.
    for key in DEFAULT_ENTITIES:
        values[key] = user_input.get(key, "")
        expected = DEFAULT_ENTITIES[key].split(".", 1)[0]
        if values[key] and (
            not isinstance(values[key], str) or values[key].split(".", 1)[0] != expected
        ):
            raise ValueError(f"{key} must select a {expected} entity")
    for key, (minimum, maximum) in _LIMITS.items():
        value = values[key]
        if (
            isinstance(value, bool)
            or not float(value).is_integer()
            or not minimum <= value <= maximum
        ):
            raise ValueError("Numeric options must be whole numbers within the displayed range")
        values[key] = int(value)
    parse_schedule(values["schedule"], values["default_interval"])
    return values


class KindleDashConfigFlow(ConfigFlow, domain=DOMAIN):
    """Only one Kindle dashboard may be configured."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Generate the credential only after validating the user's choices."""
        errors: dict[str, str] = {}
        details = ""
        if user_input is not None:
            try:
                options = validated_options(user_input)
            except (ValueError, TypeError) as err:
                errors["base"] = "invalid_options"
                details = str(err)
            else:
                return self.async_create_entry(
                    title="Kindle dashboard",
                    data={"token": secrets.token_urlsafe(32)},
                    options=options,
                )
        return self.async_show_form(
            step_id="user",
            data_schema=options_schema({**DEFAULT_OPTIONS, **(user_input or {})}),
            errors=errors,
            description_placeholders={"error": details},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KindleDashOptionsFlow:
        """The framework supplies config_entry; do not assign it in __init__."""
        return KindleDashOptionsFlow()


class KindleDashOptionsFlow(OptionsFlowWithReload):
    """HA reloads changed options without an entry update listener."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the existing credential as read-only descriptive information."""
        errors: dict[str, str] = {}
        details = ""
        if user_input is not None:
            try:
                options = validated_options(user_input)
            except (ValueError, TypeError) as err:
                errors["base"] = "invalid_options"
                details = str(err)
            else:
                generation = int(self.config_entry.options.get("token_generation", 0))
                if user_input.get("regenerate_token"):
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data={**self.config_entry.data, "token": secrets.token_urlsafe(32)},
                    )
                    generation += 1
                # Changing only the token must also trigger OptionsFlowWithReload.
                options["token_generation"] = generation
                return self.async_create_entry(data=options)
        token = self.config_entry.data["token"]
        return self.async_show_form(
            step_id="init",
            data_schema=options_schema(
                {**DEFAULT_OPTIONS, **self.config_entry.options, **(user_input or {})},
                options=True,
            ),
            errors=errors,
            description_placeholders={
                "token": token,
                "image_path": f"/api/kindle_dash/{token}/image.png",
                "status_path": f"/api/kindle_dash/{token}/status.json",
                "error": details,
            },
        )
