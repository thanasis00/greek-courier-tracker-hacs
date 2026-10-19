"""Owners of shipments.

The owner of a shipment is a Home Assistant user: the one who added it, unless
someone picked another person. A phone belongs to the user signed in to the
Companion app on it, so notifications can go only to the owner's phones.
Shipments without an owner are shared.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

try:
    from homeassistant.helpers.http import current_request
except ImportError:  # Older Home Assistant
    from homeassistant.components.http import current_request


def request_user_id() -> str | None:
    """Return the user of the frontend request being handled (forms in Settings)."""
    request = current_request.get()
    user = request.get("hass_user") if request is not None else None
    return user.id if user is not None else None


def owner_name(hass: HomeAssistant, user_id: str | None) -> str | None:
    """Return the name of the person linked to a user."""
    if not user_id:
        return None
    for state in hass.states.async_all("person"):
        if state.attributes.get("user_id") == user_id:
            return state.name
    return None


def owner_device_ids(hass: HomeAssistant, user_id: str) -> list[str]:
    """Return the Companion app devices the user is signed in to."""
    registry = dr.async_get(hass)
    return [
        device.id
        for entry in hass.config_entries.async_entries("mobile_app")
        if entry.data.get("user_id") == user_id
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
    ]


async def async_resolve_owner(hass: HomeAssistant, value: str | None) -> str | None:
    """Return the user ID for a person entity or user ID (empty means shared)."""
    if not value:
        return None
    if value.startswith("person."):
        state = hass.states.get(value)
        user_id = state.attributes.get("user_id") if state is not None else None
        if not user_id:
            raise ServiceValidationError(f"{value} is not linked to a Home Assistant user")
        return user_id
    if await hass.auth.async_get_user(value) is None:
        raise ServiceValidationError(f"There is no Home Assistant user with ID {value}")
    return value


async def async_owner_options(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return the people who can own shipments, for a dropdown."""
    users = await hass.auth.async_get_users()
    options = [
        {"value": user.id, "label": owner_name(hass, user.id) or user.name or user.id}
        for user in users
        if user.is_active and not user.system_generated
    ]
    return sorted(options, key=lambda option: option["label"].lower())
