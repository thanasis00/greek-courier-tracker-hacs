"""Couriers package - Greek courier tracking implementations."""

import asyncio
import logging
import re

import aiohttp

from .base import BaseCourier, TrackingResult
from .elta import ELTACourier
from .acs import ACSCourier
from .speedex import SpeedExCourier
from .boxnow import BoxNowCourier
from .geniki import GenikiCourier
from .courier_center import CourierCenterCourier
from .skroutz import SkroutzCourier
from .svuum import SvuumCourier

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "ELTACourier",
    "ACSCourier",
    "SpeedExCourier",
    "BoxNowCourier",
    "GenikiCourier",
    "CourierCenterCourier",
    "SkroutzCourier",
    "SvuumCourier",
    "get_courier",
    "tracking_page_url",
    "track_with_auto_detect",
    "_track_with_retry",
]

# Registry of all couriers
COURIER_REGISTRY: dict[str, type[BaseCourier]] = {
    "elta": ELTACourier,
    "acs": ACSCourier,
    "speedex": SpeedExCourier,
    "box_now": BoxNowCourier,
    "geniki": GenikiCourier,
    "courier_center": CourierCenterCourier,
    "skroutz": SkroutzCourier,
    "svuum": SvuumCourier,
}

# Maximum retries per courier
MAX_RETRIES = 3


def get_courier(
    courier_code: str, session: aiohttp.ClientSession | None = None
) -> BaseCourier | None:
    """Get a courier instance by code.

    Args:
        courier_code: The courier code (e.g., 'elta', 'acs')
        session: Shared HTTP session to use (e.g. Home Assistant's)

    Returns:
        Courier instance or None if not found
    """
    courier_class = COURIER_REGISTRY.get(courier_code)
    if courier_class:
        return courier_class(session)
    return None


def tracking_page_url(courier_code: str, tracking_number: str) -> str | None:
    """Return the courier's own tracking page for a number, if it has one."""
    courier_class = COURIER_REGISTRY.get(courier_code)
    return courier_class.tracking_page_url(tracking_number) if courier_class else None


def couriers_by_likelihood(tracking_number: str) -> list[type[BaseCourier]]:
    """Return all couriers, those whose number format matches first."""
    tn = tracking_number.strip().upper()
    matching = [
        courier_class
        for courier_class in COURIER_REGISTRY.values()
        if any(re.match(pattern, tn) for pattern in getattr(courier_class, "PATTERNS", []))
    ]
    return matching + [
        courier_class for courier_class in COURIER_REGISTRY.values() if courier_class not in matching
    ]


async def track_with_auto_detect(
    tracking_number: str, session: aiohttp.ClientSession | None = None
) -> TrackingResult:
    """Track a shipment by trying the couriers until one knows the number.

    This function:
    1. Tries the couriers whose number format matches first, then the rest
    2. Uses retry logic (up to 3 attempts) for each courier
    3. Returns the first result with valid tracking data (not "Not Found" or "Error")

    Args:
        tracking_number: The tracking number to track
        session: Shared HTTP session to use (e.g. Home Assistant's)

    Returns:
        TrackingResult from the first courier that successfully tracks the package
    """
    tn = tracking_number.strip().upper()

    _LOGGER.info(
        "Tracking %s - trying ALL %d couriers",
        tracking_number,
        len(COURIER_REGISTRY)
    )

    last_result = None

    for courier_class in couriers_by_likelihood(tn):
        courier = courier_class(session)

        _LOGGER.debug(
            "Trying %s for tracking number %s",
            courier.COURIER_NAME,
            tracking_number
        )

        result = await _track_with_retry(courier, tn)
        last_result = result

        # If we got a successful result with actual tracking data, return it
        # (an empty "Unknown" result means the courier didn't recognize the number)
        if (
            result.success
            and result.status not in ["Not Found", "Error"]
            and (result.events or result.status not in ["Unknown", ""])
        ):
            _LOGGER.info(
                "Successfully tracked %s using %s: %s",
                tracking_number,
                courier.COURIER_NAME,
                result.status
            )
            return result

        # If this courier clearly said "Not Found", try the next one
        _LOGGER.debug(
            "%s returned %s for %s, trying next courier",
            courier.COURIER_NAME,
            result.status,
            tracking_number
        )

    # No courier succeeded - return the last result
    _LOGGER.warning(
        "All couriers failed for tracking number %s",
        tracking_number
    )
    return last_result or TrackingResult(
        success=False,
        tracking_number=tracking_number,
        courier="unknown",
        courier_name="Unknown Courier",
        status="Error",
        status_category="error",
        events=[],
        error_message="All couriers failed to track this number",
    )


async def _track_with_retry(
    courier: BaseCourier,
    tracking_number: str,
    max_retries: int = MAX_RETRIES
) -> TrackingResult:
    """Track a shipment with retry logic (internal function).

    Args:
        courier: The courier instance to use
        tracking_number: The tracking number to track
        max_retries: Maximum number of retry attempts

    Returns:
        TrackingResult from the courier
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            result = await courier.track(tracking_number)

            # Check if we got a successful response
            # A result is considered "found" if:
            # - success is True AND
            # - status is not "Not Found" or "Error" AND
            # - there are events OR a valid status
            if result.success and result.status not in ["Not Found", "Error"]:
                if result.events or result.status not in ["Unknown", ""]:
                    _LOGGER.debug(
                        "Successfully tracked %s with %s on attempt %d",
                        tracking_number,
                        courier.COURIER_NAME,
                        attempt + 1
                    )
                    return result

            # Retrying a rate limited request only makes it worse
            if not result.success and (result.error_message or "").startswith("HTTP error: 429"):
                return result

            # If we got a clear "Not Found" from the courier, don't retry
            if result.success and result.status == "Not Found":
                _LOGGER.debug(
                    "Courier %s reported tracking number %s as Not Found",
                    courier.COURIER_NAME,
                    tracking_number
                )
                return result

            # Log the attempt and continue to retry
            if attempt < max_retries - 1:
                _LOGGER.debug(
                    "Attempt %d for %s with %s returned status: %s, retrying...",
                    attempt + 1,
                    tracking_number,
                    courier.COURIER_NAME,
                    result.status
                )
                await asyncio.sleep(0.5)  # Small delay between retries
            else:
                _LOGGER.debug(
                    "Final attempt for %s with %s returned: %s",
                    tracking_number,
                    courier.COURIER_NAME,
                    result.status
                )
                return result

        except Exception as err:
            last_error = err
            _LOGGER.warning(
                "Attempt %d for %s with %s failed: %s",
                attempt + 1,
                tracking_number,
                courier.COURIER_NAME,
                str(err)
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)  # Small delay between retries

    # All retries exhausted
    return TrackingResult(
        success=False,
        tracking_number=tracking_number,
        courier=courier.COURIER_CODE,
        courier_name=courier.COURIER_NAME,
        status="Error",
        status_category="error",
        events=[],
        error_message=f"Failed after {max_retries} attempts: {str(last_error)}",
    )
