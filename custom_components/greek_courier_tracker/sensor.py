"""Sensor platform for Greek Courier Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SIGNAL_TRACKING_ADDED, SIGNAL_TRACKING_CHANGED
from .couriers import tracking_page_url
from .couriers.base import TrackingEvent, TrackingResult
from .owners import owner_name
from .tracking import get_tracking_data, sensor_unique_id, status_text
from . import GreekCourierDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up sensors for each tracking number."""
    coordinator: GreekCourierDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    def _sensors(items: list[dict[str, Any]]) -> list[GreekCourierTrackingSensor]:
        return [
            GreekCourierTrackingSensor(
                coordinator,
                entry,
                tracking_number=item["tracking_number"],
                tracking_name=item["name"],
                stop_tracking_delivered=item["stop_tracking_delivered"],
                owner=item.get("owner"),
            )
            for item in items
        ]

    sensors = _sensors(get_tracking_data(entry))
    _remove_stale_sensors(hass, entry, {sensor.unique_id for sensor in sensors})
    async_add_entities(sensors)

    # Numbers added later (card, to-do list, actions, Configure) get a sensor
    # without reloading the integration
    @callback
    def _async_add_sensors(items: list[dict[str, Any]]) -> None:
        async_add_entities(_sensors(items))

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_TRACKING_ADDED.format(entry_id=entry.entry_id), _async_add_sensors)
    )


def _remove_stale_sensors(hass: HomeAssistant, entry: ConfigEntry, unique_ids: set[str]) -> None:
    """Remove sensors of tracking numbers that are no longer tracked."""
    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.domain == "sensor" and registry_entry.unique_id not in unique_ids:
            registry.async_remove(registry_entry.entity_id)


class GreekCourierTrackingSensor(CoordinatorEntity, SensorEntity):
    """Representation of a tracking sensor."""

    def __init__(
        self,
        coordinator: GreekCourierDataUpdateCoordinator,
        entry: ConfigEntry,
        tracking_number: str,
        tracking_name: str,
        stop_tracking_delivered: bool = False,
        owner: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._tracking_number = tracking_number
        self._tracking_name = tracking_name
        self._stop_tracking_delivered = stop_tracking_delivered
        self._owner = owner
        self._attr_unique_id = sensor_unique_id(entry.entry_id, tracking_number)
        # Use the custom name as the entity name
        self._attr_name = tracking_name
        # Set entity_id with greek_courier_tracker prefix
        self._attr_has_entity_name = True
        self.entity_id = f"sensor.greek_courier_tracker_{tracking_number.lower()}"

    async def async_added_to_hass(self) -> None:
        """Follow name and settings changes of this tracking number."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_TRACKING_CHANGED.format(entry_id=self._entry.entry_id),
                self._async_config_changed,
            )
        )

    @callback
    def _async_config_changed(self, configs: dict[str, dict[str, Any]]) -> None:
        """Apply a new name, owner or "stop when delivered" setting."""
        config = configs.get(self._tracking_number)
        if config is None:
            return
        self._tracking_name = config["name"]
        self._attr_name = config["name"]
        self._stop_tracking_delivered = config["stop_tracking_delivered"]
        self._owner = config.get("owner")
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        """Return the current status of the shipment."""
        result = self._get_result()
        if result is None:
            return None

        # Check if we should stop tracking (delivered and stop_tracking_delivered is True)
        stopped = self._stop_tracking_delivered and result.status_category == "delivered"
        language = self.hass.config.language if self.hass else None
        return status_text(result, language, stopped=stopped)

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
            "tracking_name": self._tracking_name,
            "owner_user_id": self._owner,
            "owner": owner_name(self.hass, self._owner) if self.hass else None,
            "courier": result.courier,
            "courier_name": result.courier_name,
            "tracking_url": _tracking_url(result),
            "status": result.status,
            "status_el": status_text(result, "el"),
            "status_category": result.status_category,
            "estimated_delivery": result.estimated_delivery,
            "latest_date": latest.date if latest else None,
            "latest_time": latest.time if latest else None,
            "latest_place": latest.location if latest else None,
            "events": _serialize_events(result.events),
            "delivered": result.status_category == "delivered",
            "stop_tracking_delivered": self._stop_tracking_delivered,
            "tracking_stopped": self._stop_tracking_delivered and result.status_category == "delivered",
            "error_message": result.error_message,
            "last_updated": result.last_updated,
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


def _tracking_url(result: TrackingResult) -> str | None:
    """Return the courier's own tracking page, once a courier has found the shipment."""
    if not result.success or result.status in ("Not Found", "Error"):
        return None
    courier = str(getattr(result.courier, "value", result.courier))
    return tracking_page_url(courier, result.tracking_number)


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
