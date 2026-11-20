"""Greek Courier Tracker integration."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import async_timeout

from homeassistant.config_entries import SOURCE_IGNORE, ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.const import Platform
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .const import (
    AUTO_DETECT_TIMEOUT,
    CARD_FILENAME,
    CARD_URL_BASE,
    CONF_LEGACY_SCAN_INTERVAL_HOURS,
    CONF_SCAN_INTERVAL,
    CONF_TRACKING_NUMBERS,
    DOMAIN,
    EVENT_NO_MOVEMENT,
    EVENT_SHIPMENT_UPDATED,
    EVENT_STATUS_CHANGED,
    NUMBER_TIMEOUT,
    REQUEST_SPACING,
    SIGNAL_HISTORY_UPDATED,
    SIGNAL_TRACKING_ADDED,
    SIGNAL_TRACKING_CHANGED,
    CourierType,
)
from .couriers import (
    COURIER_REGISTRY,
    _track_with_retry,
    get_courier,
    is_refused,
    track_with_auto_detect,
)
from .couriers.base import (
    FINAL_PROBLEMS,
    PROBLEM_CANCELLED,
    PROBLEM_RETURNED,
    STAGE_LEVELS,
    BaseCourier,
    TrackingResult,
    stage_category,
)
from .shipment_history import (
    ShipmentHistory,
    async_register_websocket,
    get_history_days,
    get_keep_history,
    snapshot,
    worth_keeping,
)
from .blueprint_update import async_check_blueprint
from .owners import owner_device_ids, owner_name
from .scheduling import CourierSchedule, courier_interval
from .services import async_setup_services
from .tracking import (
    get_auto_remove_days,
    get_scan_interval,
    get_no_movement_days,
    get_tracking_data,
    last_movement,
    no_movement_text,
    problem_text,
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

# The schedule of the numbers whose courier isn't known yet
AUTO_DETECT = CourierType.AUTO.value

# How often shipments past their days in the history are deleted
HISTORY_PURGE_INTERVAL = timedelta(hours=6)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration actions and the dashboard card."""
    _LOGGER.info("Setting up Greek Courier Tracker integration")
    try:
        await _async_merge_entries(hass)
    except Exception as err:
        _LOGGER.error("Could not merge the Greek Courier Tracker entries: %s", err, exc_info=True)
    async_setup_services(hass)
    async_register_websocket(hass)
    await _async_register_card(hass)
    # Offer the new notification blueprint to those who imported an older one
    async_at_started(hass, async_check_blueprint)
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
    options.pop(CONF_LEGACY_SCAN_INTERVAL_HOURS, None)
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
        _LOGGER.info("Scan interval: %s minutes", scan_interval)

        # An empty list is fine: numbers can be added later from the card,
        # the to-do list or the add_tracking action
        if not tracking_numbers:
            _LOGGER.info("No tracking numbers configured yet")

        # Loaded before the first refresh, which may already remove old deliveries
        history = ShipmentHistory(hass, entry.entry_id)
        await history.async_load()

        coordinator = GreekCourierDataUpdateCoordinator(
            hass=hass,
            tracking_numbers=tracking_numbers,
            tracking_configs=tracking_configs,
            scan_interval=scan_interval,
            entry=entry,
            history=history,
        )

        await coordinator.async_load_notices()

        # Initial refresh to validate configuration
        _LOGGER.info("Performing initial data refresh...")
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        entry.async_on_unload(entry.add_update_listener(_async_update_listener))

        @callback
        def _async_purge_history(_now: datetime | None = None) -> None:
            history.async_purge(get_history_days(entry))

        _async_purge_history()
        entry.async_on_unload(async_track_time_interval(hass, _async_purge_history, HISTORY_PURGE_INTERVAL))
        # Cards that subscribed before the entry was loaded get its history now
        async_dispatcher_send(hass, SIGNAL_HISTORY_UPDATED)

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
        async_dispatcher_send(hass, SIGNAL_HISTORY_UPDATED)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the history of removed shipments with the entry."""
    await ShipmentHistory(hass, entry.entry_id).async_remove()
    await Store(hass, 1, no_movement_store_key(entry.entry_id)).async_remove()


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

    # Removed shipments go to the history (if it is on); tracked again, they leave it
    coordinator.keep_in_history(changes.removed_items)
    if coordinator.history is not None:
        coordinator.history.async_delete([item["tracking_number"] for item in changes.added])
        coordinator.history.async_purge(get_history_days(entry))
    # The card also shows whether removing keeps a shipment
    async_dispatcher_send(hass, SIGNAL_HISTORY_UPDATED)

    if changes.added:
        async_dispatcher_send(hass, SIGNAL_TRACKING_ADDED.format(entry_id=entry.entry_id), changes.added)
    if changes.changed:
        async_dispatcher_send(hass, SIGNAL_TRACKING_CHANGED.format(entry_id=entry.entry_id), changes.changed)


def no_movement_store_key(entry_id: str) -> str:
    """Storage of the "no movement" notices of an entry."""
    return f"{DOMAIN}.{entry_id}.no_movement"


def _keep_stage(previous: TrackingResult | None, result: TrackingResult) -> None:
    """Don't let the progress go back when a courier answers with fewer events.

    Returns, cancellations and expiries start the trip back, so they may.
    """
    if previous is None or previous.stage is None or result.stage is None:
        return
    if result.problem in FINAL_PROBLEMS:
        return
    if STAGE_LEVELS[previous.stage] > STAGE_LEVELS[result.stage]:
        result.stage = previous.stage
        result.status_category = stage_category(previous.stage)
        if result.stage == "delivered":
            result.problem = None


@dataclass
class TrackingChanges:
    """What changed when new tracking options were applied."""

    added: list[dict[str, Any]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: dict[str, dict[str, Any]] = field(default_factory=dict)
    # The settings and last result of every removed number, for the history
    removed_items: dict[str, tuple[dict[str, Any], TrackingResult | None]] = field(default_factory=dict)


class GreekCourierDataUpdateCoordinator(DataUpdateCoordinator[dict[str, TrackingResult]]):
    """Coordinator to fetch tracking updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        tracking_numbers: list[str],
        tracking_configs: dict[str, dict],
        scan_interval: int,
        entry: ConfigEntry | None = None,
        history: ShipmentHistory | None = None,
    ) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_interval),
            **({"config_entry": entry} if _COORDINATOR_TAKES_ENTRY else {}),
        )
        self.tracking_numbers = tracking_numbers
        self.tracking_configs = tracking_configs
        self.scan_interval = scan_interval
        self.entry = entry
        self.history = history
        # Shipments whose "no movement" notice was sent: {number: their latest event}
        self._no_movement_sent: dict[str, str] = {}
        self._no_movement_store: Store[dict[str, str]] | None = (
            Store(hass, 1, no_movement_store_key(entry.entry_id)) if entry is not None else None
        )
        self._apply_lock = asyncio.Lock()
        self._fetch_lock = asyncio.Lock()
        self._schedule = CourierSchedule()
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
            previous = self.data or {}
            removed = [number for number in old_configs if number not in new_configs]

            changes = TrackingChanges(
                added=[item for number, item in new_configs.items() if number not in old_configs],
                removed=removed,
                changed={
                    number: item
                    for number, item in new_configs.items()
                    if number in old_configs and item != old_configs[number]
                },
                removed_items={number: (old_configs[number], previous.get(number)) for number in removed},
            )
            # New numbers, and numbers assigned to another courier, are fetched now
            refetch = [item["tracking_number"] for item in changes.added] + [
                number
                for number, item in changes.changed.items()
                if item.get("courier") != old_configs[number].get("courier")
            ]

            self.tracking_numbers = list(new_configs)
            self.tracking_configs = new_configs

            self.scan_interval = scan_interval

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

            # Notifies the entities and restarts the refresh timer (new wake-up time)
            old_data = self.data or {}
            self._reschedule(data)
            self.async_set_updated_data(data)
            self._after_update(old_data, data)
            return changes

    def _after_update(
        self, old_data: dict[str, TrackingResult], new_data: dict[str, TrackingResult]
    ) -> None:
        """Announce status changes and clean up old deliveries."""
        self._fire_status_events(old_data, new_data)
        self._notice_no_movement(new_data)
        self._remove_expired_deliveries(new_data)

    @staticmethod
    def _status_key(result: TrackingResult) -> tuple:
        """What a status change is: the status, its stage or problem, the latest event text."""
        latest = result.latest_event
        return (
            result.status,
            result.status_category,
            result.stage,
            result.problem,
            latest.status if latest else None,
        )

    @classmethod
    def _update_key(cls, result: TrackingResult) -> tuple:
        """What an update is: any new event, even one with the same text in another place."""
        latest = result.latest_event
        return (
            *cls._status_key(result),
            len(result.events),
            (latest.date, latest.time, latest.location) if latest else None,
        )

    def _entity_id(self, number: str) -> str | None:
        """The sensor of a tracking number, if the registry knows it."""
        if self.entry is None:
            return None
        try:
            return er.async_get(self.hass).async_get_entity_id(
                "sensor", DOMAIN, sensor_unique_id(self.entry.entry_id, number)
            )
        except Exception:  # registry not available (tests)
            return None

    def _shipment_event_data(self, number: str, result: TrackingResult, language: str | None) -> dict[str, Any]:
        """What the events of a shipment say about it now."""
        config = self.tracking_configs.get(number, {})
        owner = config.get("owner")
        latest = result.latest_event
        return {
            "entity_id": self._entity_id(number),
            "tracking_number": number,
            "name": config.get("name", number),
            "courier": str(getattr(result.courier, "value", result.courier)),
            "courier_name": result.courier_name,
            "status": status_text(result, language),
            "status_en": result.status,
            "status_category": result.status_category,
            "delivered": result.status_category == "delivered",
            "stage": result.stage,
            "problem": result.problem,
            "problem_text": problem_text(result.problem, language),
            "location": latest.location if latest else None,
            "estimated_delivery": result.estimated_delivery,
            # Shared shipments have no owner (and None instead of a phone list)
            "owner_user_id": owner,
            "owner": owner_name(self.hass, owner),
            "owner_device_ids": owner_device_ids(self.hass, owner) if owner else None,
        }

    def _fire_status_events(
        self, old_data: dict[str, TrackingResult], new_data: dict[str, TrackingResult]
    ) -> None:
        """Fire the events of every shipment that moved.

        greek_courier_tracker_shipment_updated: every new update, even one with the
        same text in another place; greek_courier_tracker_status_changed: only when
        the status itself changed (as before there was the other event).
        """
        language = getattr(self.hass.config, "language", None)
        for number, result in new_data.items():
            old = old_data.get(number)
            if old is None or not result.success or self._update_key(old) == self._update_key(result):
                continue

            data = self._shipment_event_data(number, result, language)
            status_changed = self._status_key(old) != self._status_key(result)
            changes = {
                "old_status": status_text(old, language),
                "old_problem": old.problem,
                "old_stage": old.stage,
            }
            self.hass.bus.async_fire(EVENT_SHIPMENT_UPDATED, {
                **data,
                **changes,
                "status_changed": status_changed,
                "stage_changed": old.stage != result.stage,
            })
            if status_changed:
                self.hass.bus.async_fire(EVENT_STATUS_CHANGED, {**data, **changes})

    async def async_load_notices(self) -> None:
        """Read which "no movement" notices were already sent (they survive restarts)."""
        if self._no_movement_store is not None:
            self._no_movement_sent = dict(await self._no_movement_store.async_load() or {})

    @staticmethod
    def _movement_key(result: TrackingResult) -> str:
        latest = result.latest_event
        return f"{latest.date} {latest.time} {latest.location} {latest.status}" if latest else ""

    def stalled_since(self, number: str, now: datetime | None = None) -> datetime | None:
        """When a shipment last moved, if that is longer ago than the configured days."""
        result = (self.data or {}).get(number)
        if self.entry is None or result is None:
            return None
        return self._stalled_since(result, get_no_movement_days(self.entry), now or dt_util.now())

    @staticmethod
    def _stalled_since(result: TrackingResult, days: int, now: datetime) -> datetime | None:
        if days <= 0 or not result.success or result.status in ("Not Found", "Error"):
            return None
        # Delivered, returned and cancelled shipments are done moving
        if result.status_category == "delivered" or result.problem in (PROBLEM_RETURNED, PROBLEM_CANCELLED):
            return None
        moved = last_movement(result)
        if moved is None or now - moved < timedelta(days=days):
            return None
        return moved

    def _notice_no_movement(self, data: dict[str, TrackingResult]) -> None:
        """Fire greek_courier_tracker_no_movement once per shipment and latest event."""
        changed = False
        for number in [number for number in self._no_movement_sent if number not in self.tracking_configs]:
            del self._no_movement_sent[number]
            changed = True

        days = get_no_movement_days(self.entry) if self.entry is not None else 0
        now = dt_util.now()
        language = getattr(self.hass.config, "language", None)
        for number, result in data.items():
            moved = self._stalled_since(result, days, now)
            key = self._movement_key(result)
            if moved is None or number not in self.tracking_configs or self._no_movement_sent.get(number) == key:
                continue
            self._no_movement_sent[number] = key
            changed = True
            idle = (now - moved).days
            _LOGGER.info("%s has not moved for %d days", number, idle)
            self.hass.bus.async_fire(EVENT_NO_MOVEMENT, {
                **self._shipment_event_data(number, result, language),
                "days": idle,
                "last_movement": moved.isoformat(),
                "text": no_movement_text(idle, language),
            })

        if changed and self._no_movement_store is not None:
            self._no_movement_store.async_delay_save(lambda: dict(self._no_movement_sent), 1)

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
            # Kept here, not in the options listener: on the first refresh after a
            # restart the listener isn't registered yet
            self.keep_in_history({number: (self.tracking_configs[number], data.get(number)) for number in expired})
            save_tracking_data(
                self.hass, self.entry, remove_tracking_items(get_tracking_data(self.entry), expired)
            )

    def keep_in_history(self, removed: dict[str, tuple[dict[str, Any], TrackingResult | None]]) -> None:
        """Keep removed shipments, as they are now, if the entry keeps a history.

        Numbers that no courier found aren't kept, nor numbers already kept (the
        listener sees the shipments that the clean-up of deliveries kept).
        """
        if self.history is None or self.entry is None or not get_keep_history(self.entry):
            return
        now = dt_util.utcnow()
        self.history.async_add([
            snapshot(config, result, now)
            for number, (config, result) in removed.items()
            if worth_keeping(result) and number not in self.history
        ])

    def _courier_of(self, number: str, data: dict[str, TrackingResult]) -> str:
        """Return the courier to ask about a number, or "auto" if it isn't known yet."""
        config = self.tracking_configs.get(number, {})
        selected = config.get("courier", CourierType.AUTO) if isinstance(config, dict) else CourierType.AUTO
        selected = str(getattr(selected, "value", selected))
        if selected in COURIER_REGISTRY:
            return selected
        detected = self._detected_courier(number, data)
        return detected if detected in COURIER_REGISTRY else AUTO_DETECT

    def _active_numbers(self, data: dict[str, TrackingResult]) -> list[str]:
        """Return the numbers to keep checking; a delivered shipment is finished.

        Delivered shipments keep their last result (they are asked again only
        after a restart, to show it). The stop_tracking_delivered option decides
        what their sensor shows, not whether they are checked.
        """
        active = []
        for number in self.tracking_numbers:
            current = data.get(number)
            if current is not None and current.status_category == "delivered":
                _LOGGER.debug("Not checking %s: already delivered", number)
                continue
            active.append(number)
        return active

    def _intervals(
        self, numbers: list[str], data: dict[str, TrackingResult]
    ) -> dict[str, timedelta]:
        """Return how often each courier with active numbers should be asked."""
        counts = Counter(self._courier_of(number, data) for number in numbers)
        return {
            courier: courier_interval(
                courier,
                count,
                self.scan_interval,
                COURIER_REGISTRY[courier].BATCH_SIZE if courier in COURIER_REGISTRY else 1,
            )
            for courier, count in counts.items()
        }

    def _reschedule(self, data: dict[str, TrackingResult]) -> None:
        """Wake up when the next courier is due."""
        now = dt_util.utcnow()
        intervals = self._intervals(self._active_numbers(data), data)
        self._schedule.reconcile(intervals, now)
        self.update_interval = self._schedule.next_wake(
            list(intervals), now, timedelta(minutes=self.scan_interval)
        )

    async def _async_update_data(self) -> dict[str, TrackingResult]:
        """Fetch the latest data of the couriers that are due."""
        if not self.tracking_numbers:
            _LOGGER.warning("No tracking numbers to track")
            return {}

        now = dt_util.utcnow()
        data = self._current_data()
        active = self._active_numbers(data)
        intervals = self._intervals(active, data)
        due = {courier for courier in intervals if self._schedule.is_due(courier, now)}
        numbers = [number for number in active if self._courier_of(number, data) in due]
        _LOGGER.debug("Checking %d of %d numbers (couriers: %s)", len(numbers), len(active), sorted(due))

        new_data = data
        if numbers:
            new_data = await self._async_fetch(numbers, data)
            finished = dt_util.utcnow()
            for courier in due:
                self._schedule.mark_polled(courier, intervals[courier], finished)

        self._after_update(self.data or {}, new_data)
        self._reschedule(new_data)
        return new_data

    def _record_refusal(self, code: str, courier: BaseCourier) -> None:
        """Leave a courier alone for a while after it refused a request."""
        delay = self._schedule.record_blocked(code, dt_util.utcnow(), courier.retry_after)
        _LOGGER.warning("%s refused a request, not asking it again for %s", courier.COURIER_NAME, delay)

    async def _track_one(self, courier: BaseCourier, number: str) -> TrackingResult | None:
        """Ask a courier about one number; None keeps the previous data."""
        try:
            async with async_timeout.timeout(NUMBER_TIMEOUT):
                return await _track_with_retry(courier, number)
        except Exception as err:
            _LOGGER.error("Error tracking %s with %s: %s", number, courier.COURIER_NAME, err, exc_info=True)
            return None

    async def _track_batch(
        self, courier: BaseCourier, numbers: list[str], data: dict[str, TrackingResult]
    ) -> tuple[dict[str, TrackingResult], list[str]]:
        """Ask a courier about several numbers; also return those to ask one by one."""
        results: dict[str, TrackingResult] = {}
        for start in range(0, len(numbers), courier.BATCH_SIZE):
            if start:
                await asyncio.sleep(REQUEST_SPACING)
            try:
                async with async_timeout.timeout(NUMBER_TIMEOUT):
                    results.update(await courier.track_many(numbers[start : start + courier.BATCH_SIZE]))
            except Exception as err:
                _LOGGER.warning("%s could not answer for several numbers: %s", courier.COURIER_NAME, err)
            if any(is_refused(result) for result in results.values()):
                return results, []

        # A failed batch, or a number it lost, shouldn't leave a shipment stale
        retry = [
            number
            for number in numbers
            if number not in results
            or not results[number].success
            or (results[number].status == "Not Found" and self._detected_courier(number, data))
        ]
        return results, retry

    async def _fetch_courier(
        self,
        code: str,
        numbers: list[str],
        data: dict[str, TrackingResult],
        session: Any,
        results: dict[str, TrackingResult],
    ) -> None:
        """Ask one courier about its numbers, one request at a time."""
        if self._schedule.is_blocked(code, dt_util.utcnow()):
            _LOGGER.debug("Leaving %s alone for now, keeping the data of %s", code, numbers)
            return

        courier = get_courier(code, session)
        pending = numbers
        spaced = False
        if courier.BATCH_SIZE > 1 and len(numbers) > 1:
            batch, pending = await self._track_batch(courier, numbers, data)
            results.update(batch)
            spaced = True
            if any(is_refused(result) for result in batch.values()):
                self._record_refusal(code, courier)
                return
            if len(pending) < len(numbers):
                self._schedule.record_success(code)

        for number in pending:
            if spaced:
                await asyncio.sleep(REQUEST_SPACING)
            spaced = True
            result = await self._track_one(courier, number)
            if result is None:
                continue
            results[number] = result
            if is_refused(result):
                self._record_refusal(code, courier)
                return
            if result.success:
                self._schedule.record_success(code)

    async def _detect_one(self, number: str, session: Any) -> TrackingResult | None:
        """Try all couriers that aren't backing off for a number of unknown courier."""
        now = dt_util.utcnow()
        skip = {code for code in COURIER_REGISTRY if self._schedule.is_blocked(code, now)}
        refused = lambda courier: self._record_refusal(  # noqa: E731
            str(getattr(courier.COURIER_CODE, "value", courier.COURIER_CODE)), courier
        )
        try:
            async with async_timeout.timeout(AUTO_DETECT_TIMEOUT):
                return await track_with_auto_detect(number, session, skip=skip, on_refused=refused)
        except Exception as err:
            _LOGGER.error("Error detecting the courier of %s: %s", number, err, exc_info=True)
            return None

    async def _async_fetch(
        self, numbers: list[str], base_data: dict[str, TrackingResult]
    ) -> dict[str, TrackingResult]:
        """Track the given numbers and merge the results into base_data.

        Couriers are asked at the same time, each one a request at a time. Numbers
        of unknown courier come last, as they may ask every courier.
        """
        groups: dict[str, list[str]] = {}
        for number in numbers:
            groups.setdefault(self._courier_of(number, base_data), []).append(number)
        unknown = groups.pop(AUTO_DETECT, [])

        results: dict[str, TrackingResult] = {}
        async with self._fetch_lock:
            session = async_get_clientsession(self.hass)
            await asyncio.gather(*[
                self._fetch_courier(code, group, base_data, session, results)
                for code, group in groups.items()
            ])
            for index, number in enumerate(unknown):
                if index:
                    await asyncio.sleep(REQUEST_SPACING)
                result = await self._detect_one(number, session)
                if result is not None:
                    results[number] = result

        # Merge results with existing data (keep stopped tracking numbers)
        new_data = dict(base_data)
        for number in numbers:
            result = results.get(number)
            if result is None:
                # API call failed or skipped - keep existing data
                _LOGGER.debug("No answer for %s, keeping previous data", number)
            elif not result.success or result.status in ["Error", "Not Found"]:
                # API returned error or not found - keep existing data if we have it
                if number in new_data:
                    _LOGGER.warning("API returned error for %s, keeping previous data", number)
                else:
                    # First time tracking, store the error result
                    new_data[number] = result
            else:
                # Success - update with new data and add timestamp
                result.last_updated = datetime.now(timezone.utc).isoformat()
                _keep_stage(new_data.get(number), result)
                new_data[number] = result

        _LOGGER.debug("Update complete: %d results", len(new_data))
        return new_data
