"""Simple tests for courier tracking functionality without complex mocking."""

import pytest

from custom_components.greek_courier_tracker.couriers import (
    ELTACourier,
    ACSCourier,
    SpeedExCourier,
    BoxNowCourier,
    GenikiCourier,
    CourierCenterCourier,
    get_courier,
)
from custom_components.greek_courier_tracker.couriers.base import TrackingResult, TrackingEvent


class TestCourierBasics:
    """Basic tests for courier classes that don't require mocking."""

    def test_elta_courier_properties(self):
        """Test ELTA courier properties."""
        courier = ELTACourier()
        assert courier.COURIER_CODE == "elta"
        assert courier.COURIER_NAME == "ELTA Courier"

    def test_acs_courier_properties(self):
        """Test ACS courier properties."""
        courier = ACSCourier()
        assert courier.COURIER_CODE == "acs"
        assert courier.COURIER_NAME == "ACS Courier"

    def test_speedex_courier_properties(self):
        """Test SpeedEx courier properties."""
        courier = SpeedExCourier()
        assert courier.COURIER_CODE == "speedex"
        assert courier.COURIER_NAME == "SpeedEx"

    def test_boxnow_courier_properties(self):
        """Test Box Now courier properties."""
        courier = BoxNowCourier()
        assert courier.COURIER_CODE == "box_now"
        assert courier.COURIER_NAME == "Box Now"

    def test_geniki_courier_properties(self):
        """Test Geniki courier properties."""
        courier = GenikiCourier()
        assert courier.COURIER_CODE == "geniki"
        assert courier.COURIER_NAME == "Geniki Taxydromiki"

    def test_courier_center_properties(self):
        """Test Courier Center properties."""
        courier = CourierCenterCourier()
        assert courier.COURIER_CODE == "courier_center"
        assert courier.COURIER_NAME == "Courier Center"


class TestStatusTranslation:
    """Tests for status translation functionality."""

    def test_elta_status_translation(self):
        """Test ELTA status translation."""
        courier = ELTACourier()
        result = courier.translate_status("Αποστολή παραδόθηκε", courier.STATUS_TRANSLATIONS)
        assert result == "Delivered"

    def test_acs_status_translation(self):
        """Test ACS status translation."""
        courier = ACSCourier()
        result = courier.translate_status("Η αποστολή παραδόθηκε", courier.STATUS_TRANSLATIONS)
        assert result == "Delivered"

    def test_status_category_delivered(self):
        """Test delivered status category."""
        courier = ELTACourier()
        category = courier.get_status_category(
            "Delivered",
            ["παραδόθηκε", "delivered"],
            ["μεταφοράς", "transit"],
            ["δημιουργία", "created"]
        )
        assert category == "delivered"

    def test_status_category_in_transit(self):
        """Test in transit status category."""
        courier = ELTACourier()
        category = courier.get_status_category(
            "In Transit",
            ["παραδόθηκε", "delivered"],
            ["μεταφοράς", "transit"],
            ["δημιουργία", "created"]
        )
        assert category == "in_transit"

    def test_status_category_unknown(self):
        """Test unknown status category."""
        courier = ELTACourier()
        category = courier.get_status_category(
            "Unknown Status",
            ["παραδόθηκε", "delivered"],
            ["μεταφοράς", "transit"],
            ["δημιουργία", "created"]
        )
        assert category == "unknown"


class TestCourierFactory:
    """Tests for the courier factory functions."""

    def test_get_courier_instances(self):
        """Test getting courier instances by code."""
        elta = get_courier("elta")
        assert elta is not None
        assert isinstance(elta, ELTACourier)

        acs = get_courier("acs")
        assert acs is not None
        assert isinstance(acs, ACSCourier)

        speedex = get_courier("speedex")
        assert speedex is not None
        assert isinstance(speedex, SpeedExCourier)

    def test_get_invalid_courier(self):
        """Test getting invalid courier returns None."""
        assert get_courier("invalid") is None
        assert get_courier("") is None
        assert get_courier(None) is None


class TestTrackingResult:
    """Tests for TrackingResult dataclass."""

    def test_tracking_result_creation(self):
        """Test creating a TrackingResult."""
        event = TrackingEvent(
            date="15-02-2026",
            time="14:30",
            location="Athens",
            status="Delivered",
            status_translated="Delivered"
        )

        result = TrackingResult(
            success=True,
            tracking_number="SE123456789GR",
            courier="elta",
            courier_name="ELTA Courier",
            status="Delivered",
            status_category="delivered",
            events=[event],
            latest_event=event
        )

        assert result.success is True
        assert result.tracking_number == "SE123456789GR"
        assert result.courier == "elta"
        assert result.status == "Delivered"
        assert result.status_category == "delivered"
        assert len(result.events) == 1
        assert result.latest_event is not None

    def test_tracking_result_error(self):
        """Test creating an error TrackingResult."""
        result = TrackingResult(
            success=False,
            tracking_number="SE123456789GR",
            courier="elta",
            courier_name="ELTA Courier",
            status="Error",
            status_category="error",
            events=[],
            error_message="Network error"
        )

        assert result.success is False
        assert result.status_category == "error"
        assert result.error_message == "Network error"
        assert len(result.events) == 0
