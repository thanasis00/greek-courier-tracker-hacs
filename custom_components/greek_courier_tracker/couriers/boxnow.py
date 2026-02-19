"""Box Now tracking implementation."""

from __future__ import annotations

import re
from typing import Any

import aiohttp
import asyncio

from ..const import CourierType
from .base import BaseCourier, TrackingEvent, TrackingResult


class BoxNowCourier(BaseCourier):
    """Box Now locker delivery tracking implementation."""
    
    COURIER_CODE = CourierType.BOX_NOW
    COURIER_NAME = "Box Now"
    
    API_URL = "https://api-production.boxnow.gr/api/v1/parcels:track"
    BASE_URL = "https://boxnow.gr"
    
    # Tracking number patterns
    PATTERNS = [
        r"^BN\d{8,10}$",   # BN prefix
        r"^\d{10}$",       # 10 digits
    ]
    
    # Event type translations
    EVENT_TRANSLATIONS = {
        "new": "New Order",
        "in-depot": "In Depot",
        "final-destination": "At Destination Locker",
        "delivered": "Delivered",
        "expired": "Expired",
        "returned": "Returned",
    }
    
    @classmethod
    def matches_tracking_number(cls, tracking_number: str) -> bool:
        """Check if tracking number matches Box Now format."""
        tn = tracking_number.strip().upper()
        # Box Now uses 10 digits or BN prefix
        if re.match(r"^BN\d{8,10}$", tn):
            return True
        # 10 digit numbers are ambiguous - could be ACS too
        # We'll check for BN prefix as primary identifier
        return False
    
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
            async with aiohttp.ClientSession() as session:
                async with asyncio.timeout(30):
                    async with session.post(
                        self.API_URL,
                        json={"parcelId": tracking_number},
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
            create_time = event.get("createTime", "")
            # Parse ISO timestamp: "2025-01-15T13:55:32.015Z"
            date_part = create_time.split("T")[0] if "T" in create_time else create_time
            time_part = ""
            if "T" in create_time:
                time_part = create_time.split("T")[1][:8]  # HH:MM:SS
            
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
        
        latest = events[0] if events else None
        state = parcel.get("state", "")
        status = self.EVENT_TRANSLATIONS.get(state, state)
        
        category = "delivered" if state == "delivered" else self.get_status_category(
            status,
            ["delivered"],
            ["depot", "destination"],
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
        )
