"""Greek Courier Tracker integration."""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import async_timeout

from homeassistant.config_entries import SOURCE_IGNORE, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.const import Platform
from homeassistant.loader import async_get_integration

from .const import (
    CARD_FILENAME,
    CARD_URL_BASE,
    CONF_SCAN_INTERVAL,
    CONF_TRACKING_NUMBERS,
    DOMAIN,
    EVENT_STATUS_CHANGED,
    SIGNAL_TRACKING_ADDED,
    SIGNAL_TRACKING_CHANGED,
)
from .couriers import _track_with_retry, get_courier, track_with_auto_detect
from .couriers.base import TrackingResult
from .owners import owner_device_ids, owner_name
from .services import async_setup_services
from .tracking import (
    get_auto_remove_days,
    get_scan_interval,
    get_tracking_data,
    remove_tracking_items,
    save_tracking_data,
    sensor_unique_id,
    status_text,
)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.TODO]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_LOGGER = logging.getLogger(__name__)

# Coordinators take their config entry since Home Assistant 2024.11, and newer
# versions report coordinators that leave it out
_COORDINATOR_TAKES_ENTRY = "config_entry" in inspect.signature(DataUpdateCoordinator.__init__).parameters

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration actions and the dashboard card."""
    _LOGGER.info("Setting up Greek Courier Tracker integration")
    try:
        await _async_merge_entries(hass)
    except Exception as err:
        _LOGGER.error("Could not merge the Greek Courier Tracker entries: %s", err, exc_info=True)
    async_setup_services(hass)
    await _async_register_card(hass)
    return True


async def _async_merge_entries(hass: HomeAssistant) -> None:
    """Merge the entries of older versions into the first one.

    Older versions allowed several entries. The shipments and settings of
    the other entries move to the first one, their sensors too (same entity ID,
    so the history stays), and the other entries are removed. This runs before
    the entries are set up.
    """
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.source != SOURCE_IGNORE and entry.disabled_by is None
    ]
    if len(entries) < 2:
        return

    first, others = entries[0], entries[1:]
    _LOGGER.info("Merging %d Greek Courier Tracker entries into %s", len(others), first.entry_id)

    tracking_data = get_tracking_data(first)
    moved: dict[str, str] = {}  # tracking number -> entry it comes from
    for entry in others:
        for item in get_tracking_data(entry):
            number = item["tracking_number"]
            if number not in moved and all(old["tracking_number"] != number for old in tracking_data):
                tracking_data.append(item)
                moved[number] = entry.entry_id

    # The first entry keeps its settings; the others fill in what it doesn't have
    options: dict[str, Any] = {}
    for entry in reversed(entries):
        options.update(entry.options or {})
    options[CONF_TRACKING_NUMBERS] = tracking_data
    options[CONF_SCAN_INTERVAL] = get_scan_interval(first)
    hass.config_entries.async_update_entry(first, options=options)

    # Removing an entry removes its device and entities, so the sensors of the
    # moved numbers switch to the first entry and its device first
    registry = er.async_get(hass)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, first.entry_id)})
    for entry in others:
        prefix = f"{entry.entry_id}_"
        for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            number = registry_entry.unique_id.removeprefix(prefix)
            if registry_entry.domain != "sensor" or moved.get(number) != entry.entry_id:
                continue
            registry.async_update_entity(
                registry_entry.entity_id,
                config_entry_id=first.entry_id,
                device_id=device.id if device else None,
                new_unique_id=sensor_unique_id(first.entry_id, number),
            )

    for entry in others:
        await hass.config_entries.async_remove(entry.entry_id)


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the bundled dashboard card and load it in the frontend."""
    if getattr(hass, "http", None) is None or hass.data.get(f"{DOMAIN}_card_registered"):
        return

    from homeassistant.components.frontend import add_extra_js_url

    card_path = Path(__file__).parent / "frontend" / CARD_FILENAME
    card_url = f"{CARD_URL_BASE}/{CARD_FILENAME}"

    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(card_url, str(card_path), False)]
        )
    except ImportError:
        # Home Assistant before 2024.7
        hass.http.register_static_path(card_url, str(card_path), False)

    # Version query string so browsers pick up a new card after an update
    integration = await async_get_integration(hass, DOMAIN)
    add_extra_js_url(hass, f"{card_url}?v={integration.version}")
    hass.data[f"{DOMAIN}_card_registered"] = True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Greek Courier Tracker from a config entry."""
    _LOGGER.info("Setting up Greek Courier Tracker from config entry: %s", entry.entry_id)
    _LOGGER.debug("Entry data: %s", entry.data)
    _LOGGER.debug("Entry options: %s", entry.options)

    try:
        tracking_data = get_tracking_data(entry)
        scan_interval = get_scan_interval(entry)

        # Extract just the tracking numbers for the coordinator
        tracking_numbers = [item["tracking_number"] for item in tracking_data]

        # Build a map of tracking_number -> config (name, stop_tracking_delivered, etc.)
        tracking_configs = {item["tracking_number"]: item for item in tracking_data}

        _LOGGER.info("Tracking numbers: %s", tracking_numbers)
        _LOGGER.info("Tracking configs: %s", tracking_configs)
        _LOGGER.info("Scan interval: %s hours", scan_interval)

        # An empty list is fine: numbers can be added later from the card,
        # the to-do list or the add_tracking action
        if not tracking_numbers:
            _LOGGER.info("No tracking numbers configured yet")

        coordinator = GreekCourierDataUpdateCoordinator(
            hass=hass,
            tracking_numbers=tracking_numbers,
            tracking_configs=tracking_configs,
            scan_interval=scan_interval,
            entry=entry,
        )

        # Initial refresh to validate configuration
        _LOGGER.info("Performing initial data refresh...")
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        entry.async_on_unload(entry.add_update_listener(_async_update_listener))

        _LOGGER.info("Greek Courier Tracker setup completed successfully")
        return True

    except Exception as err:
        _LOGGER.error("Error setting up Greek Courier Tracker: %s", err, exc_info=True)
        raise


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Greek Courier Tracker: %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed options without reloading the entry.

    Only the added (or re-assigned) numbers are fetched; the other sensors keep
    their state instead of going unavailable during a reload.
    """
    coordinator: GreekCourierDataUpdateCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        _LOGGER.info("Config entry updated, reloading: %s", entry.entry_id)
        await hass.config_entries.async_reload(entry.entry_id)
        return

    changes = await coordinator.async_apply_tracking_data(
        get_tracking_data(entry), get_scan_interval(entry)
    )
    _LOGGER.info(
        "Tracking numbers updated: added %s, removed %s, changed %s",
        [item["tracking_number"] for item in changes.added],
        changes.removed,
        list(changes.changed),
    )

    registry = er.async_get(hass)
    for number in changes.removed:
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, sensor_unique_id(entry.entry_id, number))
        if entity_id:
            registry.async_remove(entity_id)

    if changes.added:
        async_dispatcher_send(hass, SIGNAL_TRACKING_ADDED.format(entry_id=entry.entry_id), changes.added)
    if changes.changed:
        async_dispatcher_send(hass, SIGNAL_TRACKING_CHANGED.format(entry_id=entry.entry_id), changes.changed)


@dataclass
class TrackingChanges:
    """What changed when new tracking options were applied."""

    added: list[dict[str, Any]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: dict[str, dict[str, Any]] = field(default_factory=dict)


class GreekCourierDataUpdateCoordinator(DataUpdateCoordinator[dict[str, TrackingResult]]):
    """Coordinator to fetch tracking updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        tracking_numbers: list[str],
        tracking_configs: dict[str, dict],
        scan_interval: int,
        entry: ConfigEntry | None = None,
    ) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=DOMAIN,
            update_interval=timedelta(hours=scan_interval),
            **({"config_entry": entry} if _COORDINATOR_TAKES_ENTRY else {}),
        )
        self.tracking_numbers = tracking_numbers
        self.tracking_configs = tracking_configs
        self.scan_interval = scan_interval
        self.entry = entry
        self._apply_lock = asyncio.Lock()
        self._delivered_since: dict[str, datetime] = {}
        _LOGGER.debug("Coordinator initialized with %d tracking numbers", len(tracking_numbers))

    @staticmethod
    def _detected_courier(number: str, data: dict[str, TrackingResult]) -> str | None:
        """Return the courier that last tracked this number successfully."""
        result = data.get(number)
        if result is None or not result.success or result.status in ["Not Found", "Error"]:
            return None
        if result.courier in (None, "", "unknown"):
            return None
        return str(getattr(result.courier, "value", result.courier))

    def _current_data(self) -> dict[str, TrackingResult]:
        """Return the data of the numbers that are still tracked."""
        return {
            number: result
            for number, result in (self.data or {}).items()
            if number in self.tracking_configs
        }

    async def async_apply_tracking_data(
        self, tracking_data: list[dict[str, Any]], scan_interval: int
    ) -> TrackingChanges:
        """Switch to a new list of tracking items, fetching only what is new."""
        async with self._apply_lock:
            new_configs = {item["tracking_number"]: item for item in tracking_data}
            old_configs = self.tracking_configs

            changes = TrackingChanges(
                added=[item for number, item in new_configs.items() if number not in old_configs],
                removed=[number for number in old_configs if number not in new_configs],
                changed={
                    number: item
                    for number, item in new_configs.items()
                    if number in old_configs and item != old_configs[number]
                },
            )
            # New numbers, and numbers assigned to another courier, are fetched now
            refetch = [item["tracking_number"] for item in changes.added] + [
                number
                for number, item in changes.changed.items()
                if item.get("courier") != old_configs[number].get("courier")
            ]

            self.tracking_numbers = list(new_configs)
            self.tracking_configs = new_configs

            if scan_interval != self.scan_interval:
                self.scan_interval = scan_interval
                self.update_interval = timedelta(hours=scan_interval)

            fetched: dict[str, TrackingResult] = {}
            if refetch:
                base = {number: result for number, result in self._current_data().items() if number not in refetch}
                fetched = await self._async_fetch(refetch, base)

            # Merge into the current data (a scheduled refresh may have run meanwhile)
            data = self._current_data()
            for number in refetch:
                data.pop(number, None)
                if number in fetched:
                    data[number] = fetched[number]

            # Notifies the entities and restarts the refresh timer (new interval)
            old_data = self.data or {}
            self.async_set_updated_data(data)
            self._after_update(old_data, data)
            return changes

    def _after_update(
        self, old_data: dict[str, TrackingResult], new_data: dict[str, TrackingResult]
    ) -> None:
        """Announce status changes and clean up old deliveries."""
        self._fire_status_events(old_data, new_data)
        self._remove_expired_deliveries(new_data)

    @staticmethod
    def _status_key(result: TrackingResult) -> tuple:
        latest = result.latest_event
        return (result.status, result.status_category, latest.status if latest else None)

    def _fire_status_events(
        self, old_data: dict[str, TrackingResult], new_data: dict[str, TrackingResult]
    ) -> None:
        """Fire greek_courier_tracker_status_changed for every shipment that moved."""
        language = getattr(self.hass.config, "language", None)
        for number, result in new_data.items():
            old = old_data.get(number)
            if old is None or not result.success or self._status_key(old) == self._status_key(result):
                continue

            entity_id = None
            if self.entry is not None:
                try:
                    entity_id = er.async_get(self.hass).async_get_entity_id(
                        "sensor", DOMAIN, sensor_unique_id(self.entry.entry_id, number)
                    )
                except Exception:  # registry not available (tests)
                    entity_id = None

            config = self.tracking_configs.get(number, {})
            owner = config.get("owner")
            latest = result.latest_event
            self.hass.bus.async_fire(EVENT_STATUS_CHANGED, {
                "entity_id": entity_id,
                "tracking_number": number,
                "name": config.get("name", number),
                "courier": str(getattr(result.courier, "value", result.courier)),
                "courier_name": result.courier_name,
                "old_status": status_text(old, language),
                "status": status_text(result, language),
                "status_en": result.status,
                "status_category": result.status_category,
                "delivered": result.status_category == "delivered",
                "location": latest.location if latest else None,
                "estimated_delivery": result.estimated_delivery,
                # Shared shipments have no owner (and None instead of a phone list)
                "owner_user_id": owner,
                "owner": owner_name(self.hass, owner),
                "owner_device_ids": owner_device_ids(self.hass, owner) if owner else None,
            })

    @staticmethod
    def _delivery_date(result: TrackingResult) -> datetime | None:
        """Date of the delivery event, if it can be read."""
        latest = result.latest_event
        if latest is None:
            return None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(latest.date, fmt)
            except (TypeError, ValueError):
                continue
        return None

    def _remove_expired_deliveries(self, data: dict[str, TrackingResult]) -> None:
        """Stop tracking shipments delivered more than the configured days ago."""
        if self.entry is None:
            return
        days = get_auto_remove_days(self.entry)
        if days <= 0:
            return

        now = datetime.now()
        expired = []
        for number, result in data.items():
            if result.status_category != "delivered":
                self._delivered_since.pop(number, None)
                continue
            since = self._delivered_since.setdefault(number, self._delivery_date(result) or now)
            if number in self.tracking_configs and now - since >= timedelta(days=days):
                expired.append(number)

        if expired:
            _LOGGER.info("Removing shipments delivered more than %d days ago: %s", days, expired)
            save_tracking_data(
                self.hass, self.entry, remove_tracking_items(get_tracking_data(self.entry), expired)
            )

    async def _async_update_data(self) -> dict[str, TrackingResult]:
        """Fetch latest data for all tracking numbers."""
        if not self.tracking_numbers:
            _LOGGER.warning("No tracking numbers to track")
            return {}

        _LOGGER.debug("Fetching updates for %d tracking numbers", len(self.tracking_numbers))

        # Filter out tracking numbers that should be stopped (delivered and stop_tracking_delivered is True)
        active_numbers = []
        for number in self.tracking_numbers:
            config = self.tracking_configs.get(number, {})
            stop_when_delivered = config.get("stop_tracking_delivered", False) if isinstance(config, dict) else False

            # Check current status
            current_result = self.data.get(number) if self.data else None

            # Skip tracking if stop_tracking_delivered is True and already delivered
            if stop_when_delivered and current_result and current_result.status_category == "delivered":
                _LOGGER.debug("Skipping tracking for %s (delivered and stop_tracking_delivered is True)", number)
                # Keep the old result
                continue

            active_numbers.append(number)

        if not active_numbers:
            _LOGGER.debug("No active tracking numbers to update")
            return self._current_data()

        new_data = await self._async_fetch(active_numbers, self._current_data())
        self._after_update(self.data or {}, new_data)
        return new_data

    async def _async_fetch(
        self, numbers: list[str], base_data: dict[str, TrackingResult]
    ) -> dict[str, TrackingResult]:
        """Track the given numbers and merge the results into base_data."""
        active_numbers = numbers

        session = async_get_clientsession(self.hass)

        async def _track_one(number: str) -> TrackingResult:
            _LOGGER.debug("Tracking: %s", number)
            try:
                # Get courier selection from config
                config = self.tracking_configs.get(number, {})
                selected_courier = config.get("courier", "auto") if isinstance(config, dict) else "auto"

                if selected_courier and selected_courier != "auto":
                    # Use the selected courier
                    courier = get_courier(selected_courier, session)
                    if courier:
                        _LOGGER.debug("Using selected courier %s for %s", courier.COURIER_NAME, number)
                        result = await _track_with_retry(courier, number)
                    else:
                        _LOGGER.warning("Selected courier %s not found, falling back to auto-detect", selected_courier)
                        result = await track_with_auto_detect(number, session)
                else:
                    # Ask the courier that found it last time before trying them all
                    result = None
                    detected = self._detected_courier(number, base_data)
                    if detected:
                        courier = get_courier(detected, session)
                        if courier:
                            _LOGGER.debug("Using detected courier %s for %s", courier.COURIER_NAME, number)
                            result = await _track_with_retry(courier, number)
                            if not result.success or result.status in ["Not Found", "Error"]:
                                result = None
                    if result is None:
                        result = await track_with_auto_detect(number, session)

                _LOGGER.debug("Result for %s: success=%s, courier=%s, status=%s",
                           number, result.success, result.courier, result.status)
                return result
            except Exception as err:
                _LOGGER.error("Error tracking %s: %s", number, err, exc_info=True)
                # Return None to indicate failure - we'll keep the old data
                return None

        results: list[TrackingResult | Exception | None]
        try:
            async with async_timeout.timeout(60):
                results = await asyncio.gather(
                    *[_track_one(number) for number in active_numbers],
                    return_exceptions=True,
                )
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout while fetching tracking updates")
            # Keep existing data on timeout
            return base_data

        # Merge results with existing data (keep stopped tracking numbers)
        new_data = dict(base_data)
        for number, result in zip(active_numbers, results):
            if isinstance(result, Exception):
                _LOGGER.error("Exception for %s: %s", number, result)
                # Keep existing data for this tracking number
                if number not in new_data:
                    # Only create error result if we don't have any data yet
                    new_data[number] = TrackingResult(
                        success=False,
                        tracking_number=number,
                        courier="unknown",
                        courier_name="Unknown Courier",
                        status="No data available",
                        status_category="unknown",
                        events=[],
                        error_message=str(result),
                    )
            elif result is None:
                # API call failed - keep existing data
                _LOGGER.warning("API call failed for %s, keeping previous data", number)
            elif not result.success or result.status in ["Error", "Not Found"]:
                # API returned error or not found - keep existing data if we have it
                if number in new_data:
                    _LOGGER.warning("API returned error for %s, keeping previous data", number)
                else:
                    # First time tracking, store the error result
                    new_data[number] = result
            else:
                # Success - update with new data and add timestamp
                from datetime import datetime, timezone
                result.last_updated = datetime.now(timezone.utc).isoformat()
                new_data[number] = result

        _LOGGER.debug("Update complete: %d results", len(new_data))
        return new_data
