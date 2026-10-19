"""Skroutz Last Mile tracking implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
import async_timeout

from ..const import CourierType
from .base import BaseCourier, TrackingEvent, TrackingResult


class SkroutzCourier(BaseCourier):
    """Skroutz Last Mile tracking implementation."""

    COURIER_CODE = CourierType.SKROUTZ
    COURIER_NAME = "Skroutz Last Mile"

    # Same endpoint the skroutz.gr/track/<code> page calls from the browser
    API_URL = "https://api.sendx.gr/user/hp/{tracking_number}"
    BASE_URL = "https://www.skroutz.gr"

    # Tracking number patterns
    PATTERNS = [
        r"^[A-Z0-9]{13}$",   # 13 alphanumeric characters (e.g. E8GYRRONRYKL9)
    ]

    TIMEZONE = ZoneInfo("Europe/Athens")

    async def track(self, tracking_number: str) -> TrackingResult:
        """Track a Skroutz Last Mile shipment."""
        tracking_number = tracking_number.strip().upper()

        url = self.API_URL.format(tracking_number=tracking_number)
        params = {"skroutztracking": "1"}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with async_timeout.timeout(30):
                    async with session.get(url, params=params, headers=headers) as response:
                        # Unknown tracking numbers return HTTP 400 "Package not found"
                        if response.status in (400, 404):
                            return TrackingResult(
                                success=True,
                                tracking_number=tracking_number,
                                courier=self.COURIER_CODE,
                                courier_name=self.COURIER_NAME,
                                status="Not Found",
                                status_category="unknown",
                                events=[],
                            )

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

    def _parse_response(self, tracking_number: str, data: dict[str, Any]) -> TrackingResult:
        """Parse the Skroutz Last Mile API response."""
        if not isinstance(data, dict) or "status" not in data:
            return TrackingResult(
                success=True,
                tracking_number=tracking_number,
                courier=self.COURIER_CODE,
                courier_name=self.COURIER_NAME,
                status="Not Found",
                status_category="unknown",
                events=[],
            )

        # API returns events oldest first; keep newest first like the other couriers
        raw_events = sorted(
            data.get("trackingDetails") or [],
            key=lambda event: event.get("createdAt") or "",
            reverse=True,
        )
        events = []

        for event in raw_events:
            date_part, time_part = self._split_timestamp(event.get("createdAt") or "")
            status_gr = event.get("description_gr") or event.get("description") or ""

            events.append(TrackingEvent(
                date=date_part,
                time=time_part,
                location=event.get("notes") or "",
                status=status_gr,
                status_translated=event.get("description_en") or status_gr,
            ))

        latest = events[0] if events else None
        status = (
            data.get("statusTextEn")
            or data.get("statusTextGr")
            or (latest.status_translated if latest else None)
            or data.get("status")
            or "Unknown"
        )

        return TrackingResult(
            success=True,
            tracking_number=tracking_number,
            courier=self.COURIER_CODE,
            courier_name=self.COURIER_NAME,
            status=status,
            status_category=self._get_category(data),
            events=events,
            latest_event=latest,
            raw_data=data,
        )

    def _get_category(self, data: dict[str, Any]) -> str:
        """Determine the status category from the shipment timestamps."""
        if data.get("deliveredAt") or data.get("status") == "delivered":
            return "delivered"
        if data.get("isCompleteCancelled"):
            return "unknown"
        if data.get("pickedUpAt"):
            return "in_transit"
        return "created"

    def _split_timestamp(self, timestamp: str) -> tuple[str, str]:
        """Convert an ISO UTC timestamp to local (Athens) date and time strings."""
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return timestamp, ""

        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(self.TIMEZONE)
        return parsed.strftime("%Y-%m-%d"), parsed.strftime("%H:%M")
