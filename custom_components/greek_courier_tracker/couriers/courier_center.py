"""Courier Center tracking implementation."""

from __future__ import annotations

import re
from typing import Any

import aiohttp
import async_timeout
from bs4 import BeautifulSoup

from ..const import CourierType
from .base import BaseCourier, TrackingEvent, TrackingResult


class CourierCenterCourier(BaseCourier):
    """Courier Center tracking implementation."""
    
    COURIER_CODE = CourierType.COURIER_CENTER
    COURIER_NAME = "Courier Center"
    
    TRACKING_URL = "https://courier.gr/track/result"
    
    # Tracking number patterns
    PATTERNS = [
        r"^\d{10,12}$",    # 10-12 digits (Courier Center format)
    ]

    # Status translations
    STATUS_TRANSLATIONS = {
        "DeliveryCompleted": "Delivered",
        "InTransit": "In Transit",
        "Received": "Received",
        "OutForDelivery": "Out for Delivery",
    }

    async def track(self, tracking_number: str) -> TrackingResult:
        """Track a Courier Center shipment."""
        tracking_number = tracking_number.strip().upper()
        
        params = {"tracknr": tracking_number}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with async_timeout.timeout(30):
                    async with session.get(
                        self.TRACKING_URL,
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

                        html = await response.text()
                        # Remove UTF-8 BOM if present
                        if html.startswith('\ufeff'):
                            html = html[1:]
                        return self._parse_html(tracking_number, html)
                        
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
    
    def _parse_html(self, tracking_number: str, html: str) -> TrackingResult:
        """Parse Courier Center HTML response."""
        soup = BeautifulSoup(html, "html.parser")
        
        # Check for error message
        if soup.find("h4", {"class": "error"}):
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
        
        # Find tracking rows
        rows = soup.find_all("div", {"class": "tr"})
        
        # Skip header row
        for row in rows[1:]:
            date_elem = row.find("div", {"id": "date"})
            date = date_elem.text.strip() if date_elem else ""
            
            time_elem = row.find("div", {"id": "time"})
            time = time_elem.text.strip() if time_elem else ""
            
            area_elem = row.find("div", {"id": "area"})
            location = area_elem.text.strip() if area_elem else ""
            
            action_elem = row.find("div", {"id": "action"})
            status = action_elem.text.strip() if action_elem else ""
            
            if date:  # Only add if we have valid data
                events.append(TrackingEvent(
                    date=date,
                    time=time,
                    location=location,
                    status=status,
                    status_translated=self.translate_status(status, self.STATUS_TRANSLATIONS),
                ))
        
        latest = events[0] if events else None
        status = latest.status_translated if latest else "Unknown"
        
        # Check for delivery status
        status_div = soup.find("div", {"class": "status"})
        is_delivered = status_div and "DeliveryCompleted" in status_div.text
        
        category = "delivered" if is_delivered else self.get_status_category(
            status,
            ["deliverycompleted", "delivered"],
            ["intransit", "transit"],
            ["received", "new"]
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
        )
