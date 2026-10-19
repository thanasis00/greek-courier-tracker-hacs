"""Config flow for Greek Courier Tracker."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv

# Try to import selectors, fall back to dict representation for testing
try:
    from homeassistant.helpers.selectors import SelectSelector, SelectSelectorConfig, SelectSelectorMode
    HAS_SELECTORS = True
except ImportError:
    HAS_SELECTORS = False
    SelectSelector = lambda x: x  # type: ignore
    SelectSelectorConfig = None  # type: ignore
    SelectSelectorMode = None  # type: ignore

from .const import (
    CONF_AUTO_REMOVE_DELIVERED,
    CONF_SCAN_INTERVAL,
    CONF_TRACKING_NUMBERS,
    CONF_TRACKING_NAME,
    CONF_STOP_TRACKING_DELIVERED,
    CONF_COURIER,
    DEFAULT_AUTO_REMOVE_DELIVERED,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_NAME,
    DOMAIN,
    CourierType,
    COURIER_NAMES,
)

_LOGGER = logging.getLogger(__name__)

# Courier list for dropdown (auto first, then alphabetical)
COURIER_LIST = [
    (CourierType.AUTO, COURIER_NAMES[CourierType.AUTO]),
    (CourierType.ACS, COURIER_NAMES[CourierType.ACS]),
    (CourierType.BOX_NOW, COURIER_NAMES[CourierType.BOX_NOW]),
    (CourierType.COURIER_CENTER, COURIER_NAMES[CourierType.COURIER_CENTER]),
    (CourierType.ELTA, COURIER_NAMES[CourierType.ELTA]),
    (CourierType.GENIKI, COURIER_NAMES[CourierType.GENIKI]),
    (CourierType.SKROUTZ, COURIER_NAMES[CourierType.SKROUTZ]),
    (CourierType.SPEEDEX, COURIER_NAMES[CourierType.SPEEDEX]),
    (CourierType.SVUUM, COURIER_NAMES[CourierType.SVUUM]),
]


def _migrate_tracking_data(data: list) -> list[dict[str, Any]]:
    """Migrate old tracking number format to include courier field."""
    if not data:
        return []

    # Version 1 -> 2: list of strings to list of dicts
    if isinstance(data[0], str):
        _LOGGER.info("Migrating tracking numbers from old format to new format")
        return [
            {
                "tracking_number": number,
                "name": number,
                "stop_tracking_delivered": False,
                "courier": CourierType.AUTO,
            }
            for number in data
        ]

    # Version 2 -> 3: add courier field if missing
    for item in data:
        if isinstance(item, dict) and "courier" not in item:
            item["courier"] = CourierType.AUTO

    return data


def _parse_tracking_numbers(value: str, courier: str = CourierType.AUTO) -> list[dict[str, Any]]:
    """Parse tracking numbers from user input.

    Args:
        value: Comma or newline separated tracking numbers (with optional names after colon)
        courier: Courier type to use (default: AUTO)

    Format examples:
        - Simple: SE123456789GR
        - With name: SE123456789GR:My Package
        - Multiple: SE123456789GR:Package 1, ACS1234567890:Package 2

    Returns a list of dicts with keys:
    - tracking_number: str (uppercase)
    - name: str (from input or defaults to tracking number)
    - stop_tracking_delivered: bool (default False)
    - courier: str (from parameter or AUTO)
    """
    lines = re.split(r"[,\n]+", value or "")
    
    result = []
    seen_numbers = set()
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if line contains a name (format: "TRACKING:NAME")
        if ":" in line:
            parts = line.split(":", 1)
            tracking_number = parts[0].strip().upper()
            name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else tracking_number
        else:
            tracking_number = line.upper()
            name = tracking_number
        
        # Skip duplicates
        if tracking_number in seen_numbers:
            continue
        seen_numbers.add(tracking_number)
        
        result.append({
            "tracking_number": tracking_number,
            "name": name,
            "stop_tracking_delivered": False,
            "courier": courier,
        })
    
    return result


class GreekCourierTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Greek Courier Tracker."""

    VERSION = 3  # Version 3: added courier selection

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return GreekCourierTrackerOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        _LOGGER.info("Config flow - async_step_user called")
        errors: dict[str, str] = {}

        # One entry holds all tracking numbers; more are added from Configure,
        # the dashboard card, the Shipments to-do list or the add_tracking action
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            _LOGGER.debug("User input received: %s", user_input)
            tracking_number = user_input.get(CONF_TRACKING_NUMBERS, "").strip().upper()
            name = user_input.get(CONF_TRACKING_NAME, "").strip()
            selected_courier = user_input.get(CONF_COURIER, CourierType.AUTO)
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

            # The first tracking number is optional
            tracking_data = []
            if tracking_number:
                tracking_data.append({
                    "tracking_number": tracking_number,
                    "name": name if name else tracking_number,
                    "stop_tracking_delivered": False,
                    "courier": selected_courier,
                })
            _LOGGER.info("Parsed tracking data: %s", tracking_data)

            data = {
                CONF_TRACKING_NUMBERS: tracking_data,
                CONF_SCAN_INTERVAL: scan_interval,
                "name": DEFAULT_NAME,
            }
            _LOGGER.info("Creating config entry with data: %s", data)
            return self.async_create_entry(title=DEFAULT_NAME, data=data)

        _LOGGER.debug("Showing form to user")
        
        # Create courier selector
        if HAS_SELECTORS:
            courier_selector = SelectSelector(
                SelectSelectorConfig(
                    options=[{"value": code, "label": name} for code, name in COURIER_LIST],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            # Fallback for testing: use simple vol.In with list of codes
            courier_selector = vol.In([code for code, _ in COURIER_LIST])
        
        schema = vol.Schema(
            {
                vol.Optional(CONF_TRACKING_NUMBERS, default=""): str,
                vol.Optional(CONF_TRACKING_NAME, default=""): str,
                vol.Optional(CONF_COURIER, default=CourierType.AUTO): courier_selector,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_migrate_entry(
        self,
        config_entry: config_entries.ConfigEntry,
    ) -> bool:
        """Migrate old entry to new version."""
        _LOGGER.info(
            "Migrating config entry from version %s to %s",
            config_entry.version,
            self.VERSION,
        )

        if config_entry.version < 3:
            old_data = dict(config_entry.data)
            old_options = dict(config_entry.options)

            # Migrate tracking_numbers in data
            if CONF_TRACKING_NUMBERS in old_data:
                old_data[CONF_TRACKING_NUMBERS] = _migrate_tracking_data(
                    old_data[CONF_TRACKING_NUMBERS]
                )

            # Migrate tracking_numbers in options
            if CONF_TRACKING_NUMBERS in old_options:
                old_options[CONF_TRACKING_NUMBERS] = _migrate_tracking_data(
                    old_options[CONF_TRACKING_NUMBERS]
                )

            self.hass.config_entries.async_update_entry(
                config_entry,
                data=old_data,
                options=old_options,
                version=self.VERSION,
            )

            _LOGGER.info("Migration to version %s complete", self.VERSION)
            return True

        return False


class GreekCourierTrackerOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Greek Courier Tracker."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        super().__init__()
        self._config_entry = config_entry
        self._selected_tracking: str | None = None
        _LOGGER.debug("Options flow initialized for entry: %s", config_entry.entry_id)

        # Migrate old data format
        self._migrate_data_if_needed()

    @property
    def config_entry(self) -> config_entries.ConfigEntry:
        """Return the config entry."""
        return self._config_entry

    def _migrate_data_if_needed(self) -> None:
        """Migrate old tracking number format to include courier field."""
        existing_numbers = self._config_entry.options.get(
            CONF_TRACKING_NUMBERS,
            self.config_entry.data.get(CONF_TRACKING_NUMBERS, []),
        )

        # Check if migration is needed
        if existing_numbers and isinstance(existing_numbers[0], str):
            _LOGGER.info("Migrating tracking numbers to new format with names")
            self.migrated_data = [
                {
                    "tracking_number": number,
                    "name": number,
                    "stop_tracking_delivered": False,
                    "courier": CourierType.AUTO,
                }
                for number in existing_numbers
            ]
        else:
            # Work on copies: changing the entry's own list in place makes the
            # saved options look unchanged, so Home Assistant would skip saving
            self.migrated_data = [
                {"courier": CourierType.AUTO, **item} if isinstance(item, dict) else item
                for item in existing_numbers
            ]

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show the options menu with the tracked numbers."""
        _LOGGER.info("Options flow - async_step_init called")

        menu_options = ["add_tracking"]
        if self.migrated_data:
            menu_options += ["edit_select", "delete_select"]
        menu_options.append("settings")

        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
            description_placeholders={
                "tracking_list": self._format_tracking_list(self._tracking_list()),
            },
        )

    async def async_step_edit_select(self, user_input: dict[str, Any] | None = None):
        """Choose the tracking number to edit."""
        if user_input is not None:
            self._selected_tracking = user_input["tracking_number"]
            return await self.async_step_edit_tracking()

        schema = vol.Schema({
            vol.Required("tracking_number"): self._tracking_selector(),
        })
        return self.async_show_form(step_id="edit_select", data_schema=schema)

    async def async_step_delete_select(self, user_input: dict[str, Any] | None = None):
        """Choose the tracking numbers to stop tracking."""
        if user_input is not None:
            selected = user_input.get("tracking_numbers") or []
            if isinstance(selected, str):
                selected = [selected]

            self.migrated_data = [
                item for item in self.migrated_data
                if (item.get("tracking_number", item) if isinstance(item, dict) else item) not in selected
            ]
            _LOGGER.info("Deleted tracking numbers: %s", selected)
            return self.async_create_entry(title="", data=self._options_data())

        schema = vol.Schema({
            vol.Required("tracking_numbers"): self._tracking_selector(multiple=True),
        })
        return self.async_show_form(step_id="delete_select", data_schema=schema)

    async def async_step_settings(self, user_input: dict[str, Any] | None = None):
        """Change the scan interval and the clean-up of delivered shipments."""
        if user_input is not None:
            data = self._options_data(scan_interval=user_input[CONF_SCAN_INTERVAL])
            data[CONF_AUTO_REMOVE_DELIVERED] = user_input.get(CONF_AUTO_REMOVE_DELIVERED, 0)
            return self.async_create_entry(title="", data=data)

        auto_remove = self.config_entry.options.get(CONF_AUTO_REMOVE_DELIVERED, DEFAULT_AUTO_REMOVE_DELIVERED)
        schema = vol.Schema({
            vol.Required(CONF_SCAN_INTERVAL, default=self._scan_interval()): cv.positive_int,
            vol.Required(CONF_AUTO_REMOVE_DELIVERED, default=auto_remove): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=365)
            ),
        })
        return self.async_show_form(step_id="settings", data_schema=schema)

    def _scan_interval(self) -> int:
        """Return the current scan interval."""
        return self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

    def _options_data(self, scan_interval: int | None = None) -> dict[str, Any]:
        """Build the options to save (other settings are kept)."""
        return {
            **(self.config_entry.options or {}),
            CONF_TRACKING_NUMBERS: self.migrated_data,
            CONF_SCAN_INTERVAL: scan_interval if scan_interval is not None else self._scan_interval(),
        }

    def _tracking_list(self) -> list[dict[str, Any]]:
        """Return the tracked numbers with display names."""
        tracking_list = []
        for item in self.migrated_data:
            tracking_num = item.get("tracking_number", item) if isinstance(item, dict) else item
            name = item.get("name", tracking_num) if isinstance(item, dict) else tracking_num
            stop_tracking = item.get("stop_tracking_delivered", False) if isinstance(item, dict) else False
            courier = item.get("courier", CourierType.AUTO) if isinstance(item, dict) else CourierType.AUTO
            courier_name = COURIER_NAMES.get(courier, courier)

            tracking_list.append({
                "tracking_number": tracking_num,
                "name": name,
                "stop_tracking_delivered": stop_tracking,
                "courier": courier_name,
            })
        return tracking_list

    def _tracking_selector(self, multiple: bool = False):
        """Build a selector with the tracked numbers."""
        options = {
            item["tracking_number"]: (
                f"{item['name']} ({item['tracking_number']})"
                if item["name"] != item["tracking_number"]
                else item["tracking_number"]
            )
            for item in self._tracking_list()
        }

        if HAS_SELECTORS:
            return SelectSelector(
                SelectSelectorConfig(
                    options=[{"value": value, "label": label} for value, label in options.items()],
                    mode=SelectSelectorMode.DROPDOWN,
                    multiple=multiple,
                )
            )
        # Fallback for testing
        return cv.multi_select(options) if multiple else vol.In(list(options))

    async def async_step_add_tracking(self, user_input: dict[str, Any] | None = None):
        """Add a new tracking number."""
        errors: dict[str, str] = {}

        if user_input is not None:
            tracking_number = user_input.get("tracking_number", "").strip().upper()
            name = user_input.get("name", "").strip()
            stop_tracking_delivered = user_input.get("stop_tracking_delivered", False)
            courier = user_input.get("courier", "auto")

            if not tracking_number:
                errors["tracking_number"] = "tracking_number_required"
            else:
                # Check if tracking number already exists
                for item in self.migrated_data:
                    existing_number = item.get("tracking_number", item) if isinstance(item, dict) else item
                    if existing_number == tracking_number:
                        errors["tracking_number"] = "tracking_number_exists"
                        break

                if not errors:
                    display_name = name if name else tracking_number

                    new_tracking = {
                        "tracking_number": tracking_number,
                        "name": display_name,
                        "stop_tracking_delivered": stop_tracking_delivered,
                        "courier": courier,
                    }
                    self.migrated_data.append(new_tracking)

                    _LOGGER.info("Added new tracking: %s", new_tracking)

                    # Save and go back to main menu
                    data = self._options_data()
                    return self.async_create_entry(title="", data=data)

        # Create courier selector
        if HAS_SELECTORS:
            courier_selector = SelectSelector(
                SelectSelectorConfig(
                    options=[{"value": code, "label": name} for code, name in COURIER_LIST],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            # Fallback for testing: use simple vol.In with list of codes
            courier_selector = vol.In([code for code, _ in COURIER_LIST])

        schema = vol.Schema({
            vol.Required("tracking_number"): str,
            vol.Optional("name", default=""): str,
            vol.Optional("courier", default="auto"): courier_selector,
            vol.Optional("stop_tracking_delivered", default=False): bool,
        })

        return self.async_show_form(
            step_id="add_tracking",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_edit_tracking(self, user_input: dict[str, Any] | None = None, tracking_number: str | None = None):
        """Edit an existing tracking number."""
        errors: dict[str, str] = {}

        # The number comes from edit_select; the form submit doesn't pass it again
        if tracking_number is not None:
            self._selected_tracking = tracking_number
        tracking_number = self._selected_tracking

        # Find the tracking item
        tracking_item = None
        tracking_index = None
        for i, item in enumerate(self.migrated_data):
            existing_number = item.get("tracking_number", item) if isinstance(item, dict) else item
            if existing_number == tracking_number:
                tracking_item = item
                tracking_index = i
                break

        if tracking_item is None:
            return await self.async_step_init()

        if user_input is not None:
            new_name = user_input.get("name", "").strip()
            new_stop_tracking = user_input.get("stop_tracking_delivered", False)
            new_courier = user_input.get("courier", "auto")

            # Update the tracking item
            self.migrated_data[tracking_index] = {
                "tracking_number": tracking_number,
                "name": new_name if new_name else tracking_number,
                "stop_tracking_delivered": new_stop_tracking,
                "courier": new_courier,
            }

            _LOGGER.info("Updated tracking: %s", self.migrated_data[tracking_index])

            # Save and go back to main menu
            data = self._options_data()
            return self.async_create_entry(title="", data=data)

        # Show edit form with current values
        current_name = tracking_item.get("name", tracking_number) if isinstance(tracking_item, dict) else tracking_number
        current_stop_tracking = tracking_item.get("stop_tracking_delivered", False) if isinstance(tracking_item, dict) else False
        current_courier = tracking_item.get("courier", "auto") if isinstance(tracking_item, dict) else "auto"

        # Create courier selector
        if HAS_SELECTORS:
            courier_selector = SelectSelector(
                SelectSelectorConfig(
                    options=[{"value": code, "label": name} for code, name in COURIER_LIST],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            # Fallback for testing: use simple vol.In with list of codes
            courier_selector = vol.In([code for code, _ in COURIER_LIST])

        schema = vol.Schema({
            vol.Required("name", default=current_name): str,
            vol.Optional("courier", default=current_courier): courier_selector,
            vol.Optional("stop_tracking_delivered", default=current_stop_tracking): bool,
        })

        return self.async_show_form(
            step_id="edit_tracking",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "tracking_number": tracking_number,
            }
        )

    def _format_tracking_list(self, tracking_list: list[dict]) -> str:
        """Format tracking list for display in UI."""
        if not tracking_list:
            return "–"

        lines = []
        for item in tracking_list:
            name = item.get("name", item.get("tracking_number", "Unknown"))
            tracking_num = item.get("tracking_number", "Unknown")
            courier = item.get("courier", "Auto")

            label = f"{name} ({tracking_num})" if name != tracking_num else tracking_num
            lines.append(f"• {label} · {courier}")

        return "\n".join(lines)
