"""To-do list platform for Greek Courier Tracker.

Every tracked number is an item of the "Shipments" list: adding an item starts
tracking it, deleting an item stops tracking it, and items are checked off
automatically when the shipment is delivered.
"""

from __future__ import annotations

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GreekCourierDataUpdateCoordinator
from .const import COURIER_NAMES, DOMAIN
from .tracking import (
    TrackingNumberExistsError,
    TrackingNumberNotFoundError,
    add_tracking_item,
    get_tracking_data,
    parse_tracking_input,
    remove_tracking_items,
    rename_tracking_item,
    save_tracking_data,
    status_text,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the Shipments to-do list."""
    coordinator: GreekCourierDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GreekCourierShipmentsTodo(coordinator, entry)])


class GreekCourierShipmentsTodo(CoordinatorEntity, TodoListEntity):
    """To-do list with one item per tracked shipment."""

    _attr_has_entity_name = True
    _attr_translation_key = "shipments"
    _attr_icon = "mdi:package-variant-closed"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, coordinator: GreekCourierDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_shipments"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info (shared with the tracking sensors)."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Greek Courier Tracker",
            model="Greek Courier Tracker",
        )

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return one item per tracked shipment."""
        data = self.coordinator.data or {}
        items = []

        for item in get_tracking_data(self._entry):
            tracking_number = item["tracking_number"]
            result = data.get(tracking_number)

            details = [tracking_number]
            if result is not None:
                details.append(result.courier_name)
                details.append(status_text(result, self.hass.config.language if self.hass else None))
            elif item["courier"] in COURIER_NAMES and item["courier"] != "auto":
                details.append(COURIER_NAMES[item["courier"]])

            delivered = result is not None and result.status_category == "delivered"
            items.append(TodoItem(
                uid=tracking_number,
                summary=item["name"],
                status=TodoItemStatus.COMPLETED if delivered else TodoItemStatus.NEEDS_ACTION,
                description=" · ".join(details),
            ))

        return items

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Start tracking: the item text is the tracking number and an optional name."""
        tracking_number, name = parse_tracking_input(item.summary or "")
        if not tracking_number:
            raise ServiceValidationError("Enter a tracking number")

        try:
            tracking_data = add_tracking_item(get_tracking_data(self._entry), tracking_number, name=name)
        except TrackingNumberExistsError as err:
            raise ServiceValidationError(f"{tracking_number} is already tracked") from err

        save_tracking_data(self.hass, self._entry, tracking_data)

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Rename a shipment (its status follows the delivery status)."""
        current = next((todo for todo in self.todo_items if todo.uid == item.uid), None)
        if current is None:
            raise ServiceValidationError(f"{item.uid} is not tracked")

        if item.status is not None and item.status != current.status:
            raise ServiceValidationError(
                "Shipments are checked off automatically when they are delivered"
            )

        if item.summary and item.summary != current.summary:
            try:
                tracking_data = rename_tracking_item(get_tracking_data(self._entry), item.uid, item.summary)
            except TrackingNumberNotFoundError as err:
                raise ServiceValidationError(f"{item.uid} is not tracked") from err
            save_tracking_data(self.hass, self._entry, tracking_data)

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Stop tracking the given shipments."""
        try:
            tracking_data = remove_tracking_items(get_tracking_data(self._entry), uids)
        except TrackingNumberNotFoundError as err:
            raise ServiceValidationError(f"{err} is not tracked") from err

        save_tracking_data(self.hass, self._entry, tracking_data)
