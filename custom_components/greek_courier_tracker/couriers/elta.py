"""ELTA Courier tracking implementation."""

from __future__ import annotations

import re
from typing import Any

import aiohttp
import asyncio

from ..const import CourierType
from .base import BaseCourier, TrackingEvent, TrackingResult


class ELTACourier(BaseCourier):
    """ELTA Courier tracking implementation."""
    
    COURIER_CODE = CourierType.ELTA
    COURIER_NAME = "ELTA Courier"
    
    API_URL = "https://www.elta-courier.gr/track.php"
    BASE_URL = "https://www.elta-courier.gr"
    
    # Tracking number patterns
    PATTERNS = [
        r"^SE\d{9}GR$",      # SE101046219GR
        r"^EL\d{9}GR$",
        r"^GR\d{9}[A-Z]{2}$",
        r"^[A-Z]{2}\d{9}GR$",
    ]
    
    # Status translations
    STATUS_TRANSLATIONS = {
        "Αποστολή παραδόθηκε": "Delivered",
        "Αποστολή παραδόθηκε σε": "Delivered to",
        "Αποστολή βρίσκεται σε στάδιο μεταφοράς": "In Transit",
        "Δημιουργία ΣΥ.ΔΕ.ΤΑ.": "Shipment Created",
        "Παραλαβή από": "Picked up by",
    }
    
    @classmethod
    def matches_tracking_number(cls, tracking_number: str) -> bool:
        """Check if tracking number matches ELTA format."""
        tn = tracking_number.strip().upper()
        for pattern in cls.PATTERNS:
            if re.match(pattern, tn):
                return True
        return False
    
    async def track(self, tracking_number: str) -> TrackingResult:
        """Track an ELTA shipment."""
        tracking_number = tracking_number.strip().upper()
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/search?br={tracking_number}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with asyncio.timeout(30):
                    async with session.post(
                        self.API_URL,
                        data=f"number={tracking_number}&s=0",
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
                        
                        result = await response.json()
                        return self._parse_response(tracking_number, result)
                        
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
        """Parse the ELTA API response."""
        if data.get("status") != 1:
            return TrackingResult(
                success=False,
                tracking_number=tracking_number,
                courier=self.COURIER_CODE,
                courier_name=self.COURIER_NAME,
                status="Error",
                status_category="error",
                events=[],
                error_message=data.get("result", "Unknown error"),
            )
        
        tracking_data = data.get("result", {}).get(tracking_number, {})
        
        if tracking_data.get("status") == 1:
            raw_events = tracking_data.get("result", [])
            events = []
            
            for event in raw_events:
                translated = self.translate_status(
                    event.get("status", ""),
                    self.STATUS_TRANSLATIONS
                )
                events.append(TrackingEvent(
                    date=event.get("date", ""),
                    time=event.get("time", ""),
                    location=event.get("place", ""),
                    status=event.get("status", ""),
                    status_translated=translated,
                ))
            
            latest = events[0] if events else None
            status = latest.status_translated if latest else "Unknown"
            category = self.get_status_category(
                status,
                ["παραδόθηκε", "delivered"],
                ["μεταφοράς", "transit"],
                ["δημιουργία", "created", "συ.δε.τα."]
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
        
        elif tracking_data.get("status") == 2:
            return TrackingResult(
                success=True,
                tracking_number=tracking_number,
                courier=self.COURIER_CODE,
                courier_name=self.COURIER_NAME,
                status=tracking_data.get("result", "Message"),
                status_category="unknown",
                events=[],
            )
        
        else:
            return TrackingResult(
                success=True,
                tracking_number=tracking_number,
                courier=self.COURIER_CODE,
                courier_name=self.COURIER_NAME,
                status="Not Found",
                status_category="unknown",
                events=[],
            )
