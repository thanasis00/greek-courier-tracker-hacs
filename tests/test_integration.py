"""Integration tests for Greek Courier Tracker with Home Assistant."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_registry import EntityRegistry


class TestConfigFlow:
    """Tests for the config flow."""

    @pytest.mark.asyncio
    async def test_config_flow_single_tracking_number(self):
        """Test config flow with a single tracking number."""
        from custom_components.greek_courier_tracker.config_flow import (
            GreekCourierTrackerConfigFlow,
            _parse_tracking_numbers,
        )

        # Test parsing single number - now returns list of dicts
        result = _parse_tracking_numbers("SE123456789GR")
        assert len(result) == 1
        assert result[0]["tracking_number"] == "SE123456789GR"
        assert result[0]["name"] == "SE123456789GR"
        assert result[0]["stop_tracking_delivered"] is False

    @pytest.mark.asyncio
    async def test_config_flow_multiple_tracking_numbers(self):
        """Test config flow with multiple tracking numbers."""
        from custom_components.greek_courier_tracker.config_flow import _parse_tracking_numbers

        # Test parsing comma-separated
        result = _parse_tracking_numbers("SE123456789GR, BN12345678, 1234567890")
        assert len(result) == 3
        tracking_numbers = [r["tracking_number"] for r in result]
        assert "SE123456789GR" in tracking_numbers
        assert "BN12345678" in tracking_numbers
        assert "1234567890" in tracking_numbers

    @pytest.mark.asyncio
    async def test_config_flow_newline_separated(self):
        """Test config flow with newline-separated numbers."""
        from custom_components.greek_courier_tracker.config_flow import _parse_tracking_numbers

        result = _parse_tracking_numbers("SE123456789GR\nBN12345678\n1234567890")
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_config_flow_removes_duplicates(self):
        """Test that duplicate tracking numbers are removed."""
        from custom_components.greek_courier_tracker.config_flow import _parse_tracking_numbers

        result = _parse_tracking_numbers("SE123456789GR, SE123456789GR, BN12345678")
        assert len(result) == 2
        tracking_numbers = [r["tracking_number"] for r in result]
        assert tracking_numbers.count("SE123456789GR") == 1

    @pytest.mark.asyncio
    async def test_config_flow_normalizes_case(self):
        """Test that tracking numbers are normalized to uppercase."""
        from custom_components.greek_courier_tracker.config_flow import _parse_tracking_numbers

        result = _parse_tracking_numbers("se123456789gr, bn12345678")
        tracking_numbers = [r["tracking_number"] for r in result]
        assert "SE123456789GR" in tracking_numbers
        assert "BN12345678" in tracking_numbers

    @pytest.mark.asyncio
    async def test_config_flow_empty_numbers(self):
        """Test that empty tracking numbers are filtered out."""
        from custom_components.greek_courier_tracker.config_flow import _parse_tracking_numbers

        result = _parse_tracking_numbers("SE123456789GR, , , BN12345678")
        assert len(result) == 2


class TestCoordinator:
    """Tests for the data update coordinator."""

    @pytest.mark.asyncio
    async def test_coordinator_initialization(self):
        """Test coordinator initialization."""
        from custom_components.greek_courier_tracker import (
            GreekCourierDataUpdateCoordinator,
        )

        # Create a simple mock hass object without spec to avoid frame issues
        mock_hass = MagicMock()
        mock_hass.data = {}
        # Add required attributes that DataUpdateCoordinator might need
        mock_hass.config = MagicMock()
        mock_hass.config.asynchronous_panel = False

        tracking_configs = {
            "SE123456789GR": {
                "tracking_number": "SE123456789GR",
                "name": "SE123456789GR",
                "stop_tracking_delivered": False,
            },
            "BN12345678": {
                "tracking_number": "BN12345678",
                "name": "BN12345678",
                "stop_tracking_delivered": False,
            },
        }

        coordinator = GreekCourierDataUpdateCoordinator(
            hass=mock_hass,
            tracking_numbers=["SE123456789GR", "BN12345678"],
            tracking_configs=tracking_configs,
            scan_interval=1,
        )

        assert coordinator.tracking_numbers == ["SE123456789GR", "BN12345678"]
        assert coordinator.update_interval == timedelta(hours=1)

    @pytest.mark.asyncio
    async def test_coordinator_empty_tracking_numbers(self):
        """Test coordinator with no tracking numbers."""
        from custom_components.greek_courier_tracker import (
            GreekCourierDataUpdateCoordinator,
        )

        # Create a simple mock hass object without spec to avoid frame issues
        mock_hass = MagicMock()
        mock_hass.data = {}
        # Add required attributes that DataUpdateCoordinator might need
        mock_hass.config = MagicMock()
        mock_hass.config.asynchronous_panel = False

        coordinator = GreekCourierDataUpdateCoordinator(
            hass=mock_hass,
            tracking_numbers=[],
            tracking_configs={},
            scan_interval=30,
        )

        # Should return empty data
        result = await coordinator._async_update_data()
        assert result == {}


class TestSensorEntity:
    """Tests for the sensor entity."""

    @pytest.mark.asyncio
    async def test_sensor_properties(self):
        """Test sensor entity properties."""
        from custom_components.greek_courier_tracker.sensor import (
            GreekCourierTrackingSensor,
        )
        from custom_components.greek_courier_tracker.couriers.base import (
            TrackingResult,
            TrackingEvent,
        )

        mock_coordinator = AsyncMock()
        mock_coordinator.data = {
            "SE123456789GR": TrackingResult(
                success=True,
                tracking_number="SE123456789GR",
                courier="elta",
                courier_name="ELTA Courier",
                status="Delivered",
                status_category="delivered",
                events=[
                    TrackingEvent(
                        date="15-02-2026",
                        time="14:30",
                        location="Athens",
                        status="Delivered",
                        status_translated="Delivered",
                    )
                ],
                latest_event=TrackingEvent(
                    date="15-02-2026",
                    time="14:30",
                    location="Athens",
                    status="Delivered",
                    status_translated="Delivered",
                ),
            )
        }

        mock_entry = MagicMock(spec=ConfigEntry)
        mock_entry.entry_id = "test_entry_id"
        mock_entry.title = "Greek Courier Tracker"

        sensor = GreekCourierTrackingSensor(
            coordinator=mock_coordinator,
            entry=mock_entry,
            tracking_number="SE123456789GR",
            tracking_name="My Package",  # Custom name
            stop_tracking_delivered=False,
        )

        assert sensor.native_value == "Delivered"
        assert sensor.available is True
        assert sensor.unique_id == "test_entry_id_SE123456789GR"
        assert sensor.name == "My Package"  # Uses custom name

    @pytest.mark.asyncio
    async def test_sensor_attributes(self):
        """Test sensor entity attributes."""
        from custom_components.greek_courier_tracker.sensor import (
            GreekCourierTrackingSensor,
        )
        from custom_components.greek_courier_tracker.couriers.base import (
            TrackingResult,
            TrackingEvent,
        )

        mock_coordinator = AsyncMock()
        mock_coordinator.data = {
            "SE123456789GR": TrackingResult(
                success=True,
                tracking_number="SE123456789GR",
                courier="elta",
                courier_name="ELTA Courier",
                status="Delivered",
                status_category="delivered",
                events=[
                    TrackingEvent(
                        date="15-02-2026",
                        time="14:30",
                        location="Athens",
                        status="Delivered",
                        status_translated="Delivered",
                    )
                ],
                latest_event=TrackingEvent(
                    date="15-02-2026",
                    time="14:30",
                    location="Athens",
                    status="Delivered",
                    status_translated="Delivered",
                ),
            )
        }

        mock_entry = MagicMock(spec=ConfigEntry)
        mock_entry.entry_id = "test_entry_id"
        mock_entry.title = "Greek Courier Tracker"

        sensor = GreekCourierTrackingSensor(
            coordinator=mock_coordinator,
            entry=mock_entry,
            tracking_number="SE123456789GR",
            tracking_name="My Package",
            stop_tracking_delivered=False,
        )

        attrs = sensor.extra_state_attributes
        assert attrs["tracking_number"] == "SE123456789GR"
        assert attrs["courier"] == "elta"
        assert attrs["courier_name"] == "ELTA Courier"
        assert attrs["status"] == "Delivered"
        assert attrs["status_category"] == "delivered"
        assert attrs["delivered"] is True
        assert attrs["stop_tracking_delivered"] is False
        assert attrs["tracking_stopped"] is False
        assert len(attrs["events"]) == 1

    @pytest.mark.asyncio
    async def test_sensor_no_data(self):
        """Test sensor with no tracking data."""
        from custom_components.greek_courier_tracker.sensor import (
            GreekCourierTrackingSensor,
        )

        mock_coordinator = AsyncMock()
        mock_coordinator.data = {}

        mock_entry = MagicMock(spec=ConfigEntry)
        mock_entry.entry_id = "test_entry_id"
        mock_entry.title = "Greek Courier Tracker"

        sensor = GreekCourierTrackingSensor(
            coordinator=mock_coordinator,
            entry=mock_entry,
            tracking_number="SE123456789GR",
            tracking_name="SE123456789GR",  # Default name is tracking number
            stop_tracking_delivered=False,
        )

        assert sensor.native_value is None
        assert sensor.available is False
        assert sensor.extra_state_attributes == {}


class TestStatusTranslation:
    """Tests for status translation functionality."""

    @pytest.mark.asyncio
    async def test_status_category_delivered(self):
        """Test delivered status category detection."""
        from custom_components.greek_courier_tracker.couriers.base import BaseCourier

        class TestCourier(BaseCourier):
            COURIER_CODE = "test"
            COURIER_NAME = "Test"

            async def track(self, tracking_number):
                pass

        courier = TestCourier()

        category = courier.get_status_category(
            status="Η αποστολή παραδόθηκε",
            delivered_keywords=["παραδόθηκε", "delivered"],
            in_transit_keywords=["μεταφοράς", "transit"],
            created_keywords=["δημιουργία", "created"],
        )

        assert category == "delivered"

    @pytest.mark.asyncio
    async def test_status_category_in_transit(self):
        """Test in transit status category detection."""
        from custom_components.greek_courier_tracker.couriers.base import BaseCourier

        class TestCourier(BaseCourier):
            COURIER_CODE = "test"
            COURIER_NAME = "Test"

            async def track(self, tracking_number):
                pass

        courier = TestCourier()

        category = courier.get_status_category(
            status="Η αποστολή βρίσκεται σε στάδιο μεταφοράς",
            delivered_keywords=["παραδόθηκε", "delivered"],
            in_transit_keywords=["μεταφοράς", "transit"],
            created_keywords=["δημιουργία", "created"],
        )

        assert category == "in_transit"

    @pytest.mark.asyncio
    async def test_status_category_unknown(self):
        """Test unknown status category detection."""
        from custom_components.greek_courier_tracker.couriers.base import BaseCourier

        class TestCourier(BaseCourier):
            COURIER_CODE = "test"
            COURIER_NAME = "Test"

            async def track(self, tracking_number):
                pass

        courier = TestCourier()

        category = courier.get_status_category(
            status="Unknown status",
            delivered_keywords=["παραδόθηκε", "delivered"],
            in_transit_keywords=["μεταφοράς", "transit"],
            created_keywords=["δημιουργία", "created"],
        )

        assert category == "unknown"


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_auto_detect_with_invalid_number(self):
        """Test auto-detection with invalid tracking number format."""
        from custom_components.greek_courier_tracker.couriers import track_with_auto_detect

        result = await track_with_auto_detect("INVALID")

        # All couriers should fail
        assert result.success is False
        assert result.status_category == "error"
        # The courier will be one of the tried couriers (last one in registry)
        # or "unknown" if all return failure responses
        assert result.courier in ["unknown", "elta", "acs", "speedex", "box_now", "geniki", "courier_center"]
        # The error message may vary, just check it exists
        assert result.error_message is not None
        assert len(result.error_message) > 0

    def test_error_result_creation(self):
        """Test creating an error TrackingResult."""
        from custom_components.greek_courier_tracker.couriers.base import TrackingResult

        result = TrackingResult(
            success=False,
            tracking_number="TEST123",
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
