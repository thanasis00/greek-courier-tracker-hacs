"""Sensor platform for Greek Courier Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_TRACKING_NUMBERS,
    CONF_TRACKING_NAME,
    DOMAIN,
)
from .couriers.base import TrackingEvent, TrackingResult
from . import GreekCourierDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up sensors for each tracking number."""
    coordinator: GreekCourierDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Get tracking data with names
    tracking_data = _get_tracking_data(entry)

    sensors = [
        GreekCourierTrackingSensor(
            coordinator,
            entry,
            tracking_number=item.get("tracking_number", item) if isinstance(item, dict) else item,
            tracking_name=item.get("name", item) if isinstance(item, dict) else item,
            stop_tracking_delivered=item.get("stop_tracking_delivered", False) if isinstance(item, dict) else False,
        )
        for item in tracking_data
    ]
    async_add_entities(sensors)


def _get_tracking_data(entry: ConfigEntry) -> list:
    """Get tracking data from entry data or options."""
    # Try options first (where updates are stored), then data
    tracking_data = entry.options.get(
        CONF_TRACKING_NUMBERS,
        entry.data.get(CONF_TRACKING_NUMBERS, [])
    )

    # Migrate old format (list of strings) to new format (list of dicts)
    if tracking_data and isinstance(tracking_data[0], str):
        return [
            {
                "tracking_number": number,
                "name": number,
                "stop_tracking_delivered": False,
            }
            for number in tracking_data
        ]

    return tracking_data


class GreekCourierTrackingSensor(CoordinatorEntity, SensorEntity):
    """Representation of a tracking sensor."""

    def __init__(
        self,
        coordinator: GreekCourierDataUpdateCoordinator,
        entry: ConfigEntry,
        tracking_number: str,
        tracking_name: str,
        stop_tracking_delivered: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._tracking_number = tracking_number
        self._tracking_name = tracking_name
        self._stop_tracking_delivered = stop_tracking_delivered
        self._attr_unique_id = f"{entry.entry_id}_{tracking_number}"
        # Use the custom name as the entity name
        self._attr_name = tracking_name
        # Set entity_id with greek_courier_tracker prefix
        self._attr_has_entity_name = True
        self.entity_id = f"sensor.greek_courier_tracker_{tracking_number.lower()}"

    @property
    def native_value(self) -> str | None:
        """Return the current status of the shipment."""
        result = self._get_result()
        if result is None:
            return None

        # Check if we should stop tracking (delivered and stop_tracking_delivered is True)
        if self._stop_tracking_delivered and result.status_category == "delivered":
            return f"Delivered - Tracking Stopped"

        return result.status

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        result = self._get_result()

        # If stop_tracking_delivered is enabled and package is delivered, mark unavailable
        if self._stop_tracking_delivered and result and result.status_category == "delivered":
            return False

        return result is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        result = self._get_result()
        if result is None:
            return {}

        latest = result.latest_event
        return {
            "tracking_number": result.tracking_number,
            "courier": result.courier,
            "courier_name": result.courier_name,
            "status": result.status,
            "status_category": result.status_category,
            "latest_date": latest.date if latest else None,
            "latest_time": latest.time if latest else None,
            "latest_place": latest.location if latest else None,
            "events": _serialize_events(result.events),
            "delivered": result.status_category == "delivered",
            "stop_tracking_delivered": self._stop_tracking_delivered,
            "tracking_stopped": self._stop_tracking_delivered and result.status_category == "delivered",
            "error_message": result.error_message,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Greek Courier Tracker",
            model="Greek Courier Tracker",
        )

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added."""
        return True

    def _get_result(self) -> TrackingResult | None:
        data = self.coordinator.data or {}
        return data.get(self._tracking_number)


def _serialize_events(events: list[TrackingEvent]) -> list[dict[str, Any]]:
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
