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


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration from configuration.yaml (not used)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Greek Courier Tracker from a config entry."""
    tracking_numbers = _get_tracking_numbers(entry)
    scan_interval = _get_scan_interval(entry)

    coordinator = GreekCourierDataUpdateCoordinator(
        hass=hass,
        tracking_numbers=tracking_numbers,
        scan_interval=scan_interval,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


def _get_tracking_numbers(entry: ConfigEntry) -> list[str]:
    """Get tracking numbers from entry data or options."""
    if entry.options and CONF_TRACKING_NUMBERS in entry.options:
        return list(entry.options.get(CONF_TRACKING_NUMBERS, []))
    return list(entry.data.get(CONF_TRACKING_NUMBERS, []))


def _get_scan_interval(entry: ConfigEntry) -> int:
    """Get scan interval from entry data or options."""
    if entry.options and CONF_SCAN_INTERVAL in entry.options:
        return int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    return int(entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))


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

    async def _async_update_data(self) -> dict[str, TrackingResult]:
        """Fetch latest data for all tracking numbers."""
        if not self.tracking_numbers:
            return {}

        async def _track_one(number: str) -> TrackingResult:
            return await track_with_auto_detect(number)

        results: list[TrackingResult | Exception]
        async with async_timeout.timeout(60):
            results = await asyncio.gather(
                *[_track_one(number) for number in self.tracking_numbers],
                return_exceptions=True,
            )

        data: dict[str, TrackingResult] = {}
        for number, result in zip(self.tracking_numbers, results):
            if isinstance(result, Exception):
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
        return data
