"""History of removed shipments.

When Configure → Settings → "Keep removed shipments" is on, a shipment that stops
being tracked (removed from the card, the to-do list, an action, Configure, or
automatically after delivery) is kept here as it was at that moment: its status,
events and details are frozen and its courier is never asked again. It has no
sensor; the card reads the history through the greek_courier_tracker/history
websocket subscription. Shipments leave the history when deleted from it (card or
the delete_history action), when tracked again, or after the configured days.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_HISTORY_DAYS,
    CONF_KEEP_HISTORY,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_KEEP_HISTORY,
    DOMAIN,
    SIGNAL_HISTORY_UPDATED,
)
from .couriers import tracking_page_url
from .couriers.base import TrackingEvent, TrackingResult
from .tracking import status_text

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 1  # seconds


def get_keep_history(entry: ConfigEntry) -> bool:
    """Whether removed shipments are kept in the history."""
    return bool((entry.options or {}).get(CONF_KEEP_HISTORY, DEFAULT_KEEP_HISTORY))


def get_history_days(entry: ConfigEntry) -> int:
    """Days a removed shipment stays in the history (0 keeps it forever)."""
    return int((entry.options or {}).get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS))


def tracking_url(result: TrackingResult) -> str | None:
    """Return the courier's own tracking page, once a courier has found the shipment."""
    if not result.success or result.status in ("Not Found", "Error"):
        return None
    courier = str(getattr(result.courier, "value", result.courier))
    return tracking_page_url(courier, result.tracking_number)


def serialize_events(events: list[TrackingEvent]) -> list[dict[str, Any]]:
    """Serialize TrackingEvent objects to dictionaries."""
    return [
        {
            "date": event.date,
            "time": event.time,
            "location": event.location,
            "status": event.status,
            "status_translated": event.status_translated,
        }
        for event in events
    ]


def worth_keeping(result: TrackingResult | None) -> bool:
    """A courier found the shipment; numbers never found have nothing to keep."""
    return result is not None and result.success and result.status not in ("Not Found", "Error")


def snapshot(config: dict[str, Any], result: TrackingResult, removed_at: datetime) -> dict[str, Any]:
    """Freeze a shipment as it is now, with the attributes its sensor had."""
    latest = result.latest_event
    number = config["tracking_number"]
    return {
        "tracking_number": number,
        "name": config.get("name") or number,
        "owner_user_id": config.get("owner"),
        "courier": str(getattr(result.courier, "value", result.courier)),
        "courier_name": result.courier_name,
        "tracking_url": tracking_url(result),
        "status": result.status,
        "status_el": status_text(result, "el"),
        "status_category": result.status_category,
        "delivered": result.status_category == "delivered",
        "estimated_delivery": result.estimated_delivery,
        "latest_date": latest.date if latest else None,
        "latest_time": latest.time if latest else None,
        "latest_place": latest.location if latest else None,
        "events": serialize_events(result.events),
        "last_updated": result.last_updated,
        "removed_at": removed_at.isoformat(),
    }


class ShipmentHistory:
    """The removed shipments of a config entry, stored in .storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.history")
        self._items: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        """Read the stored history."""
        data = await self._store.async_load() or {}
        self._items = {
            item["tracking_number"]: item
            for item in data.get("shipments", [])
            if isinstance(item, dict) and item.get("tracking_number")
        }

    @property
    def items(self) -> list[dict[str, Any]]:
        """The kept shipments, the most recently removed first."""
        return sorted(self._items.values(), key=lambda item: item.get("removed_at") or "", reverse=True)

    def __contains__(self, tracking_number: str) -> bool:
        return tracking_number in self._items

    @callback
    def async_add(self, shipments: list[dict[str, Any]]) -> None:
        """Keep shipments (a number already in the history is replaced)."""
        if not shipments:
            return
        for shipment in shipments:
            self._items[shipment["tracking_number"]] = shipment
        _LOGGER.info("Kept in the history: %s", [shipment["tracking_number"] for shipment in shipments])
        self._changed()

    @callback
    def async_delete(self, tracking_numbers: list[str]) -> list[str]:
        """Delete shipments from the history; return those that were in it."""
        deleted = [number for number in tracking_numbers if self._items.pop(number, None) is not None]
        if deleted:
            _LOGGER.info("Deleted from the history: %s", deleted)
            self._changed()
        return deleted

    @callback
    def async_purge(self, days: int, now: datetime | None = None) -> list[str]:
        """Delete the shipments removed more than `days` ago (0 keeps them all)."""
        if days <= 0:
            return []
        cutoff = (now or dt_util.utcnow()) - timedelta(days=days)
        expired = []
        for number, item in self._items.items():
            removed_at = dt_util.parse_datetime(item.get("removed_at") or "")
            if removed_at is not None and removed_at < cutoff:
                expired.append(number)
        return self.async_delete(expired)

    async def async_remove(self) -> None:
        """Delete the stored history (the config entry is being removed)."""
        await self._store.async_remove()

    @callback
    def _changed(self) -> None:
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY)
        async_dispatcher_send(self.hass, SIGNAL_HISTORY_UPDATED)

    @callback
    def _data_to_save(self) -> dict[str, Any]:
        return {"shipments": list(self._items.values())}


def loaded_histories(hass: HomeAssistant) -> list[ShipmentHistory]:
    """The histories of the loaded entries."""
    return [
        coordinator.history
        for coordinator in hass.data.get(DOMAIN, {}).values()
        if isinstance(getattr(coordinator, "history", None), ShipmentHistory)
    ]


@callback
def history_message(hass: HomeAssistant) -> dict[str, Any]:
    """What the card needs: the kept shipments, and whether removing keeps them."""
    histories = loaded_histories(hass)
    shipments = [item for history in histories for item in history.items]
    shipments.sort(key=lambda item: item.get("removed_at") or "", reverse=True)
    keep = any(
        get_keep_history(coordinator.entry)
        for coordinator in hass.data.get(DOMAIN, {}).values()
        if getattr(coordinator, "entry", None) is not None
    )
    return {"shipments": shipments, "keep_history": keep}


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/history/subscribe"})
@callback
def websocket_subscribe_history(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send the history now and every time it changes."""

    @callback
    def forward() -> None:
        connection.send_message(websocket_api.event_message(msg["id"], history_message(hass)))

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(hass, SIGNAL_HISTORY_UPDATED, forward)
    connection.send_result(msg["id"])
    forward()


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Register the websocket command of the card."""
    websocket_api.async_register_command(hass, websocket_subscribe_history)
