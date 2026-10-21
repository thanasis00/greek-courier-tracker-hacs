"""SpeedEx Courier tracking implementation."""

from __future__ import annotations

import re
from datetime import datetime
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
    
    # Page shown in an iframe by the speedex.gr tracking page
    TRACKING_URL = "https://www.speedex.gr/speedex/NewTrackAndTrace.aspx"
    TRACKING_PAGE_URL = "https://www.speedex.gr/isapohi.asp?voucher_code={tracking_number}"
    
    # Tracking number patterns
    PATTERNS = [
        r"^\d{12}$",         # 12 digits
        r"^\d{9}[A-Z]{2}$",  # 9 digits + 2 letters
    ]
    
    # Status translations (matched without Greek accents)
    STATUS_TRANSLATIONS = {
        "Η ΑΠΟΣΤΟΛΗ ΠΑΡΑΔΟΘΗΚΕ": "Delivered",
        "ΑΝΑΜΟΝΗ ΑΝΑΘΕΣΗΣ ΑΠΟ ΑΠΟΣΤΟΛΕΑ": "Shipment Created",
        "ΠΑΡΑΛΑΒΗ ΣΤΟ ΚΑΤΑΣΤΗΜΑ": "Picked Up",
        "ΕΞΑΓΩΓΗ ΑΠΟ ΚΑΤΑΣΤΗΜΑ": "Left the Store",
        "ΕΙΣΑΓΩΓΗ ΣΕ Δ/Κ": "Arrived at Hub",
        "ΕΞΑΓΩΓΗ ΑΠΟ Δ/Κ": "Left the Hub",
        "ΕΙΣΑΓΩΓΗ ΣΕ ΚΑΤΑΣΤΗΜΑ": "Arrived at Store",
        "ΣΕ ΜΕΤΑΦΟΡΑ": "In Transit",
        "ΠΑΡΑΛΑΒΗ": "Picked Up",
        "ΑΠΟΣΤΟΛΗ": "Shipped",
    }

    # The sender has created the voucher but not handed the parcel over yet
    CREATED_KEYWORDS = ["αναμονη αναθεσης"]

    DATE_TIME = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})(?:\s*στις\s*(\d{1,2}:\d{2}))?")
    PHONE = re.compile(r"^[\d\s+()-]+$")

    async def track(self, tracking_number: str) -> TrackingResult:
        """Track a SpeedEx shipment by scraping their website."""
        tracking_number = tracking_number.strip().upper()
        
        params = {"number": tracking_number}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        
        try:
            async with self._client_session() as session:
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
            status = " ".join(title_elem.text.split()) if title_elem else ""
            date, time, location = self._parse_card_info(card)
            
            events.append(TrackingEvent(
                date=date,
                time=time,
                location=location,
                status=status,
                status_translated=self.translate_status(self._normalize(status), self.STATUS_TRANSLATIONS),
            ))
        
        # The page lists the events oldest first; keep newest first like the other couriers
        events = sorted(reversed(events), key=self._event_time, reverse=True)
        
        latest = events[0] if events else None
        status = latest.status_translated if latest else "Unknown"
        
        return TrackingResult(
            success=True,
            tracking_number=tracking_number,
            courier=self.COURIER_CODE,
            courier_name=self.COURIER_NAME,
            status=status,
            status_category=self._get_category(soup, events),
            events=events,
            latest_event=latest,
        )

    def _parse_card_info(self, card: Any) -> tuple[str, str, str]:
        """Read the date, time and place of a timeline card.

        The card has a line with "19/10/2026 στις 15:34", one with the store
        address (", ΚΗΦΙΣΙΑ" when it has none) and one with its phone number.
        Older pages had "Αθήνα, 15/01/2025 στις 14:30" on a single line.
        """
        date = time = location = ""
        for span in card.find_all("span", {"class": "font-small-3"}):
            # "View on Google Maps"
            if span.find("a"):
                continue
            text = " ".join(span.text.split())
            match = self.DATE_TIME.search(text)
            if match and not date:
                date, time = match.group(1), match.group(2) or ""
                text = text[:match.start()] + text[match.end():]
            text = ", ".join(part.strip() for part in text.split(",") if part.strip())
            if text and not location and not self.PHONE.match(text):
                location = text
        return date, time, location

    def _event_time(self, event: TrackingEvent) -> datetime:
        """Sortable time of an event (events without one sort last)."""
        try:
            return datetime.strptime(f"{event.date} {event.time or '00:00'}", "%d/%m/%Y %H:%M")
        except ValueError:
            return datetime.min

    def _get_category(self, soup: BeautifulSoup, events: list[TrackingEvent]) -> str:
        """Determine the status category from all the events."""
        if not events:
            return "unknown"
        statuses = [self._normalize(event.status) for event in events]
        # The website colours the delivery event with "delivered-speedex"
        if soup.find(class_="delivered-speedex") or any(
            "παραδοθηκε" in status and "δεν " not in status for status in statuses
        ):
            return "delivered"
        if all(any(keyword in status for keyword in self.CREATED_KEYWORDS) for status in statuses):
            return "created"
        return "in_transit"
