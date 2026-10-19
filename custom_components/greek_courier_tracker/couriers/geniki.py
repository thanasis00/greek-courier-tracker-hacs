"""Geniki Taxydromiki tracking implementation."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
import async_timeout

from ..const import CourierType
from .base import BaseCourier, TrackingEvent, TrackingResult


class GenikiCourier(BaseCourier):
    """Geniki Taxydromiki tracking implementation."""

    COURIER_CODE = CourierType.GENIKI
    COURIER_NAME = "Geniki Taxydromiki"

    # Same endpoint the taxydromiki.com/track/<number> page calls from the browser
    API_URL = "https://taxydromiki.com/external_scripts/track-site.php"
    BASE_URL = "https://taxydromiki.com"

    # Tracking number patterns
    PATTERNS = [
        r"^\d{10,12}$",       # 10-12 digits (Geniki format)
    ]

    # Status code groups used by the taxydromiki.com tracking page
    CREATE_STATUSES = {"C_NW", "C_SC", "C_KK"}
    RECEIVE_STATUSES = {"C_W3", "C_A1", "C_K8"}
    DELIVERY_STATUSES = {"C_W2", "C_P1", "C_S2"}
    CANCEL_STATUSES = {"C_E2", "C_L2", "C_K9", "C_P4", "C_S5", "C_S8"}
    # An event followed by its cancelling event is hidden, as on the website
    CANCEL_PAIRS = [("C_L1", "C_L2"), ("C_E1", "C_E2"), ("C_K8", "C_K9")]

    # Status translations (used when the English text is not available)
    STATUS_TRANSLATIONS = {
        "ΠΑΡΑΔΟΣΗ": "Delivered",
        "ΜΕΤΑΦΟΡΑ": "In Transit",
        "ΠΑΡΑΛΑΒΗ": "Picked Up",
        "ΚΡΑΤΗΣΗ": "Held",
        "ΕΠΙΣΤΡΟΦΗ": "Returned",
    }

    TIMEZONE = ZoneInfo("Europe/Athens")

    async def track(self, tracking_number: str) -> TrackingResult:
        """Track a Geniki Taxydromiki shipment."""
        tracking_number = tracking_number.strip().upper()

        try:
            async with aiohttp.ClientSession() as session:
                status, data = await self._fetch(session, tracking_number, "el")
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

                checkpoints = self._get_checkpoints(data, tracking_number)
                if not checkpoints:
                    return TrackingResult(
                        success=True,
                        tracking_number=tracking_number,
                        courier=self.COURIER_CODE,
                        courier_name=self.COURIER_NAME,
                        status="Not Found",
                        status_category="unknown",
                        events=[],
                    )

                # Fetch the English texts too; Greek ones are kept if this fails
                checkpoints_en: list[dict[str, Any]] = []
                try:
                    status_en, data_en = await self._fetch(session, tracking_number, "en")
                    if status_en == 200:
                        checkpoints_en = self._get_checkpoints(data_en, tracking_number)
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    pass

                return self._parse_checkpoints(tracking_number, checkpoints, checkpoints_en, data)

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

    async def _fetch(
        self, session: aiohttp.ClientSession, tracking_number: str, lang: str
    ) -> tuple[int, Any]:
        """Request tracking data in the given language ("el" or "en")."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            # The website sends a JSON body with a form content type
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/track/{tracking_number}/",
        }
        body = json.dumps({"lang": lang, "voucherNo": tracking_number})

        async with async_timeout.timeout(30):
            async with session.post(self.API_URL, data=body, headers=headers) as response:
                if response.status != 200:
                    return response.status, None
                return response.status, await response.json(content_type=None)

    def _get_checkpoints(self, data: Any, tracking_number: str) -> list[dict[str, Any]]:
        """Extract the checkpoint list (oldest first) for a tracking number."""
        if not isinstance(data, dict):
            return []

        shipment = data.get(tracking_number) or {}
        result = shipment.get("TrackAndTraceResult") or {}
        checkpoints = (result.get("Checkpoints") or {}).get("Checkpoint") or []

        # A single checkpoint may come back as an object instead of a list
        if isinstance(checkpoints, dict):
            checkpoints = [checkpoints]
        return [item for item in checkpoints if isinstance(item, dict)]

    def _parse_checkpoints(
        self,
        tracking_number: str,
        checkpoints: list[dict[str, Any]],
        checkpoints_en: list[dict[str, Any]],
        data: dict[str, Any],
    ) -> TrackingResult:
        """Build the tracking result from the Geniki checkpoints."""
        # English texts are matched by position, so only use them if the lists line up
        if len(checkpoints_en) != len(checkpoints):
            checkpoints_en = []

        hidden = self._cancelled_indices(checkpoints)
        events = []
        codes = []

        for index, checkpoint in enumerate(checkpoints):
            if index in hidden:
                continue

            status = (checkpoint.get("Status") or "").strip()
            status_en = (checkpoints_en[index].get("Status") or "").strip() if checkpoints_en else ""
            date_part, time_part = self._split_timestamp(checkpoint.get("StatusDate") or "")

            events.append(TrackingEvent(
                date=date_part,
                time=time_part,
                location=(checkpoint.get("Shop") or "").strip(),
                status=status,
                status_translated=status_en or self.translate_status(status, self.STATUS_TRANSLATIONS),
            ))
            codes.append(checkpoint.get("StatusCode") or "")

        # API returns events oldest first; keep newest first like the other couriers
        events.reverse()
        codes.reverse()

        latest = events[0] if events else None
        status = latest.status_translated if latest else "Unknown"

        return TrackingResult(
            success=True,
            tracking_number=tracking_number,
            courier=self.COURIER_CODE,
            courier_name=self.COURIER_NAME,
            status=status,
            status_category=self._get_category(codes),
            events=events,
            latest_event=latest,
            raw_data=data,
        )

    def _cancelled_indices(self, checkpoints: list[dict[str, Any]]) -> set[int]:
        """Find events that were cancelled by a later event (hidden on the website)."""
        codes = [checkpoint.get("StatusCode") for checkpoint in checkpoints]
        hidden: set[int] = set()

        for first, second in self.CANCEL_PAIRS:
            pair = None
            for index, code in enumerate(codes):
                if code == first and second in codes[index + 1:]:
                    pair = (index, codes.index(second, index + 1))
            if pair:
                hidden.update(pair)

        return hidden

    def _get_category(self, codes: list[str]) -> str:
        """Determine the status category from the status codes."""
        if not codes:
            return "unknown"
        if any(code in self.DELIVERY_STATUSES and code not in self.CANCEL_STATUSES for code in codes):
            return "delivered"
        if all(code in self.CREATE_STATUSES for code in codes):
            return "created"
        return "in_transit"

    def _split_timestamp(self, timestamp: str) -> tuple[str, str]:
        """Convert a .NET style timestamp to local (Athens) date and time strings."""
        # Trim fractional seconds (.NET may send 7 digits) and normalize "Z"
        cleaned = re.sub(r"(\.\d+)", "", timestamp.strip()).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            return timestamp, ""

        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(self.TIMEZONE)
        return parsed.strftime("%Y-%m-%d"), parsed.strftime("%H:%M")
