"""Tests for courier factory functions."""

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
