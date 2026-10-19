"""ACS Courier tracking implementation."""

from __future__ import annotations

import re
import time
from typing import Any

import aiohttp
import async_timeout

from ..const import CourierType
from .base import BaseCourier, TrackingEvent, TrackingResult


class ACSCourier(BaseCourier):
    """ACS Courier tracking implementation."""

    COURIER_CODE = CourierType.ACS
    COURIER_NAME = "ACS Courier"

    API_URL = "https://api.acscourier.net/api/parcels/search/{tracking_number}"
    BASE_URL = "https://www.acscourier.net"
    # The tracking page carries the public token the API expects
    TOKEN_PAGE_URL = f"{BASE_URL}/el/myacs/anafores-apostolwn/anazitisi-apostolwn/"
    TOKEN_MAX_AGE = 30 * 60  # seconds

    # Tracking number patterns (10 digits)
    PATTERNS = [r"^\d{10}$"]

    # Status translations
    STATUS_TRANSLATIONS = {
        "Η αποστολή παρελήφθη": "Shipment Received",
        "Η αποστολή παραδόθηκε": "Delivered",
        "Η αποστολή βρίσκεται σε διάκριση": "In Transit",
        "Η αποστολή δεν βρέθηκε": "Not Found",
    }

    # Shared by all instances: one token serves every request for a while
    _token: str | None = None
    _token_time: float = 0.0

    async def track(self, tracking_number: str) -> TrackingResult:
        """Track an ACS shipment.

        The API needs the public token of the tracking page (X-Encrypted-Key),
        the country and the site origin; without them it answers 404/406.
        """
        tracking_number = tracking_number.strip()

        try:
            async with self._client_session() as session:
                async with async_timeout.timeout(30):
                    status, data = await self._search(session, tracking_number)
                    if status != 200:
                        # The token may have expired: get a new one and retry once
                        status, data = await self._search(session, tracking_number, refresh_token=True)

                if status != 200:
                    return TrackingResult(
                        success=False,
                        tracking_number=tracking_number,
                        courier=self.COURIER_CODE,
                        courier_name=self.COURIER_NAME,
                        status="Error",
                        status_category="error",
                        events=[],
                        error_message=f"HTTP error: {status}",
                    )
                return self._parse_response(tracking_number, data)

        except aiohttp.ClientError as err:
            return TrackingResult(
                success=False,
                tracking_number=tracking_number,
                courier=self.COURIER_CODE,
                courier_name=self.COURIER_NAME,
                status="Error",
                status_category="error",
                events=[],
                error_message=str(err),
            )
        except Exception as err:
            return TrackingResult(
                success=False,
                tracking_number=tracking_number,
                courier=self.COURIER_CODE,
                courier_name=self.COURIER_NAME,
                status="Error",
                status_category="error",
                events=[],
                error_message=f"Unexpected error: {err}",
            )

    async def _search(
        self, session: aiohttp.ClientSession, tracking_number: str, refresh_token: bool = False
    ) -> tuple[int, Any]:
        """Call the parcel search API."""
        token = await self._get_token(session, refresh=refresh_token)
        if not token:
            return 0, None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Language": "el-GR",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/",
            "X-Country": "GR",
            "X-Encrypted-Key": token,
        }
        url = self.API_URL.format(tracking_number=tracking_number)
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                return response.status, None
            return response.status, await response.json(content_type=None)

    async def _get_token(self, session: aiohttp.ClientSession, refresh: bool = False) -> str | None:
        """Return the public token of the tracking page (cached for a while)."""
        cls = type(self)
        if not refresh and cls._token and time.monotonic() - cls._token_time < self.TOKEN_MAX_AGE:
            return cls._token

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        }
        async with session.get(self.TOKEN_PAGE_URL, headers=headers) as response:
            if response.status != 200:
                return None
            text = await response.text()

        # The page has it as an attribute: publictoken="..."
        match = re.search(r'publicToken["\']?\s*[:=]\s*["\']([^"\']+)["\']', text, re.IGNORECASE)
        if not match:
            return None

        cls._token = match.group(1)
        cls._token_time = time.monotonic()
        return cls._token

    def _parse_response(self, tracking_number: str, data: dict[str, Any]) -> TrackingResult:
        """Parse the ACS API response."""
        items = (data or {}).get("items") or []
        parcel = items[0] if items else {}
        raw_events = parcel.get("statusHistory") or []

        # Unknown numbers come back as an item without history ("Η αποστολή δεν βρέθηκε")
        if not raw_events:
            return TrackingResult(
                success=True,
                tracking_number=tracking_number,
                courier=self.COURIER_CODE,
                courier_name=self.COURIER_NAME,
                status="Not Found",
                status_category="unknown",
                events=[],
            )

        events = []
        for event in raw_events:
            date_str = event.get("controlPointDate") or ""
            # Parse ISO date
            date_part = date_str.split("T")[0] if "T" in date_str else date_str
            time_part = date_str.split("T")[1][:5] if "T" in date_str else ""

            events.append(TrackingEvent(
                date=date_part,
                time=time_part,
                location=event.get("controlPoint") or "",
                status=event.get("description") or "",
                status_translated=self.translate_status(
                    event.get("description") or "",
                    self.STATUS_TRANSLATIONS
                ),
            ))

        # Keep newest first like the other couriers
        events.sort(key=lambda event: (event.date, event.time or ""), reverse=True)
        latest = events[0]
        is_delivered = parcel.get("isDelivered", False)

        status = "Delivered" if is_delivered else latest.status_translated or latest.status
        category = "delivered" if is_delivered else self.get_status_category(
            status,
            ["παραδόθηκε", "delivered"],
            ["διάκριση", "transit"],
            ["παρελήφθη", "received"]
        )
        # Anything past the first scan is on its way
        if category == "unknown":
            category = "in_transit" if len(events) > 1 else "created"

        return TrackingResult(
            success=True,
            tracking_number=tracking_number,
            courier=self.COURIER_CODE,
            courier_name=self.COURIER_NAME,
            status=status,
            status_category=category,
            events=events,
            latest_event=latest,
            raw_data=data,
        )
