"""Sensor platform for Greek Courier Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .couriers.base import TrackingEvent, TrackingResult
from . import GreekCourierDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up sensors for each tracking number."""
    coordinator: GreekCourierDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    sensors = [
        GreekCourierTrackingSensor(coordinator, entry, tracking_number)
        for tracking_number in coordinator.tracking_numbers
    ]
    async_add_entities(sensors)


class GreekCourierTrackingSensor(CoordinatorEntity, SensorEntity):
    """Representation of a tracking sensor."""

    def __init__(
        self,
        coordinator: GreekCourierDataUpdateCoordinator,
        entry: ConfigEntry,
        tracking_number: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._tracking_number = tracking_number
        self._attr_unique_id = f"{entry.entry_id}_{tracking_number}"
        self._attr_name = f"{entry.title} {tracking_number}"

    @property
    def native_value(self) -> str | None:
        """Return the current status of the shipment."""
        result = self._get_result()
        if result is None:
            return None
        return result.status

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        result = self._get_result()
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
