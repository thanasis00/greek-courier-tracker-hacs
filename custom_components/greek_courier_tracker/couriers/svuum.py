"""Svuum tracking implementation."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import aiohttp
import async_timeout

from ..const import CourierType
from .base import BaseCourier, TrackingEvent, TrackingResult


class SvuumCourier(BaseCourier):
    """Svuum tracking implementation (FarEye tracking platform)."""

    COURIER_CODE = CourierType.SVUUM
    COURIER_NAME = "Svuum"

    # Same endpoint the svuum.gr tracking iframe (live.svuum.com) calls
    API_URL = "https://live.svuum.com/track-referenceNo/get_status_multiple"
    BASE_URL = "https://live.svuum.com"
    COMPANY_CODE = "svm"
    PROCESS_MASTER_ID = "5630"  # "Website Tracking" process used by svuum.gr

    # Tracking number patterns
    PATTERNS = [
        r"^\d{7}$",          # 7 digits (e.g. 3416482)
    ]

    # Status code translations
    STATUS_CODE_TRANSLATIONS = {
        "S010": "Order Still at the E-shop",
        "S210": "Received at Svuum Central Warehouse",
    }

    # Keywords are matched against lowercase text without Greek accents
    FAILED_KEYWORDS = ["ανεπιτυχ", "αποτυχ", "failed"]
    DELIVERED_KEYWORDS = ["παραδοθηκε", "επιτυχης παραδοση", "delivered"]
    CREATED_KEYWORDS = ["eshop", "e-shop", "δημιουργ", "καταχωρ"]

    MONTHS = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    async def track(self, tracking_number: str) -> TrackingResult:
        """Track a Svuum shipment."""
        tracking_number = tracking_number.strip().upper()

        params = {
            "com_code": self.COMPANY_CODE,
            "referenceNumber": tracking_number,
            "processMasterIds": self.PROCESS_MASTER_ID,
            "onlyLatest": "false",
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": f"{self.BASE_URL}/track.html?com_code={self.COMPANY_CODE}",
        }

        try:
            async with self._client_session() as session:
                async with async_timeout.timeout(30):
                    async with session.get(
                        self.API_URL,
                        params=params,
                        headers=headers,
                    ) as response:
                        if response.status != 200:
                            return TrackingResult(
                                success=False,
                                tracking_number=tracking_number,
                                courier=self.COURIER_CODE,
                                courier_name=self.COURIER_NAME,
                                status="Error",
                                status_category="error",
                                events=[],
                                error_message=f"HTTP error: {response.status}",
                            )

                        data = await response.json(content_type=None)
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

    def _parse_response(self, tracking_number: str, data: Any) -> TrackingResult:
        """Parse the Svuum (FarEye) API response."""
        # Unknown tracking numbers return an empty list
        parcels = data if isinstance(data, list) else [data]
        parcel = next(
            (item for item in parcels if isinstance(item, dict) and item.get("processTimeLineLogsList")),
            None,
        )

        if parcel is None:
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

        # Timeline is already newest first
        for event in parcel.get("processTimeLineLogsList", []):
            status = (event.get("status") or "").strip()
            date_part, time_part = self._parse_status_time(event.get("statusTime") or "")

            events.append(TrackingEvent(
                date=date_part,
                time=time_part,
                location="",
                status=status,
                status_translated=self.STATUS_CODE_TRANSLATIONS.get(
                    event.get("statusCode", ""), status
                ),
            ))

        latest = events[0] if events else None
        status = latest.status_translated if latest else "Unknown"
        status_code = (parcel.get("processTimeLineLogsList") or [{}])[0].get("statusCode", "")

        return TrackingResult(
            success=True,
            tracking_number=tracking_number,
            courier=self.COURIER_CODE,
            courier_name=self.COURIER_NAME,
            status=status,
            status_category=self._get_category(latest, status_code),
            events=events,
            latest_event=latest,
            raw_data={"data": data},
            status_el=latest.status if latest else None,
        )

    def _get_category(self, latest: TrackingEvent | None, status_code: str) -> str:
        """Determine the status category from the latest event."""
        if latest is None:
            return "unknown"

        text = self._normalize(f"{latest.status} {latest.status_translated or ''}")

        # "Ανεπιτυχής παράδοση" contains "επιτυχής παράδοση", so check failures first
        if any(keyword in text for keyword in self.FAILED_KEYWORDS):
            return "in_transit"
        if any(keyword in text for keyword in self.DELIVERED_KEYWORDS):
            return "delivered"
        if status_code == "S010" or any(keyword in text for keyword in self.CREATED_KEYWORDS):
            return "created"
        return "in_transit"

    def _normalize(self, text: str) -> str:
        """Lowercase text and strip Greek accents for keyword matching."""
        decomposed = unicodedata.normalize("NFD", text.lower())
        return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")

    def _parse_status_time(self, status_time: str) -> tuple[str, str]:
        """Parse FarEye time ("Oct-19-2026 05:40 PM") into date and 24h time."""
        match = re.match(
            r"^([A-Za-z]{3})-(\d{1,2})-(\d{4})\s+(\d{1,2}):(\d{2})\s*([AaPp][Mm])$",
            status_time.strip(),
        )
        if not match or match.group(1).lower() not in self.MONTHS:
            return status_time, ""

        month = self.MONTHS[match.group(1).lower()]
        day, year = int(match.group(2)), int(match.group(3))
        hour, minute = int(match.group(4)) % 12, int(match.group(5))
        if match.group(6).upper() == "PM":
            hour += 12

        return f"{year:04d}-{month:02d}-{day:02d}", f"{hour:02d}:{minute:02d}"
