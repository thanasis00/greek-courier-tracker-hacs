"""Greek Courier Tracker integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.const import Platform

from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TRACKING_NUMBERS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .couriers import track_with_auto_detect
from .couriers.base import TrackingResult

PLATFORMS: list[Platform] = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration from configuration.yaml (not used)."""
    _LOGGER.info("Setting up Greek Courier Tracker integration")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Greek Courier Tracker from a config entry."""
    _LOGGER.info("Setting up Greek Courier Tracker from config entry: %s", entry.entry_id)
    _LOGGER.debug("Entry data: %s", entry.data)
    _LOGGER.debug("Entry options: %s", entry.options)

    try:
        tracking_data = _get_tracking_data(entry)
        scan_interval = _get_scan_interval(entry)

        # Extract just the tracking numbers for the coordinator
        tracking_numbers = [
            item.get("tracking_number", item) if isinstance(item, dict) else item
            for item in tracking_data
        ]

        # Build a map of tracking_number -> config (name, stop_tracking_delivered, etc.)
        tracking_configs = {
            item.get("tracking_number", item) if isinstance(item, dict) else item: item
            for item in tracking_data
        }

        _LOGGER.info("Tracking numbers: %s", tracking_numbers)
        _LOGGER.info("Tracking configs: %s", tracking_configs)
        _LOGGER.info("Scan interval: %s minutes", scan_interval)

        if not tracking_numbers:
            _LOGGER.error("No tracking numbers provided!")
            return False

        coordinator = GreekCourierDataUpdateCoordinator(
            hass=hass,
            tracking_numbers=tracking_numbers,
            tracking_configs=tracking_configs,
            scan_interval=scan_interval,
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
    """Handle options update."""
    _LOGGER.info("Config entry updated, reloading: %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


def _get_tracking_data(entry: ConfigEntry) -> list:
    """Get tracking data from entry data or options."""
    if entry.options and CONF_TRACKING_NUMBERS in entry.options:
        data = list(entry.options.get(CONF_TRACKING_NUMBERS, []))
        _LOGGER.debug("Got tracking data from options: %s", data)
        return _migrate_tracking_data(data)

    data = list(entry.data.get(CONF_TRACKING_NUMBERS, []))
    _LOGGER.debug("Got tracking data from data: %s", data)
    return _migrate_tracking_data(data)


def _migrate_tracking_data(data: list) -> list:
    """Migrate old tracking number format to new format."""
    if not data:
        return []

    # Check if migration is needed (old format: list of strings)
    if isinstance(data[0], str):
        _LOGGER.info("Migrating tracking numbers to new format with names")
        return [
            {
                "tracking_number": number,
                "name": number,
                "stop_tracking_delivered": False,
            }
            for number in data
        ]

    return data


def _get_scan_interval(entry: ConfigEntry) -> int:
    """Get scan interval from entry data or options."""
    if entry.options and CONF_SCAN_INTERVAL in entry.options:
        interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        _LOGGER.debug("Got scan interval from options: %s", interval)
        return interval
    interval = int(entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    _LOGGER.debug("Got scan interval from data: %s", interval)
    return interval


class GreekCourierDataUpdateCoordinator(DataUpdateCoordinator[dict[str, TrackingResult]]):
    """Coordinator to fetch tracking updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        tracking_numbers: list[str],
        tracking_configs: dict[str, dict],
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=DOMAIN,
            update_interval=timedelta(hours=scan_interval),
        )
        self.tracking_numbers = tracking_numbers
        self.tracking_configs = tracking_configs
        _LOGGER.debug("Coordinator initialized with %d tracking numbers", len(tracking_numbers))

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
            return self.data or {}

        async def _track_one(number: str) -> TrackingResult:
            _LOGGER.debug("Tracking: %s", number)
            try:
                # Get courier selection from config
                config = self.tracking_configs.get(number, {})
                selected_courier = config.get("courier", "auto") if isinstance(config, dict) else "auto"

                if selected_courier and selected_courier != "auto":
                    # Use the selected courier
                    from .couriers import get_courier, _track_with_retry
                    courier = get_courier(selected_courier)
                    if courier:
                        _LOGGER.debug("Using selected courier %s for %s", courier.COURIER_NAME, number)
                        result = await _track_with_retry(courier, number)
                    else:
                        _LOGGER.warning("Selected courier %s not found, falling back to auto-detect", selected_courier)
                        result = await track_with_auto_detect(number)
                else:
                    # Auto-detect - try all couriers
                    result = await track_with_auto_detect(number)

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
            return self.data or {}

        # Merge results with existing data (keep stopped tracking numbers)
        new_data = dict(self.data or {})
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
