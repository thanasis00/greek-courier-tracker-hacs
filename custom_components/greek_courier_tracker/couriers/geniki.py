"""Geniki Taxydromiki tracking implementation."""

from __future__ import annotations

import re
from typing import Any

import aiohttp
import async_timeout
from bs4 import BeautifulSoup

from ..const import CourierType
from .base import BaseCourier, TrackingEvent, TrackingResult


class GenikiCourier(BaseCourier):
    """Geniki Taxydromiki tracking implementation."""
    
    COURIER_CODE = CourierType.GENIKI
    COURIER_NAME = "Geniki Taxydromiki"
    
    TRACKING_URL = "https://www.taxydromiki.com/track/{tracking_number}"
    
    # Tracking number patterns
    PATTERNS = [
        r"^\d{10,12}$",       # 10-12 digits (Geniki format)
    ]
    
    # Status translations
    STATUS_TRANSLATIONS = {
        "ΠΑΡΑΔΟΣΗ": "Delivered",
        "ΜΕΤΑΦΟΡΑ": "In Transit",
        "ΠΑΡΑΛΑΒΗ": "Picked Up",
        "ΚΡΑΤΗΣΗ": "Held",
        "ΕΠΙΣΤΡΟΦΗ": "Returned",
    }

    async def track(self, tracking_number: str) -> TrackingResult:
        """Track a Geniki Taxydromiki shipment."""
        tracking_number = tracking_number.strip().upper()
        
        url = self.TRACKING_URL.format(tracking_number=tracking_number)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with async_timeout.timeout(30):
                    async with session.get(url, headers=headers) as response:
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
        """Parse Geniki HTML response."""
        soup = BeautifulSoup(html, "html.parser")
        
        # Check for "not found" message
        if soup.find("div", {"class": "empty-text"}):
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
        
        # Find tracking checkpoints
        checkpoints = soup.find_all("div", {"class": "tracking-checkpoint"})
        
        for checkpoint in checkpoints:
            status_elem = checkpoint.find("div", {"class": "checkpoint-status"})
            status = status_elem.text.strip() if status_elem else ""
            
            location_elem = checkpoint.find("div", {"class": "checkpoint-location"})
            location = location_elem.text.strip() if location_elem else ""
            
            date_elem = checkpoint.find("div", {"class": "checkpoint-date"})
            date_text = date_elem.text.strip() if date_elem else ""
            # Format: "Δευτέρα, 15/01/2025"
            date = date_text.split(", ")[-1] if ", " in date_text else date_text
            
            time_elem = checkpoint.find("div", {"class": "checkpoint-time"})
            time = time_elem.text.strip() if time_elem else ""
            
            events.append(TrackingEvent(
                date=date,
                time=time,
                location=location,
                status=status,
                status_translated=self.translate_status(status, self.STATUS_TRANSLATIONS),
            ))
        
        latest = events[0] if events else None
        status = latest.status_translated if latest else "Unknown"
        
        category = self.get_status_category(
            status,
            ["παραδοσ", "delivered"],
            ["μεταφορ", "transit"],
            ["παραλαβ", "picked"]
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
