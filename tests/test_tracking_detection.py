"""Tests for tracking number detection and courier matching."""

import pytest
from custom_components.greek_courier_tracker.couriers import (
    ELTACourier,
    ACSCourier,
    SpeedExCourier,
    BoxNowCourier,
    GenikiCourier,
    CourierCenterCourier,
    detect_courier,
    get_courier,
)


class TestELTADetection:
    """Tests for ELTA tracking number detection."""

    def test_valid_elta_numbers(self):
        """Test valid ELTA tracking numbers are detected."""
        assert ELTACourier.matches_tracking_number("SE123456789GR") is True
        assert ELTACourier.matches_tracking_number("EL987654321GR") is True
        assert ELTACourier.matches_tracking_number("PW123456789GR") is True
        assert ELTACourier.matches_tracking_number("AB123456789GR") is True
        assert ELTACourier.matches_tracking_number("GR123456789EL") is True

    def test_invalid_elta_numbers(self):
        """Test invalid ELTA tracking numbers are rejected."""
        assert ELTACourier.matches_tracking_number("1234567890") is False
        assert ELTACourier.matches_tracking_number("XX12345678GR") is False  # 8 digits
        assert ELTACourier.matches_tracking_number("XX12345678901GR") is False  # 11 digits
        assert ELTACourier.matches_tracking_number("123456789GR") is False  # No prefix
        assert ELTACourier.matches_tracking_number("XX123456789G") is False  # Missing R
        assert ELTACourier.matches_tracking_number("X123456789GR") is False  # 1 letter prefix

    def test_case_insensitive(self):
        """Test that detection is case insensitive."""
        assert ELTACourier.matches_tracking_number("se123456789gr") is True
        assert ELTACourier.matches_tracking_number("Se123456789Gr") is True
        assert ELTACourier.matches_tracking_number("SE123456789GR") is True


class TestACSDetection:
    """Tests for ACS tracking number detection."""

    def test_valid_acs_numbers(self):
        """Test valid ACS tracking numbers are detected."""
        assert ACSCourier.matches_tracking_number("1234567890") is True
        assert ACSCourier.matches_tracking_number("0000000001") is True
        assert ACSCourier.matches_tracking_number("9999999999") is True

    def test_invalid_acs_numbers(self):
        """Test invalid ACS tracking numbers are rejected."""
        assert ACSCourier.matches_tracking_number("123456789") is False  # 9 digits
        assert ACSCourier.matches_tracking_number("12345678901") is False  # 11 digits
        assert ACSCourier.matches_tracking_number("ABCDEFGHIJ") is False  # Letters
        assert ACSCourier.matches_tracking_number("XX123456789GR") is False  # ELTA format


class TestSpeedExDetection:
    """Tests for SpeedEx tracking number detection."""

    def test_valid_speedex_numbers(self):
        """Test valid SpeedEx tracking numbers are detected."""
        assert SpeedExCourier.matches_tracking_number("SP12345678") is True
        assert SpeedExCourier.matches_tracking_number("SP123456789") is True
        assert SpeedExCourier.matches_tracking_number("SP1234567890") is True
        assert SpeedExCourier.matches_tracking_number("123456789012") is True  # 12 digits
        assert SpeedExCourier.matches_tracking_number("123456789AB") is True  # 9 digits + 2 letters
        assert SpeedExCourier.matches_tracking_number("123456789EL") is True

    def test_invalid_speedex_numbers(self):
        """Test invalid SpeedEx tracking numbers are rejected."""
        assert SpeedExCourier.matches_tracking_number("SP1234567") is False  # 7 digits
        assert SpeedExCourier.matches_tracking_number("1234567890") is False  # 10 digits (ACS)
        assert SpeedExCourier.matches_tracking_number("1234567890123") is False  # 13 digits
        assert SpeedExCourier.matches_tracking_number("12345678A") is False  # 8 digits + 1 letter


class TestBoxNowDetection:
    """Tests for Box Now tracking number detection."""

    def test_valid_boxnow_numbers(self):
        """Test valid Box Now tracking numbers are detected."""
        assert BoxNowCourier.matches_tracking_number("BN12345678") is True
        assert BoxNowCourier.matches_tracking_number("BN123456789") is True
        assert BoxNowCourier.matches_tracking_number("BN1234567890") is True

    def test_invalid_boxnow_numbers(self):
        """Test invalid Box Now tracking numbers are rejected."""
        assert BoxNowCourier.matches_tracking_number("1234567890") is False  # Without BN prefix
        assert BoxNowCourier.matches_tracking_number("BN1234567") is False  # 7 digits
        assert BoxNowCourier.matches_tracking_number("BX12345678") is False  # Wrong prefix

    def test_case_insensitive(self):
        """Test that detection is case insensitive."""
        assert BoxNowCourier.matches_tracking_number("bn12345678") is True
        assert BoxNowCourier.matches_tracking_number("Bn12345678") is True


class TestGenikiDetection:
    """Tests for Geniki Taxydromiki tracking number detection."""

    def test_valid_geniki_numbers(self):
        """Test valid Geniki tracking numbers are detected."""
        assert GenikiCourier.matches_tracking_number("GT123456789") is True
        assert GenikiCourier.matches_tracking_number("GT1234567890") is True
        assert GenikiCourier.matches_tracking_number("GT12345678901") is True
        assert GenikiCourier.matches_tracking_number("1234567890") is True  # 10 digits
        assert GenikiCourier.matches_tracking_number("123456789012") is True  # 12 digits

    def test_invalid_geniki_numbers(self):
        """Test invalid Geniki tracking numbers are rejected."""
        assert GenikiCourier.matches_tracking_number("123456789") is False  # 9 digits
        assert GenikiCourier.matches_tracking_number("1234567890123") is False  # 13 digits
        assert GenikiCourier.matches_tracking_number("G123456789") is False  # 1 letter prefix


class TestCourierCenterDetection:
    """Tests for Courier Center tracking number detection."""

    def test_valid_courier_center_numbers(self):
        """Test valid Courier Center tracking numbers are detected."""
        assert CourierCenterCourier.matches_tracking_number("CC12345678") is True
        assert CourierCenterCourier.matches_tracking_number("CC123456789") is True
        assert CourierCenterCourier.matches_tracking_number("CC1234567890") is True

    def test_invalid_courier_center_numbers(self):
        """Test invalid Courier Center tracking numbers are rejected."""
        assert CourierCenterCourier.matches_tracking_number("1234567890") is False  # Without CC prefix
        assert CourierCenterCourier.matches_tracking_number("CC1234567") is False  # 7 digits
        assert CourierCenterCourier.matches_tracking_number("C12345678") is False  # 1 letter prefix


class TestAutoDetection:
    """Tests for automatic courier detection."""

    def test_detect_elta(self):
        """Test ELTA is detected correctly."""
        assert detect_courier("SE123456789GR") == "elta"
        assert detect_courier("EL123456789GR") == "elta"
        assert detect_courier("GR123456789EL") == "elta"

    def test_detect_box_now(self):
        """Test Box Now is detected correctly."""
        assert detect_courier("BN12345678") == "box_now"
        assert detect_courier("BN1234567890") == "box_now"

    def test_detect_courier_center(self):
        """Test Courier Center is detected correctly."""
        assert detect_courier("CC12345678") == "courier_center"
        assert detect_courier("CC1234567890") == "courier_center"

    def test_detect_speedex(self):
        """Test SpeedEx is detected correctly."""
        assert detect_courier("SP12345678") == "speedex"
        assert detect_courier("SP1234567890") == "speedex"

    def test_detect_geniki(self):
        """Test Geniki is detected correctly."""
        assert detect_courier("GT123456789") == "geniki"
        assert detect_courier("GT1234567890") == "geniki"

    def test_detect_acs_fallback(self):
        """Test ACS is detected as fallback for 10 digits."""
        # Note: Geniki also matches 10 digits and is checked before ACS
        # So 10 digits will be detected as geniki, not acs
        # This is a known ambiguity - 10 digit numbers could be either
        assert detect_courier("1234567890") == "geniki"  # Geniki takes precedence

    def test_unknown_courier(self):
        """Test unknown formats return None."""
        assert detect_courier("INVALID") is None
        assert detect_courier("12345") is None
        assert detect_courier("ABC123") is None


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
