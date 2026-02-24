"""SpeedEx Courier tracking implementation."""

from __future__ import annotations

import re
from typing import Any

import aiohttp
import async_timeout
from bs4 import BeautifulSoup

from ..const import CourierType
from .base import BaseCourier, TrackingEvent, TrackingResult


class SpeedExCourier(BaseCourier):
    """SpeedEx Courier tracking implementation."""
    
    COURIER_CODE = CourierType.SPEEDEX
    COURIER_NAME = "SpeedEx"
    
    TRACKING_URL = "http://www.speedex.gr/speedex/NewTrackAndTrace.aspx"
    
    # Tracking number patterns
    PATTERNS = [
        r"^\d{12}$",         # 12 digits
        r"^\d{9}[A-Z]{2}$",  # 9 digits + 2 letters
    ]
    
    # Status translations
    STATUS_TRANSLATIONS = {
        "Η ΑΠΟΣΤΟΛΗ ΠΑΡΑΔΟΘΗΚΕ": "Delivered",
        "ΣΕ ΜΕΤΑΦΟΡΑ": "In Transit",
        "ΠΑΡΑΛΑΒΗ": "Picked Up",
        "ΑΠΟΣΤΟΛΗ": "Shipped",
    }

    async def track(self, tracking_number: str) -> TrackingResult:
        """Track a SpeedEx shipment by scraping their website."""
        tracking_number = tracking_number.strip().upper()
        
        params = {"number": tracking_number}
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
        """Parse SpeedEx HTML response."""
        soup = BeautifulSoup(html, "html.parser")
        
        # Check for "not found" message
        if soup.find("div", {"class": "alert-warning"}):
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
        
        # Find timeline cards
        cards = soup.find_all("div", {"class": "timeline-card"})
        
        for card in cards:
            # Get status description
            title_elem = card.find("h4", {"class": "card-title"})
            status = title_elem.text.strip() if title_elem else ""
            
            # Get location and date/time
            info_elem = card.find("span", {"class": "font-small-3"})
            info_text = info_elem.text.strip() if info_elem else ""
            
            # Parse: "Αθήνα, 15/01/2025 στις 14:30"
            location = ""
            date = ""
            time = ""
            
            if info_text:
                parts = info_text.split(", ")
                if len(parts) >= 2:
                    location = parts[0]
                    date_time = parts[1]
                    # Parse date and time
                    if "στις" in date_time:
                        date_part, time_part = date_time.split(" στις ")
                        date = date_part.strip()
                        time = time_part.strip()
                    else:
                        date = date_time
            
            events.append(TrackingEvent(
                date=date,
                time=time,
                location=location,
                status=status,
                status_translated=self.translate_status(status, self.STATUS_TRANSLATIONS),
            ))
        
        latest = events[0] if events else None
        status = latest.status_translated if latest else "Unknown"
        
        # Check if delivered
        is_delivered = any(
            e.status.upper() == "Η ΑΠΟΣΤΟΛΗ ΠΑΡΑΔΟΘΗΚΕ" 
            for e in events
        )
        
        category = "delivered" if is_delivered else self.get_status_category(
            status,
            ["παραδόθηκ", "delivered"],
            ["μεταφορ", "transit"],
            ["παραλαβή", "picked"]
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
