"""ACS Courier tracking implementation."""

from __future__ import annotations

import re
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
    
    # Tracking number patterns (10 digits)
    PATTERNS = [r"^\d{10}$"]
    
    # Status translations
    STATUS_TRANSLATIONS = {
        "Η αποστολή παρελήφθη": "Shipment Received",
        "Η αποστολή παραδόθηκε": "Delivered",
        "Η αποστολή βρίσκεται σε διάκριση": "In Transit",
        "Η αποστολή δεν βρέθηκε": "Not Found",
    }

    async def track(self, tracking_number: str) -> TrackingResult:
        """Track an ACS shipment.
        
        Note: ACS requires a dynamic x-encrypted-key token that must be 
        fetched from the website. This implementation uses the public API.
        """
        tracking_number = tracking_number.strip()
        
        # First, try to get a token from the website
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/",
            "x-country": "GR",
            "x-subscription-id": "",
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                # Try the public API without token first
                async with async_timeout.timeout(30):
                    url = self.API_URL.format(tracking_number=tracking_number)
                    async with session.get(url, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            return self._parse_response(tracking_number, data)
                        elif response.status == 401:
                            # Token required - try to fetch it
                            token = await self._fetch_token(session)
                            if token:
                                headers["x-encrypted-key"] = token
                                async with session.get(url, headers=headers) as resp:
                                    if resp.status == 200:
                                        data = await resp.json()
                                        return self._parse_response(tracking_number, data)
                        
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
    
    async def _fetch_token(self, session: aiohttp.ClientSession) -> str | None:
        """Fetch the dynamic token from ACS website."""
        try:
            async with session.get(
                f"{self.BASE_URL}/el/myacs/anafores-apostolwn/anazitisi-apostolwn/"
            ) as response:
                if response.status == 200:
                    text = await response.text()
                    # Remove UTF-8 BOM if present
                    if text.startswith('\ufeff'):
                        text = text[1:]
                    # Look for publicToken in the HTML
                    match = re.search(r'publicToken["\']?\s*[:=]\s*["\']([^"\']+)["\']', text)
                    if match:
                        return match.group(1)
        except Exception:
            pass
        return None
    
    def _parse_response(self, tracking_number: str, data: dict[str, Any]) -> TrackingResult:
        """Parse the ACS API response."""
        items = data.get("items", [])
        
        if not items:
            return TrackingResult(
                success=True,
                tracking_number=tracking_number,
                courier=self.COURIER_CODE,
                courier_name=self.COURIER_NAME,
                status="Not Found",
                status_category="unknown",
                events=[],
            )
        
        parcel = items[0]
        raw_events = parcel.get("statusHistory", [])
        events = []
        
        for event in raw_events:
            date_str = event.get("controlPointDate", "")
            # Parse ISO date
            date_part = date_str.split("T")[0] if "T" in date_str else date_str
            time_part = date_str.split("T")[1][:5] if "T" in date_str and len(date_str.split("T")) > 1 else ""
            
            events.append(TrackingEvent(
                date=date_part,
                time=time_part,
                location=event.get("controlPoint", ""),
                status=event.get("description", ""),
                status_translated=self.translate_status(
                    event.get("description", ""),
                    self.STATUS_TRANSLATIONS
                ),
            ))
        
        latest = events[0] if events else None
        is_delivered = parcel.get("isDelivered", False)
        
        status = "Delivered" if is_delivered else (latest.status_translated if latest else "Unknown")
        category = "delivered" if is_delivered else self.get_status_category(
            status,
            ["παραδόθηκε", "delivered"],
            ["διάκριση", "transit"],
            ["παρελήφθη", "received"]
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
