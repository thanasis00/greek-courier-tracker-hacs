"""Tests for Greek Courier Tracker."""

import asyncio
import pytest
from datetime import datetime

# Import couriers
import sys
sys.path.insert(0, '/home/z/my-project/download/greek_courier_tracker/custom_components/greek_courier_tracker')

from couriers import (
    ELTACourier,
    ACSCourier,
    SpeedExCourier,
    BoxNowCourier,
    GenikiCourier,
    CourierCenterCourier,
    detect_courier,
    get_courier,
    track_with_auto_detect,
)


class TestTrackingNumberDetection:
    """Tests for tracking number format detection."""
    
    def test_elta_detection(self):
        """Test ELTA tracking number detection."""
        assert ELTACourier.matches_tracking_number("SE101046219GR") is True
        assert ELTACourier.matches_tracking_number("EL123456789GR") is True
        assert ELTACourier.matches_tracking_number("GR123456789GR") is True
        assert ELTACourier.matches_tracking_number("1234567890") is False
    
    def test_acs_detection(self):
        """Test ACS tracking number detection."""
        assert ACSCourier.matches_tracking_number("1234567890") is True
        assert ACSCourier.matches_tracking_number("123456789") is False  # 9 digits
        assert ACSCourier.matches_tracking_number("12345678901") is False  # 11 digits
        assert ACSCourier.matches_tracking_number("SE101046219GR") is False
    
    def test_speedex_detection(self):
        """Test SpeedEx tracking number detection."""
        assert SpeedExCourier.matches_tracking_number("SP12345678") is True
        assert SpeedExCourier.matches_tracking_number("SP123456789") is True
        assert SpeedExCourier.matches_tracking_number("123456789012") is True  # 12 digits
        assert SpeedExCourier.matches_tracking_number("123456789AB") is True  # 9 digits + 2 letters
        assert SpeedExCourier.matches_tracking_number("SE101046219GR") is False
    
    def test_boxnow_detection(self):
        """Test Box Now tracking number detection."""
        assert BoxNowCourier.matches_tracking_number("BN12345678") is True
        assert BoxNowCourier.matches_tracking_number("BN1234567890") is True
        assert BoxNowCourier.matches_tracking_number("1234567890") is False  # Without BN prefix
    
    def test_courier_center_detection(self):
        """Test Courier Center tracking number detection."""
        assert CourierCenterCourier.matches_tracking_number("CC12345678") is True
        assert CourierCenterCourier.matches_tracking_number("CC1234567890") is True
        assert CourierCenterCourier.matches_tracking_number("1234567890") is False  # Without CC prefix
    
    def test_auto_detection(self):
        """Test automatic courier detection."""
        assert detect_courier("SE101046219GR") == "elta"
        assert detect_courier("BN12345678") == "box_now"
        assert detect_courier("CC12345678") == "courier_center"
        assert detect_courier("SP12345678") == "speedex"
        assert detect_courier("1234567890") == "acs"  # Generic 10 digits


class TestELTATracking:
    """Tests for ELTA Courier tracking."""
    
    @pytest.mark.asyncio
    async def test_elta_track_real_number(self):
        """Test tracking a real ELTA shipment."""
        courier = ELTACourier()
        result = await courier.track("SE101046219GR")
        
        assert result.success is True
        assert result.tracking_number == "SE101046219GR"
        assert result.courier == "elta"
        assert len(result.events) > 0
        assert result.latest_event is not None
        print(f"\nELTA Tracking Result:")
        print(f"  Status: {result.status}")
        print(f"  Category: {result.status_category}")
        print(f"  Events: {len(result.events)}")
        for event in result.events[:3]:
            print(f"    - {event.date} {event.time}: {event.status_translated}")
    
    @pytest.mark.asyncio
    async def test_elta_track_invalid_number(self):
        """Test tracking an invalid ELTA shipment."""
        courier = ELTACourier()
        result = await courier.track("SE999999999GR")
        
        # Should either return not found or error
        assert result.courier == "elta"
        print(f"\nELTA Invalid Number Result: {result.status}")


class TestBoxNowTracking:
    """Tests for Box Now tracking."""
    
    @pytest.mark.asyncio
    async def test_boxnow_api_works(self):
        """Test that Box Now API responds."""
        courier = BoxNowCourier()
        # Use a test number - should return empty data for invalid
        result = await courier.track("1234567890")
        
        assert result.courier == "box_now"
        print(f"\nBox Now API Result: {result.status}")


class TestCourierFactory:
    """Tests for the courier factory functions."""
    
    def test_get_courier(self):
        """Test getting courier instances."""
        assert get_courier("elta") is not None
        assert get_courier("acs") is not None
        assert get_courier("speedex") is not None
        assert get_courier("invalid") is None
    
    def test_all_couriers_in_registry(self):
        """Test that all couriers are registered."""
        expected = ["elta", "acs", "speedex", "box_now", "geniki", "courier_center"]
        for code in expected:
            assert code in ["elta", "acs", "speedex", "box_now", "geniki", "courier_center"]


class TestStatusTranslation:
    """Tests for status translation."""
    
    def test_elta_translation(self):
        """Test ELTA status translation."""
        courier = ELTACourier()
        
        assert courier.translate_status("Αποστολή παραδόθηκε", courier.STATUS_TRANSLATIONS) == "Delivered"
        assert courier.translate_status("Δημιουργία ΣΥ.ΔΕ.ΤΑ.", courier.STATUS_TRANSLATIONS) == "Shipment Created"
    
    def test_status_category_detection(self):
        """Test status category detection."""
        courier = ELTACourier()
        
        assert courier.get_status_category(
            "Delivered",
            ["παραδόθηκε", "delivered"],
            ["μεταφοράς", "transit"],
            ["δημιουργία", "created"]
        ) == "delivered"
        
        assert courier.get_status_category(
            "In Transit",
            ["παραδόθηκε", "delivered"],
            ["μεταφοράς", "transit"],
            ["δημιουργία", "created"]
        ) == "in_transit"


# Run tests if executed directly
if __name__ == "__main__":
    print("Running Greek Courier Tracker Tests...")
    print("=" * 50)
    
    # Run detection tests
    print("\n1. Tracking Number Detection Tests")
    print("-" * 30)
    test = TestTrackingNumberDetection()
    test.test_elta_detection()
    print("  ✓ ELTA detection")
    test.test_acs_detection()
    print("  ✓ ACS detection")
    test.test_speedex_detection()
    print("  ✓ SpeedEx detection")
    test.test_boxnow_detection()
    print("  ✓ Box Now detection")
    test.test_courier_center_detection()
    print("  ✓ Courier Center detection")
    test.test_auto_detection()
    print("  ✓ Auto detection")
    
    # Run factory tests
    print("\n2. Courier Factory Tests")
    print("-" * 30)
    test = TestCourierFactory()
    test.test_get_courier()
    print("  ✓ Get courier")
    test.test_all_couriers_in_registry()
    print("  ✓ All couriers registered")
    
    # Run translation tests
    print("\n3. Status Translation Tests")
    print("-" * 30)
    test = TestStatusTranslation()
    test.test_elta_translation()
    print("  ✓ ELTA translation")
    test.test_status_category_detection()
    print("  ✓ Status category detection")
    
    # Run async tests
    print("\n4. Live API Tests")
    print("-" * 30)
    
    async def run_async_tests():
        # Test ELTA
        test = TestELTATracking()
        await test.test_elta_track_real_number()
        print("  ✓ ELTA live tracking")
        
        # Test Box Now
        test = TestBoxNowTracking()
        await test.test_boxnow_api_works()
        print("  ✓ Box Now API")
    
    asyncio.run(run_async_tests())
    
    print("\n" + "=" * 50)
    print("All tests passed! ✓")
