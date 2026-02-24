"""Constants for the Greek Courier Tracker integration."""

from typing import Final
from enum import Enum

DOMAIN: Final = "greek_courier_tracker"

# Configuration keys
CONF_TRACKING_NUMBERS: Final = "tracking_numbers"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_NAME: Final = "name"
CONF_COURIER: Final = "courier"
CONF_TRACKING_NAME: Final = "tracking_name"  # Custom name for a tracking number
CONF_AUTO_REMOVE_DELIVERED: Final = "auto_remove_delivered"  # Auto-remove delivered packages
CONF_STOP_TRACKING_DELIVERED: Final = "stop_tracking_delivered"  # Stop tracking delivered packages

# Default values
DEFAULT_SCAN_INTERVAL: Final = 1  # hours
DEFAULT_NAME: Final = "Greek Courier Tracker"


class CourierType(str, Enum):
    """Supported courier types."""
    ELTA = "elta"
    ACS = "acs"
    GENIKI = "geniki"
    SPEEDEX = "speedex"
    COURIER_CENTER = "courier_center"
    BOX_NOW = "box_now"
    AUTO = "auto"


# Courier display names
COURIER_NAMES: Final[dict[str, str]] = {
    CourierType.ELTA: "ELTA Courier",
    CourierType.ACS: "ACS Courier",
    CourierType.GENIKI: "Geniki Taxydromiki",
    CourierType.SPEEDEX: "SpeedEx",
    CourierType.COURIER_CENTER: "Courier Center",
    CourierType.BOX_NOW: "Box Now",
    CourierType.AUTO: "Auto-detect (try all)",
}

# Tracking number patterns for auto-detection
TRACKING_PATTERNS: Final[dict[str, list[str]]] = {
    # ELTA: Any 2 letters + 9 digits + GR (e.g., SE, EL, PW, etc.)
    CourierType.ELTA: [
        r"^[A-Z]{2}\d{9}GR$",      # XX123456789GR (SE, EL, PW, etc.)
        r"^GR\d{9}[A-Z]{2}$",      # GR123456789XX (international)
    ],
    # ACS: 10 digits
    CourierType.ACS: [
        r"^\d{10}$",         # 1234567890
    ],
    # Geniki: 10-12 digits or alphanumeric
    CourierType.GENIKI: [
        r"^[A-Z]{2}\d{9,11}$",  # GT123456789
        r"^\d{10,12}$",         # 10-12 digits
    ],
    # SpeedEx: SP prefix + digits, or 12 digits
    CourierType.SPEEDEX: [
        r"^SP\d{8,10}$",     # SP12345678
        r"^\d{12}$",         # 12 digits
        r"^\d{9}[A-Z]{2}$",  # 9 digits + 2 letters
    ],
    # Courier Center: 10-12 digits
    CourierType.COURIER_CENTER: [
        r"^CC\d{8,10}$",     # CC prefix
        r"^\d{10,12}$",      # 10-12 digits
    ],
    # Box Now: 10 digits (similar to ACS but different API)
    CourierType.BOX_NOW: [
        r"^BN\d{8,10}$",     # BN prefix
    ],
}

# Status translations (Greek to English)
STATUS_TRANSLATIONS: Final[dict[str, str]] = {
    # ELTA
    "Αποστολή παραδόθηκε": "Delivered",
    "Αποστολή παραδόθηκε σε": "Delivered to",
    "Αποστολή βρίσκεται σε στάδιο μεταφοράς": "In Transit",
    "Δημιουργία ΣΥ.ΔΕ.ΤΑ.": "Shipment Created",
    "Παραλαβή από": "Picked up by",
    
    # ACS
    "Η αποστολή παρελήφθη": "Shipment received",
    "Η αποστολή παραδόθηκε": "Delivered",
    "Η αποστολή βρίσκεται σε διακίνηση": "In transit",
    
    # Geniki
    "ΠΑΡΑΔΟΣΗ": "Delivered",
    "ΜΕΤΑΦΟΡΑ": "In Transit",
    "ΠΑΡΑΛΑΒΗ": "Picked up",
    
    # SpeedEx
    "Η ΑΠΟΣΤΟΛΗ ΠΑΡΑΔΟΘΗΚΕ": "Delivered",
    "ΣΕ ΜΕΤΑΦΟΡΑ": "In Transit",
    
    # Courier Center
    "DeliveryCompleted": "Delivered",
    "InTransit": "In Transit",
    
    # Box Now
    "delivered": "Delivered",
    "in-depot": "In Depot",
    "final-destination": "At Destination",
    "new": "New Order",
}

# Delivery status keywords
DELIVERED_KEYWORDS: Final[list[str]] = [
    "παραδόθηκε", "παραδόθηκ", "delivered", "deliverycompleted",
    "παραδοση", "παράδοση"
]
IN_TRANSIT_KEYWORDS: Final[list[str]] = [
    "μεταφοράς", "transit", "μεταφορ", "διάκριση"
]
CREATED_KEYWORDS: Final[list[str]] = [
    "δημιουργία", "created", "συ.δε.τα.", "new", "παρελήφθη"
]
