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
        tracking_numbers = _get_tracking_numbers(entry)
        scan_interval = _get_scan_interval(entry)

        _LOGGER.info("Tracking numbers: %s", tracking_numbers)
        _LOGGER.info("Scan interval: %s minutes", scan_interval)

        if not tracking_numbers:
            _LOGGER.error("No tracking numbers provided!")
            return False

        coordinator = GreekCourierDataUpdateCoordinator(
            hass=hass,
            tracking_numbers=tracking_numbers,
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


def _get_tracking_numbers(entry: ConfigEntry) -> list[str]:
    """Get tracking numbers from entry data or options."""
    if entry.options and CONF_TRACKING_NUMBERS in entry.options:
        numbers = list(entry.options.get(CONF_TRACKING_NUMBERS, []))
        _LOGGER.debug("Got tracking numbers from options: %s", numbers)
        return numbers
    numbers = list(entry.data.get(CONF_TRACKING_NUMBERS, []))
    _LOGGER.debug("Got tracking numbers from data: %s", numbers)
    return numbers


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
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_interval),
        )
        self.tracking_numbers = tracking_numbers
        _LOGGER.debug("Coordinator initialized with %d tracking numbers", len(tracking_numbers))

    async def _async_update_data(self) -> dict[str, TrackingResult]:
        """Fetch latest data for all tracking numbers."""
        if not self.tracking_numbers:
            _LOGGER.warning("No tracking numbers to track")
            return {}

        _LOGGER.debug("Fetching updates for %d tracking numbers", len(self.tracking_numbers))

        async def _track_one(number: str) -> TrackingResult:
            _LOGGER.debug("Tracking: %s", number)
            try:
                result = await track_with_auto_detect(number)
                _LOGGER.debug("Result for %s: success=%s, courier=%s, status=%s",
                           number, result.success, result.courier, result.status)
                return result
            except Exception as err:
                _LOGGER.error("Error tracking %s: %s", number, err, exc_info=True)
                return TrackingResult(
                    success=False,
                    tracking_number=number,
                    courier="unknown",
                    courier_name="Unknown Courier",
                    status="Error",
                    status_category="error",
                    events=[],
                    error_message=str(err),
                )

        results: list[TrackingResult | Exception]
        try:
            async with async_timeout.timeout(60):
                results = await asyncio.gather(
                    *[_track_one(number) for number in self.tracking_numbers],
                    return_exceptions=True,
                )
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout while fetching tracking updates")
            # Return error results for all numbers
            return {
                number: TrackingResult(
                    success=False,
                    tracking_number=number,
                    courier="unknown",
                    courier_name="Unknown Courier",
                    status="Error",
                    status_category="error",
                    events=[],
                    error_message="Timeout",
                )
                for number in self.tracking_numbers
            }

        data: dict[str, TrackingResult] = {}
        for number, result in zip(self.tracking_numbers, results):
            if isinstance(result, Exception):
                _LOGGER.error("Exception for %s: %s", number, result)
                data[number] = TrackingResult(
                    success=False,
                    tracking_number=number,
                    courier="unknown",
                    courier_name="Unknown Courier",
                    status="Error",
                    status_category="error",
                    events=[],
                    error_message=str(result),
                )
            else:
                data[number] = result

        _LOGGER.debug("Update complete: %d results", len(data))
        return data
