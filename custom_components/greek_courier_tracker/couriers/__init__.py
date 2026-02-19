"""Couriers package - Greek courier tracking implementations."""

from .base import BaseCourier, TrackingEvent, TrackingResult
from .elta import ELTACourier
from .acs import ACSCourier
from .speedex import SpeedExCourier
from .boxnow import BoxNowCourier
from .geniki import GenikiCourier
from .courier_center import CourierCenterCourier

__all__ = [
    "BaseCourier",
    "TrackingEvent",
    "TrackingResult",
    "ELTACourier",
    "ACSCourier",
    "SpeedExCourier",
    "BoxNowCourier",
    "GenikiCourier",
    "CourierCenterCourier",
]

# Registry of all couriers
COURIER_REGISTRY: dict[str, type[BaseCourier]] = {
    "elta": ELTACourier,
    "acs": ACSCourier,
    "speedex": SpeedExCourier,
    "box_now": BoxNowCourier,
    "geniki": GenikiCourier,
    "courier_center": CourierCenterCourier,
}


def get_courier(courier_code: str) -> BaseCourier | None:
    """Get a courier instance by code.
    
    Args:
        courier_code: The courier code (e.g., 'elta', 'acs')
        
    Returns:
        Courier instance or None if not found
    """
    courier_class = COURIER_REGISTRY.get(courier_code)
    if courier_class:
        return courier_class()
    return None


def detect_courier(tracking_number: str) -> str | None:
    """Detect the courier based on tracking number format.
    
    Args:
        tracking_number: The tracking number to analyze
        
    Returns:
        Courier code or None if not detected
    """
    tn = tracking_number.strip().upper()
    
    # Check each courier in order of specificity
    # More specific patterns first
    
    # Box Now: BN prefix
    if BoxNowCourier.matches_tracking_number(tn):
        return "box_now"
    
    # Courier Center: CC prefix
    if CourierCenterCourier.matches_tracking_number(tn):
        return "courier_center"
    
    # SpeedEx: SP prefix
    if SpeedExCourier.matches_tracking_number(tn):
        return "speedex"
    
    # ELTA: SE/EL/GR patterns
    if ELTACourier.matches_tracking_number(tn):
        return "elta"
    
    # Geniki: GT prefix or 10-12 digits
    if GenikiCourier.matches_tracking_number(tn):
        return "geniki"
    
    # ACS: 10 digits (most generic, check last)
    if ACSCourier.matches_tracking_number(tn):
        return "acs"
    
    return None


async def track_with_auto_detect(tracking_number: str) -> TrackingResult:
    """Track a shipment with automatic courier detection.
    
    Args:
        tracking_number: The tracking number to track
        
    Returns:
        TrackingResult from the detected courier
    """
    courier_code = detect_courier(tracking_number)
    
    if courier_code is None:
        from .base import TrackingResult
        return TrackingResult(
            success=False,
            tracking_number=tracking_number,
            courier="unknown",
            courier_name="Unknown Courier",
            status="Error",
            status_category="error",
            events=[],
            error_message="Could not detect courier from tracking number format",
        )
    
    courier = get_courier(courier_code)
    if courier is None:
        from .base import TrackingResult
        return TrackingResult(
            success=False,
            tracking_number=tracking_number,
            courier=courier_code,
            courier_name=courier_code,
            status="Error",
            status_category="error",
            events=[],
            error_message=f"Courier '{courier_code}' not implemented",
        )
    
    return await courier.track(tracking_number)
