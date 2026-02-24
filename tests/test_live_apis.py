"""Live API tests for Greek Courier Tracker.

These tests make actual HTTP requests to courier APIs.
They should be run separately from unit tests and may require valid tracking numbers.

To run only these tests:
    pytest tests/test_live_apis.py -v

To skip these tests in regular runs:
    pytest tests/ -v -m "not live"
"""

import pytest
import asyncio

from custom_components.greek_courier_tracker.couriers import (
    ELTACourier,
    ACSCourier,
    SpeedExCourier,
    BoxNowCourier,
    GenikiCourier,
    CourierCenterCourier,
)


# Test tracking numbers - these should be valid numbers for each courier
# In production, these would be real tracking numbers. For testing, we use
# format-valid numbers that may or may not return actual data.
TEST_TRACKING_NUMBERS = {
    "elta": [
        "SE101046219GR",  # Example format
        "EL123456789GR",  # Example format
    ],
    "acs": [
        "1234567890",  # 10 digits
    ],
    "box_now": [
        "BN12345678",  # BN + 8 digits
    ],
    "speedex": [
        "SP12345678",  # SP + 8 digits
        "123456789EL",  # 9 digits + 2 letters
    ],
    "geniki": [
        "GT123456789",  # GT + 9 digits
        "123456789012",  # 12 digits
    ],
    "courier_center": [
        "CC12345678",  # CC + 8 digits
    ],
}


@pytest.mark.live
@pytest.mark.asyncio
class TestELTALiveAPI:
    """Live API tests for ELTA Courier."""

    async def test_elta_api_reachable(self):
        """Test that ELTA API is reachable."""
        courier = ELTACourier()
        # Use a tracking number that's likely to exist or return a valid response
        result = await courier.track("SE101046219GR")

        # We don't assert success since we don't have a guaranteed valid number
        # Just verify the API call completed without throwing an exception
        assert result is not None
        assert result.courier == "elta"
        assert result.tracking_number == "SE101046219GR"

    async def test_elta_multiple_formats(self):
        """Test ELTA with different tracking number formats."""
        courier = ELTACourier()

        for tn in TEST_TRACKING_NUMBERS["elta"]:
            result = await courier.track(tn)
            assert result is not None
            assert result.courier == "elta"


@pytest.mark.live
@pytest.mark.asyncio
class TestACSLiveAPI:
    """Live API tests for ACS Courier."""

    async def test_acs_api_reachable(self):
        """Test that ACS API is reachable."""
        courier = ACSCourier()
        result = await courier.track("1234567890")

        assert result is not None
        assert result.courier == "acs"
        assert result.tracking_number == "1234567890"


@pytest.mark.live
@pytest.mark.asyncio
class TestBoxNowLiveAPI:
    """Live API tests for Box Now."""

    async def test_boxnow_api_reachable(self):
        """Test that Box Now API is reachable."""
        courier = BoxNowCourier()
        result = await courier.track("BN12345678")

        assert result is not None
        assert result.courier == "box_now"
        assert result.tracking_number == "BN12345678"


@pytest.mark.live
@pytest.mark.asyncio
class TestSpeedExLiveAPI:
    """Live API tests for SpeedEx."""

    async def test_speedex_api_reachable(self):
        """Test that SpeedEx API is reachable."""
        courier = SpeedExCourier()
        result = await courier.track("SP12345678")

        assert result is not None
        assert result.courier == "speedex"
        assert result.tracking_number == "SP12345678"


@pytest.mark.live
@pytest.mark.asyncio
class TestGenikiLiveAPI:
    """Live API tests for Geniki Taxydromiki."""

    async def test_geniki_api_reachable(self):
        """Test that Geniki API is reachable."""
        courier = GenikiCourier()
        result = await courier.track("GT123456789")

        assert result is not None
        assert result.courier == "geniki"
        assert result.tracking_number == "GT123456789"


@pytest.mark.live
@pytest.mark.asyncio
class TestCourierCenterLiveAPI:
    """Live API tests for Courier Center."""

    async def test_courier_center_api_reachable(self):
        """Test that Courier Center API is reachable."""
        courier = CourierCenterCourier()
        result = await courier.track("CC12345678")

        assert result is not None
        assert result.courier == "courier_center"
        assert result.tracking_number == "CC12345678"


@pytest.mark.live
@pytest.mark.asyncio
class TestAllCouriersReachable:
    """Test that all courier APIs are reachable."""

    async def test_all_couriers_respond(self):
        """Test that all couriers respond to tracking requests."""
        couriers = {
            "elta": ELTACourier(),
            "acs": ACSCourier(),
            "box_now": BoxNowCourier(),
            "speedex": SpeedExCourier(),
            "geniki": GenikiCourier(),
            "courier_center": CourierCenterCourier(),
        }

        test_numbers = {
            "elta": "SE101046219GR",
            "acs": "1234567890",
            "box_now": "BN12345678",
            "speedex": "SP12345678",
            "geniki": "GT123456789",
            "courier_center": "CC12345678",
        }

        results = {}
        for code, courier in couriers.items():
            result = await courier.track(test_numbers[code])
            results[code] = result
            assert result is not None
            assert result.courier == code

        # Verify all couriers responded
        assert len(results) == len(couriers)
