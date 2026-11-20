"""ELTA Courier tracking implementation."""

from __future__ import annotations

import re
from typing import Any

import aiohttp
import async_timeout

from ..const import CourierType
from .base import (
    STAGE_CREATED,
    STAGE_IN_TRANSIT,
    STAGE_OUT_FOR_DELIVERY,
    STAGE_READY_FOR_PICKUP,
    BaseCourier,
    TrackingEvent,
    TrackingResult,
    stage_category,
)


class ELTACourier(BaseCourier):
    """ELTA Courier tracking implementation."""
    
    COURIER_CODE = CourierType.ELTA
    COURIER_NAME = "ELTA Courier"
    
    API_URL = "https://www.elta-courier.gr/track.php"
    BASE_URL = "https://www.elta-courier.gr"
    TRACKING_PAGE_URL = f"{BASE_URL}/search?br={{tracking_number}}"
    
    # Tracking number patterns
    # ELTA uses various 2-letter prefixes (SE, EL, PW, etc.) + 9 digits + GR
    PATTERNS = [
        r"^[A-Z]{2}\d{9}GR$",      # XX123456789GR (SE, EL, PW, etc.)
        r"^GR\d{9}[A-Z]{2}$",      # GR123456789XX (international)
    ]
    
    # Status translations
    STATUS_TRANSLATIONS = {
        "Αποστολή παραδόθηκε": "Delivered",
        "Αποστολή παραδόθηκε σε": "Delivered to",
        "Αποστολή βρίσκεται σε στάδιο μεταφοράς": "In Transit",
        "Δημιουργία ΣΥ.ΔΕ.ΤΑ.": "Shipment Created",
        "Παραλαβή από": "Picked up by",
    }

    # ELTA's own phrases (problems such as "Απουσία παραλήπτη" are common rules)
    STATUS_RULES = [
        ("συ.δε.τα", STAGE_CREATED, None),
        ("βρισκεται στο καταστημα", STAGE_READY_FOR_PICKUP, None),
        ("δυνατοτητα παραλαβης", STAGE_READY_FOR_PICKUP, None),
        ("σε διανομεα", STAGE_OUT_FOR_DELIVERY, None),
        ("σταδιο μεταφορας", STAGE_IN_TRANSIT, None),
        ("παραλαβη αποστολης", STAGE_IN_TRANSIT, None),
        ("παραλαβη απο", STAGE_IN_TRANSIT, None),
        ("καταστημα", STAGE_IN_TRANSIT, None),
        ("διανομ", STAGE_IN_TRANSIT, None),
    ]

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
            async with self._client_session() as session:
                async with async_timeout.timeout(30):
                    async with session.post(
                        self.API_URL,
                        data=f"number={tracking_number}&s=0",
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
                        
                        # ELTA API returns JSON with wrong content-type (text/html)
                        # Use text() then parse manually, handling potential UTF-8 BOM
                        text = await response.text()
                        # Remove UTF-8 BOM if present and parse JSON
                        import json
                        if text.startswith('\ufeff'):
                            text = text[1:]  # Remove BOM
                        result = json.loads(text)
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
            # ELTA has more phrases than we know; once the parcel has more than
            # one scan it has left the sender (see BaseCourier.progress)
            self.classify_events(events)
            stage, problem = self.progress(events)

            return TrackingResult(
                success=True,
                tracking_number=tracking_number,
                courier=self.COURIER_CODE,
                courier_name=self.COURIER_NAME,
                status=status,
                status_category=stage_category(stage),
                events=events,
                latest_event=latest,
                raw_data=data,
                stage=stage,
                problem=problem,
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
