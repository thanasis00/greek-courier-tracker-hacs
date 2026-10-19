"""Helpers for reading and changing the tracking numbers of a config entry."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AUTO_REMOVE_DELIVERED,
    CONF_SCAN_INTERVAL,
    CONF_TRACKING_NUMBERS,
    DEFAULT_AUTO_REMOVE_DELIVERED,
    DEFAULT_SCAN_INTERVAL,
    CourierType,
)
from .couriers.base import TrackingResult

GREEK = re.compile(r"[\u0370-\u03FF\u1F00-\u1FFF]")

# Greek for the English statuses the couriers report themselves
STATUS_TEXT_EL = {
    "Not Found": "Δεν βρέθηκε ακόμα",
    "Error": "Σφάλμα",
    "Unknown": "Άγνωστη κατάσταση",
    "Delivered": "Παραδόθηκε",
    "Delivered - Tracking Stopped": "Παραδόθηκε - Τέλος παρακολούθησης",
    "In Transit": "Σε μεταφορά",
    "Picked Up": "Παραλήφθηκε",
    "Shipment Created": "Δημιουργήθηκε",
    "New Order": "Νέα παραγγελία",
    "In Depot": "Στην αποθήκη",
    "At Destination Locker": "Στο locker προορισμού",
    "Expired": "Έληξε",
    "Returned": "Επιστράφηκε",
    "New Shipment": "Νέα αποστολή",
    "Out for Delivery": "Προς παράδοση",
    "Returning to Sender": "Επιστρέφει στον αποστολέα",
}


class TrackingNumberExistsError(ValueError):
    """Raised when adding a tracking number that is already tracked."""


class TrackingNumberNotFoundError(ValueError):
    """Raised when removing a tracking number that is not tracked."""


def sensor_unique_id(entry_id: str, tracking_number: str) -> str:
    """Return the unique ID of the sensor of a tracking number."""
    return f"{entry_id}_{tracking_number}"


def normalize_tracking_number(tracking_number: str) -> str:
    """Normalize a tracking number (strip spaces, uppercase)."""
    return re.sub(r"\s+", "", tracking_number or "").upper()


def parse_tracking_input(text: str) -> tuple[str, str | None]:
    """Split free text like "SE123456789GR Shoes" or "SE123456789GR: Shoes".

    Returns the normalized tracking number and the optional name.
    """
    parts = re.split(r"\s*:\s*|\s+", (text or "").strip(), maxsplit=1)
    tracking_number = normalize_tracking_number(parts[0]) if parts else ""
    name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    return tracking_number, name


def get_tracking_data(entry: ConfigEntry) -> list[dict[str, Any]]:
    """Return a copy of the tracking items of an entry (options first, then data)."""
    if entry.options and CONF_TRACKING_NUMBERS in entry.options:
        raw = entry.options.get(CONF_TRACKING_NUMBERS) or []
    else:
        raw = entry.data.get(CONF_TRACKING_NUMBERS) or []

    items = []
    for item in raw:
        if isinstance(item, str):
            item = {"tracking_number": item, "name": item}
        items.append({
            "tracking_number": item.get("tracking_number", ""),
            "name": item.get("name") or item.get("tracking_number", ""),
            "stop_tracking_delivered": item.get("stop_tracking_delivered", False),
            "courier": item.get("courier") or CourierType.AUTO,
        })
    return items


def get_auto_remove_days(entry: ConfigEntry) -> int:
    """Days after delivery when a shipment is removed (0 keeps it)."""
    return int((entry.options or {}).get(CONF_AUTO_REMOVE_DELIVERED, DEFAULT_AUTO_REMOVE_DELIVERED))


def status_text(result: TrackingResult, language: str | None, stopped: bool = False) -> str:
    """Return the status in Greek for a Greek Home Assistant, else in English."""
    english = "Delivered - Tracking Stopped" if stopped else result.status
    if not (language if isinstance(language, str) else "").lower().startswith("el"):
        return english
    if stopped:
        return STATUS_TEXT_EL[english]
    if english in ("Not Found", "Error"):
        return STATUS_TEXT_EL[english]
    if result.status_el:
        return result.status_el
    latest = result.latest_event
    if latest and GREEK.search(latest.status or ""):
        return latest.status
    return STATUS_TEXT_EL.get(english, english)


def get_scan_interval(entry: ConfigEntry) -> int:
    """Return the scan interval of an entry (options first, then data)."""
    if entry.options and CONF_SCAN_INTERVAL in entry.options:
        return int(entry.options[CONF_SCAN_INTERVAL])
    return int(entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))


def build_options(entry: ConfigEntry, tracking_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the entry options for a new list of tracking items (other settings are kept)."""
    return {
        **(entry.options or {}),
        CONF_TRACKING_NUMBERS: tracking_data,
        CONF_SCAN_INTERVAL: get_scan_interval(entry),
    }


def add_tracking_item(
    tracking_data: list[dict[str, Any]],
    tracking_number: str,
    name: str | None = None,
    courier: str = CourierType.AUTO,
    stop_tracking_delivered: bool = False,
) -> list[dict[str, Any]]:
    """Return a new list with the tracking number added."""
    tracking_number = normalize_tracking_number(tracking_number)
    if not tracking_number:
        raise ValueError("Tracking number is required")
    if any(item["tracking_number"] == tracking_number for item in tracking_data):
        raise TrackingNumberExistsError(tracking_number)

    return [
        *tracking_data,
        {
            "tracking_number": tracking_number,
            "name": (name or "").strip() or tracking_number,
            "stop_tracking_delivered": stop_tracking_delivered,
            "courier": courier or CourierType.AUTO,
        },
    ]


def remove_tracking_items(
    tracking_data: list[dict[str, Any]], tracking_numbers: list[str]
) -> list[dict[str, Any]]:
    """Return a new list without the given tracking numbers."""
    to_remove = {normalize_tracking_number(number) for number in tracking_numbers}
    missing = to_remove - {item["tracking_number"] for item in tracking_data}
    if missing:
        raise TrackingNumberNotFoundError(", ".join(sorted(missing)))
    return [item for item in tracking_data if item["tracking_number"] not in to_remove]


def rename_tracking_item(
    tracking_data: list[dict[str, Any]], tracking_number: str, name: str
) -> list[dict[str, Any]]:
    """Return a new list with the tracking number renamed."""
    tracking_number = normalize_tracking_number(tracking_number)
    if not any(item["tracking_number"] == tracking_number for item in tracking_data):
        raise TrackingNumberNotFoundError(tracking_number)
    return [
        {**item, "name": name.strip() or tracking_number}
        if item["tracking_number"] == tracking_number
        else item
        for item in tracking_data
    ]


def save_tracking_data(
    hass: HomeAssistant, entry: ConfigEntry, tracking_data: list[dict[str, Any]]
) -> None:
    """Store a new list of tracking items (the entry reloads on change)."""
    hass.config_entries.async_update_entry(entry, options=build_options(entry, tracking_data))
