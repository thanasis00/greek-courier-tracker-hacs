"""Base courier tracking module."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class TrackingEvent:
    """Represents a single tracking event."""
    date: str
    time: str | None
    location: str
    status: str
    status_translated: str | None = None


@dataclass
class TrackingResult:
    """Result of a tracking request."""
    success: bool
    tracking_number: str
    courier: str
    courier_name: str
    status: str
    status_category: str  # delivered, in_transit, created, unknown, error
    events: list[TrackingEvent]
    latest_event: TrackingEvent | None = None
    error_message: str | None = None
    raw_data: dict[str, Any] | None = None


class BaseCourier(ABC):
    """Base class for courier tracking implementations."""
    
    # Subclasses must define these
    COURIER_CODE: str = ""
    COURIER_NAME: str = ""
    
    @abstractmethod
    async def track(self, tracking_number: str) -> TrackingResult:
        """Track a shipment by tracking number.
        
        Args:
            tracking_number: The tracking number to look up
            
        Returns:
            TrackingResult with shipment status and events
        """
        pass
    
    @classmethod
    @abstractmethod
    def matches_tracking_number(cls, tracking_number: str) -> bool:
        """Check if the tracking number matches this courier's format.
        
        Args:
            tracking_number: The tracking number to check
            
        Returns:
            True if the tracking number matches this courier's format
        """
        pass
    
    def translate_status(self, status: str, translations: dict[str, str]) -> str:
        """Translate Greek status to English.
        
        Args:
            status: The status text (may be in Greek)
            translations: Dictionary of translations
            
        Returns:
            Translated status or original if no translation found
        """
        status_lower = status.lower()
        
        # Check for exact match
        for greek, english in translations.items():
            if greek.lower() == status_lower:
                return english
        
        # Check for partial match
        for greek, english in translations.items():
            if greek.lower() in status_lower or status_lower in greek.lower():
                return english
        
        return status
    
    def get_status_category(self, status: str, delivered_keywords: list[str], 
                           in_transit_keywords: list[str], 
                           created_keywords: list[str]) -> str:
        """Determine the status category from status text.
        
        Args:
            status: The status text
            delivered_keywords: Keywords indicating delivery
            in_transit_keywords: Keywords indicating transit
            created_keywords: Keywords indicating creation
            
        Returns:
            Category string: delivered, in_transit, created, or unknown
        """
        status_lower = status.lower()
        
        for keyword in delivered_keywords:
            if keyword.lower() in status_lower:
                return "delivered"
        
        for keyword in in_transit_keywords:
            if keyword.lower() in status_lower:
                return "in_transit"
        
        for keyword in created_keywords:
            if keyword.lower() in status_lower:
                return "created"
        
        return "unknown"
    
    def parse_date(self, date_str: str, formats: list[str] | None = None) -> datetime | None:
        """Parse a date string into a datetime object.
        
        Args:
            date_str: The date string to parse
            formats: List of format strings to try
            
        Returns:
            Parsed datetime or None if parsing failed
        """
        if formats is None:
            formats = ["%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, TypeError):
                continue
        
        return None
