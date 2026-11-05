"""Box Now tracking implementation."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
import async_timeout

from ..const import CourierType
from .base import BaseCourier, TrackingEvent, TrackingResult


class BoxNowCourier(BaseCourier):
    """Box Now locker delivery tracking implementation."""
    
    COURIER_CODE = CourierType.BOX_NOW
    COURIER_NAME = "Box Now"
    
    API_URL = "https://api-production.boxnow.gr/api/v1/parcels:track"
    BASE_URL = "https://boxnow.gr"
    TRACKING_PAGE_URL = f"{BASE_URL}/?track={{tracking_number}}"
    
    # Tracking number patterns
    PATTERNS = [
        r"^\d{10}$",       # 10 digits (Box Now format)
    ]

    # Event type translations
    EVENT_TRANSLATIONS = {
        "new": "New Order",
        "accepted-to-locker": "Accepted at Locker",
        "in-depot": "In Depot",
        "in-transit": "In Transit",
        "final-destination": "At Destination Locker",
        "in-final-destination": "At Destination Locker",
        "delivered": "Delivered",
        "expired": "Expired",
        "returned": "Returned",
    }

    TIMEZONE = ZoneInfo("Europe/Athens")

    async def track(self, tracking_number: str) -> TrackingResult:
        """Track a Box Now shipment."""
        tracking_number = tracking_number.strip()
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/",
        }
        
        try:
            async with self._client_session() as session:
                async with async_timeout.timeout(30):
                    async with session.post(
                        self.API_URL,
                        json={"parcelId": tracking_number},
                        headers=headers,
                    ) as response:
                        if response.status != 200:
                            self._note_refusal(response)
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
                        
                        data = await response.json()
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
        """Parse the Box Now API response."""
        parcels = data.get("data", [])
        
        if not parcels:
            return TrackingResult(
                success=True,
                tracking_number=tracking_number,
                courier=self.COURIER_CODE,
                courier_name=self.COURIER_NAME,
                status="Not Found",
                status_category="unknown",
                events=[],
            )
        
        parcel = parcels[0]
        raw_events = parcel.get("events", [])
        events = []
        
        for event in raw_events:
            date_part, time_part = self._local_date_time(event.get("createTime", ""))

            event_type = event.get("type", "")
            
            events.append(TrackingEvent(
                date=date_part,
                time=time_part,
                location=event.get("locationDisplayName", ""),
                status=event_type,
                status_translated=self.EVENT_TRANSLATIONS.get(
                    event_type, event_type
                ),
            ))
        
        # The API returns events oldest first; keep newest first like the other couriers
        events.sort(key=lambda event: (event.date, event.time or ""), reverse=True)
        latest = events[0] if events else None
        state = parcel.get("state", "")
        status = self.EVENT_TRANSLATIONS.get(state, state)
        
        category = "delivered" if state == "delivered" else self.get_status_category(
            status,
            ["delivered"],
            ["depot", "destination", "transit", "locker"],
            ["new"]
        )
        
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
            estimated_delivery=self._estimated_delivery(parcel, state),
        )

    def _local_date_time(self, timestamp: str) -> tuple[str, str]:
        """Convert an ISO UTC timestamp ("2025-01-15T13:55:32.015Z") to Athens date and time."""
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return timestamp, ""
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(self.TIMEZONE)
        return parsed.strftime("%Y-%m-%d"), parsed.strftime("%H:%M")

    def _estimated_delivery(self, parcel: dict[str, Any], state: str) -> str | None:
        """Return the expected day; the time of etaDate (around 04:00) is no real estimate."""
        if state == "delivered" or not parcel.get("etaDate"):
            return None
        date_part, time_part = self._local_date_time(str(parcel["etaDate"]))
        return date_part if time_part else None
