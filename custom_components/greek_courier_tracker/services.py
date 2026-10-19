"""Actions (services) for Greek Courier Tracker."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import COURIER_NAMES, DOMAIN, CourierType
from .owners import async_resolve_owner
from .tracking import (
    TrackingNumberExistsError,
    TrackingNumberNotFoundError,
    add_tracking_item,
    get_tracking_data,
    normalize_tracking_number,
    remove_tracking_items,
    save_tracking_data,
    set_tracking_owner,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_ADD_TRACKING = "add_tracking"
SERVICE_REMOVE_TRACKING = "remove_tracking"
SERVICE_SET_OWNER = "set_owner"

ATTR_TRACKING_NUMBER = "tracking_number"
ATTR_NAME = "name"
ATTR_COURIER = "courier"
ATTR_STOP_TRACKING_DELIVERED = "stop_tracking_delivered"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_OWNER = "owner"

ADD_TRACKING_SCHEMA = vol.Schema({
    vol.Required(ATTR_TRACKING_NUMBER): cv.string,
    vol.Optional(ATTR_NAME): cv.string,
    vol.Optional(ATTR_COURIER, default=CourierType.AUTO): vol.In([code.value for code in COURIER_NAMES]),
    vol.Optional(ATTR_STOP_TRACKING_DELIVERED, default=False): cv.boolean,
    # Person entity or user ID; left out = whoever runs the action, empty = shared
    vol.Optional(ATTR_OWNER): vol.Any(None, cv.string),
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
})

REMOVE_TRACKING_SCHEMA = vol.Schema({
    vol.Required(ATTR_TRACKING_NUMBER): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
})

SET_OWNER_SCHEMA = vol.Schema({
    vol.Required(ATTR_TRACKING_NUMBER): vol.All(cv.ensure_list, [cv.string]),
    # Person entity or user ID; left out or empty = shared
    vol.Optional(ATTR_OWNER): vol.Any(None, cv.string),
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
})


def get_target_entry(hass: HomeAssistant, entry_id: str | None = None) -> ConfigEntry:
    """Return the config entry to change (the given one, else the first loaded one)."""
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(f"Config entry {entry_id} is not a Greek Courier Tracker entry")
        return entry

    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("Set up the Greek Courier Tracker integration first")
    loaded = [entry for entry in entries if entry.state is ConfigEntryState.LOADED]
    return (loaded or entries)[0]


async def async_add_tracking(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the add_tracking action."""
    entry = get_target_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    tracking_number = normalize_tracking_number(call.data[ATTR_TRACKING_NUMBER])
    if not tracking_number:
        raise ServiceValidationError("Enter a tracking number")

    if ATTR_OWNER in call.data:
        owner = await async_resolve_owner(hass, call.data[ATTR_OWNER])
    else:
        owner = call.context.user_id

    try:
        tracking_data = add_tracking_item(
            get_tracking_data(entry),
            tracking_number,
            name=call.data.get(ATTR_NAME),
            courier=call.data.get(ATTR_COURIER, CourierType.AUTO),
            stop_tracking_delivered=call.data.get(ATTR_STOP_TRACKING_DELIVERED, False),
            owner=owner,
        )
    except TrackingNumberExistsError as err:
        raise ServiceValidationError(f"{tracking_number} is already tracked") from err

    _LOGGER.info("Adding tracking number %s via action", tracking_number)
    save_tracking_data(hass, entry, tracking_data)


async def async_remove_tracking(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the remove_tracking action."""
    entry = get_target_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))

    try:
        tracking_data = remove_tracking_items(get_tracking_data(entry), call.data[ATTR_TRACKING_NUMBER])
    except TrackingNumberNotFoundError as err:
        raise ServiceValidationError(f"{err} is not tracked") from err

    _LOGGER.info("Removing tracking number(s) %s via action", call.data[ATTR_TRACKING_NUMBER])
    save_tracking_data(hass, entry, tracking_data)


async def async_set_owner(hass: HomeAssistant, call: ServiceCall) -> None:
    """Handle the set_owner action."""
    entry = get_target_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    owner = await async_resolve_owner(hass, call.data.get(ATTR_OWNER))

    try:
        tracking_data = set_tracking_owner(get_tracking_data(entry), call.data[ATTR_TRACKING_NUMBER], owner)
    except TrackingNumberNotFoundError as err:
        raise ServiceValidationError(f"{err} is not tracked") from err

    _LOGGER.info("Setting the owner of %s via action", call.data[ATTR_TRACKING_NUMBER])
    save_tracking_data(hass, entry, tracking_data)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration actions."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_TRACKING):
        return

    async def _add(call: ServiceCall) -> None:
        await async_add_tracking(hass, call)

    async def _remove(call: ServiceCall) -> None:
        await async_remove_tracking(hass, call)

    async def _set_owner(call: ServiceCall) -> None:
        await async_set_owner(hass, call)

    hass.services.async_register(DOMAIN, SERVICE_ADD_TRACKING, _add, schema=ADD_TRACKING_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_TRACKING, _remove, schema=REMOVE_TRACKING_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_OWNER, _set_owner, schema=SET_OWNER_SCHEMA)
