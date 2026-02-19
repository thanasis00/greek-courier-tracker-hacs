"""Config flow for Greek Courier Tracker."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TRACKING_NUMBERS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_NAME,
    DOMAIN,
)


def _parse_tracking_numbers(value: str) -> list[str]:
    parts = [
        part.strip().upper()
        for part in re.split(r"[\n,]+", value or "")
        if part.strip()
    ]
    # Preserve order and remove duplicates
    return list(dict.fromkeys(parts))


class GreekCourierTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Greek Courier Tracker."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            tracking_numbers = _parse_tracking_numbers(user_input[CONF_TRACKING_NUMBERS])
            if not tracking_numbers:
                errors["base"] = "no_tracking_numbers"
            else:
                data = {
                    CONF_TRACKING_NUMBERS: tracking_numbers,
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    "name": DEFAULT_NAME,
                }
                return self.async_create_entry(title=DEFAULT_NAME, data=data)

        schema = vol.Schema(
            {
                vol.Required(CONF_TRACKING_NUMBERS): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return GreekCourierTrackerOptionsFlow(config_entry)


class GreekCourierTrackerOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Greek Courier Tracker."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            tracking_numbers = _parse_tracking_numbers(user_input[CONF_TRACKING_NUMBERS])
            if not tracking_numbers:
                errors["base"] = "no_tracking_numbers"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_TRACKING_NUMBERS: tracking_numbers,
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    },
                )

        existing_numbers = self.config_entry.options.get(
            CONF_TRACKING_NUMBERS,
            self.config_entry.data.get(CONF_TRACKING_NUMBERS, []),
        )
        existing_text = "\n".join(existing_numbers)
        schema = vol.Schema(
            {
                vol.Required(CONF_TRACKING_NUMBERS, default=existing_text): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL,
                        self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ),
                ): cv.positive_int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
