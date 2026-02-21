"""Config flow for Greek Courier Tracker."""

from __future__ import annotations

import logging
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

_LOGGER = logging.getLogger(__name__)


def _parse_tracking_numbers(value: str) -> list[str]:
    """Parse tracking numbers from user input."""
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
        _LOGGER.info("Config flow - async_step_user called")
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug("User input received: %s", user_input)
            tracking_numbers = _parse_tracking_numbers(user_input[CONF_TRACKING_NUMBERS])
            _LOGGER.info("Parsed tracking numbers: %s", tracking_numbers)

            if not tracking_numbers:
                _LOGGER.error("No tracking numbers provided")
                errors["base"] = "no_tracking_numbers"
            else:
                data = {
                    CONF_TRACKING_NUMBERS: tracking_numbers,
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    "name": DEFAULT_NAME,
                }
                _LOGGER.info("Creating config entry with data: %s", data)
                return self.async_create_entry(title=DEFAULT_NAME, data=data)

        _LOGGER.debug("Showing form to user")
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
        _LOGGER.debug("Getting options flow for entry: %s", config_entry.entry_id)
        return GreekCourierTrackerOptionsFlow(config_entry)


class GreekCourierTrackerOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Greek Courier Tracker."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        _LOGGER.debug("Options flow initialized for entry: %s", config_entry.entry_id)

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the options."""
        _LOGGER.info("Options flow - async_step_init called")
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug("Options user input received: %s", user_input)
            tracking_numbers = _parse_tracking_numbers(user_input[CONF_TRACKING_NUMBERS])
            _LOGGER.info("Parsed tracking numbers: %s", tracking_numbers)

            if not tracking_numbers:
                _LOGGER.error("No tracking numbers provided in options")
                errors["base"] = "no_tracking_numbers"
            else:
                data = {
                    CONF_TRACKING_NUMBERS: tracking_numbers,
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                }
                _LOGGER.info("Updating options with data: %s", data)
                return self.async_create_entry(title="", data=data)

        existing_numbers = self.config_entry.options.get(
            CONF_TRACKING_NUMBERS,
            self.config_entry.data.get(CONF_TRACKING_NUMBERS, []),
        )
        existing_text = "\n".join(existing_numbers)
        _LOGGER.debug("Existing tracking numbers: %s", existing_numbers)

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
