"""Tests for the config flow - specifically courier selection dropdown."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestCourierDropdown:
    """Tests for the courier dropdown functionality."""

    @pytest.mark.asyncio
    async def test_add_tracking_saves_courier_selection(self):
        """Test that courier selection is properly saved when adding tracking."""
        from custom_components.greek_courier_tracker.config_flow import (
            GreekCourierTrackerOptionsFlow,
        )

        # Create a mock config entry
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.options = {
            "tracking_numbers": [],
            "scan_interval": 30,
        }
        mock_entry.data = {}

        # Create options flow
        flow = GreekCourierTrackerOptionsFlow(mock_entry)

        # Submit the form with a specific courier selected
        result = await flow.async_step_add_tracking(
            user_input={
                "tracking_number": "1234567890",
                "name": "My Package",
                "courier": "acs",
                "stop_tracking_delivered": False,
            }
        )

        # Verify the entry is created
        assert result["type"] == "create_entry"

        # Verify the data includes the courier selection
        data = result["data"]
        tracking_numbers = data["tracking_numbers"]
        assert len(tracking_numbers) == 1
        assert tracking_numbers[0]["courier"] == "acs"
        assert tracking_numbers[0]["tracking_number"] == "1234567890"

    @pytest.mark.asyncio
    async def test_add_tracking_default_courier_is_auto(self):
        """Test that courier defaults to 'auto' when not specified."""
        from custom_components.greek_courier_tracker.config_flow import (
            GreekCourierTrackerOptionsFlow,
        )

        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.options = {
            "tracking_numbers": [],
            "scan_interval": 30,
        }
        mock_entry.data = {}

        flow = GreekCourierTrackerOptionsFlow(mock_entry)

        # Submit without specifying courier (should default to auto)
        result = await flow.async_step_add_tracking(
            user_input={
                "tracking_number": "1234567890",
                "name": "My Package",
                "stop_tracking_delivered": False,
            }
        )

        assert result["type"] == "create_entry"
        data = result["data"]
        tracking_numbers = data["tracking_numbers"]
        assert tracking_numbers[0]["courier"] == "auto"

    @pytest.mark.asyncio
    async def test_edit_tracking_updates_courier_selection(self):
        """Test that courier selection is properly updated when editing tracking."""
        from custom_components.greek_courier_tracker.config_flow import (
            GreekCourierTrackerOptionsFlow,
        )

        # Create a mock config entry
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.options = {
            "tracking_numbers": [
                {
                    "tracking_number": "1234567890",
                    "name": "My Package",
                    "stop_tracking_delivered": False,
                    "courier": "auto",
                }
            ],
            "scan_interval": 30,
        }
        mock_entry.data = {}

        # Create options flow
        flow = GreekCourierTrackerOptionsFlow(mock_entry)

        # Submit the edit form with a different courier
        result = await flow.async_step_edit_tracking(
            user_input={
                "name": "My Package",
                "courier": "geniki",
                "stop_tracking_delivered": True,
            },
            tracking_number="1234567890"
        )

        # Verify the entry is created
        assert result["type"] == "create_entry"

        # Verify the data includes the updated courier selection
        data = result["data"]
        tracking_numbers = data["tracking_numbers"]
        assert len(tracking_numbers) == 1
        assert tracking_numbers[0]["courier"] == "geniki"
        assert tracking_numbers[0]["stop_tracking_delivered"] is True

    @pytest.mark.asyncio
    async def test_add_tracking_all_couriers_valid(self):
        """Test that all valid courier codes can be saved."""
        from custom_components.greek_courier_tracker.config_flow import (
            GreekCourierTrackerOptionsFlow,
            COURIER_LIST,
        )

        valid_couriers = [code for code, _ in COURIER_LIST]

        for courier_code in valid_couriers:
            mock_entry = MagicMock()
            mock_entry.entry_id = "test_entry"
            mock_entry.options = {
                "tracking_numbers": [],
                "scan_interval": 30,
            }
            mock_entry.data = {}

            flow = GreekCourierTrackerOptionsFlow(mock_entry)

            result = await flow.async_step_add_tracking(
                user_input={
                    "tracking_number": f"TEST{courier_code}",
                    "name": f"Test {courier_code}",
                    "courier": courier_code,
                    "stop_tracking_delivered": False,
                }
            )

            assert result["type"] == "create_entry"
            assert result["data"]["tracking_numbers"][0]["courier"] == courier_code

    def test_courier_list_structure(self):
        """Test that COURIER_LIST has proper structure."""
        from custom_components.greek_courier_tracker.config_flow import COURIER_LIST

        # Verify COURIER_LIST is a list of tuples
        assert isinstance(COURIER_LIST, list)

        # Verify each item is a tuple with (code, name)
        for item in COURIER_LIST:
            assert isinstance(item, tuple)
            assert len(item) == 2
            code, name = item
            assert isinstance(code, str)
            assert isinstance(name, str)

        # Verify 'auto' is first
        assert COURIER_LIST[0][0] == "auto"

        # Verify all expected couriers are present
        courier_codes = [code for code, _ in COURIER_LIST]
        expected_codes = ["auto", "acs", "box_now", "courier_center", "elta", "geniki", "speedex"]
        for code in expected_codes:
            assert code in courier_codes, f"Missing courier code: {code}"

    @pytest.mark.asyncio
    async def test_migration_adds_courier_field(self):
        """Test that migration adds courier field to existing data."""
        from custom_components.greek_courier_tracker.config_flow import _migrate_tracking_data

        # Test old format (list of strings)
        old_data = ["SE123456789GR", "BN12345678"]
        migrated = _migrate_tracking_data(old_data)

        assert len(migrated) == 2
        assert all("courier" in item for item in migrated)
        assert all(item["courier"] == "auto" for item in migrated)

        # Test format without courier field
        data_without_courier = [
            {
                "tracking_number": "SE123456789GR",
                "name": "Package 1",
                "stop_tracking_delivered": False,
            }
        ]
        migrated = _migrate_tracking_data(data_without_courier)

        assert len(migrated) == 1
        assert "courier" in migrated[0]
        assert migrated[0]["courier"] == "auto"

    @pytest.mark.asyncio
    async def test_parse_tracking_numbers_includes_courier(self):
        """Test that _parse_tracking_numbers includes courier field."""
        from custom_components.greek_courier_tracker.config_flow import _parse_tracking_numbers

        result = _parse_tracking_numbers("SE123456789GR, BN12345678")

        assert len(result) == 2
        assert all("courier" in item for item in result)
        assert all(item["courier"] == "auto" for item in result)

    @pytest.mark.asyncio
    async def test_parse_tracking_numbers_with_names(self):
        """Test that _parse_tracking_numbers handles the TRACKING:NAME format."""
        from custom_components.greek_courier_tracker.config_flow import _parse_tracking_numbers

        # Test single tracking number with name
        result = _parse_tracking_numbers("SE123456789GR:My Package")
        assert len(result) == 1
        assert result[0]["tracking_number"] == "SE123456789GR"
        assert result[0]["name"] == "My Package"
        assert result[0]["courier"] == "auto"

        # Test multiple tracking numbers with mixed formats
        result = _parse_tracking_numbers(
            "SE123456789GR:Package 1, BN12345678:Package 2, ACS1234567890"
        )
        assert len(result) == 3
        assert result[0]["tracking_number"] == "SE123456789GR"
        assert result[0]["name"] == "Package 1"
        assert result[1]["tracking_number"] == "BN12345678"
        assert result[1]["name"] == "Package 2"
        assert result[2]["tracking_number"] == "ACS1234567890"
        assert result[2]["name"] == "ACS1234567890"  # No name provided, defaults to tracking number

        # Test newline separated
        result = _parse_tracking_numbers(
            "SE123456789GR:First Package\nBN12345678:Second Package"
        )
        assert len(result) == 2
        assert result[0]["name"] == "First Package"
        assert result[1]["name"] == "Second Package"

        # Test with custom courier
        result = _parse_tracking_numbers("SE123456789GR:ELTA Package", courier="elta")
        assert len(result) == 1
        assert result[0]["courier"] == "elta"
        assert result[0]["name"] == "ELTA Package"

    @pytest.mark.asyncio
    async def test_add_tracking_duplicate_number_error(self):
        """Test that duplicate tracking numbers are rejected."""
        from custom_components.greek_courier_tracker.config_flow import (
            GreekCourierTrackerOptionsFlow,
        )

        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.options = {
            "tracking_numbers": [
                {
                    "tracking_number": "1234567890",
                    "name": "Existing Package",
                    "stop_tracking_delivered": False,
                    "courier": "auto",
                }
            ],
            "scan_interval": 30,
        }
        mock_entry.data = {}

        flow = GreekCourierTrackerOptionsFlow(mock_entry)

        # Try to add duplicate
        result = await flow.async_step_add_tracking(
            user_input={
                "tracking_number": "1234567890",
                "name": "Duplicate Package",
                "courier": "acs",
                "stop_tracking_delivered": False,
            }
        )

        # Should return form with error, not create entry
        assert result["type"] == "form"
        assert "tracking_number" in result["errors"]

    @pytest.mark.asyncio
    async def test_add_tracking_empty_number_error(self):
        """Test that empty tracking numbers are rejected."""
        from custom_components.greek_courier_tracker.config_flow import (
            GreekCourierTrackerOptionsFlow,
        )

        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.options = {
            "tracking_numbers": [],
            "scan_interval": 30,
        }
        mock_entry.data = {}

        flow = GreekCourierTrackerOptionsFlow(mock_entry)

        result = await flow.async_step_add_tracking(
            user_input={
                "tracking_number": "",
                "name": "Empty Package",
                "courier": "acs",
                "stop_tracking_delivered": False,
            }
        )

        assert result["type"] == "form"
        assert "tracking_number" in result["errors"]


class TestCourierCoordinatorIntegration:
    """Tests for coordinator integration with courier selection."""

    @pytest.mark.asyncio
    async def test_coordinator_uses_selected_courier(self):
        """Test that coordinator uses the selected courier instead of auto-detect."""
        from custom_components.greek_courier_tracker import GreekCourierDataUpdateCoordinator
        from custom_components.greek_courier_tracker.couriers import get_courier

        mock_hass = MagicMock()
        mock_hass.data = {}
        mock_hass.config = MagicMock()
        mock_hass.config.asynchronous_panel = False

        tracking_configs = {
            "1234567890": {
                "tracking_number": "1234567890",
                "name": "My Package",
                "stop_tracking_delivered": False,
                "courier": "acs",  # Selected courier
            }
        }

        coordinator = GreekCourierDataUpdateCoordinator(
            hass=mock_hass,
            tracking_numbers=["1234567890"],
            tracking_configs=tracking_configs,
            scan_interval=30,
        )

        # Verify the tracking config has the courier field
        assert coordinator.tracking_configs["1234567890"]["courier"] == "acs"

        # Verify we can get the courier instance
        courier = get_courier("acs")
        assert courier is not None
        assert courier.COURIER_CODE == "acs"

    @pytest.mark.asyncio
    async def test_coordinator_auto_detect_when_courier_is_auto(self):
        """Test that coordinator uses auto-detect when courier is 'auto'."""
        from custom_components.greek_courier_tracker import GreekCourierDataUpdateCoordinator

        mock_hass = MagicMock()
        mock_hass.data = {}
        mock_hass.config = MagicMock()
        mock_hass.config.asynchronous_panel = False

        tracking_configs = {
            "1234567890": {
                "tracking_number": "1234567890",
                "name": "My Package",
                "stop_tracking_delivered": False,
                "courier": "auto",  # Auto-detect
            }
        }

        coordinator = GreekCourierDataUpdateCoordinator(
            hass=mock_hass,
            tracking_numbers=["1234567890"],
            tracking_configs=tracking_configs,
            scan_interval=30,
        )

        # Verify the tracking config has courier set to 'auto'
        assert coordinator.tracking_configs["1234567890"]["courier"] == "auto"


class TestCourierSelectionWithAllCodes:
    """Tests for all courier codes work correctly."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("courier_code,expected_name", [
        ("auto", "Auto-detect (try all)"),
        ("acs", "ACS Courier"),
        ("elta", "ELTA Courier"),
        ("geniki", "Geniki Taxydromiki"),
        ("speedex", "SpeedEx"),
        ("courier_center", "Courier Center"),
        ("box_now", "Box Now"),
    ])
    async def test_each_courier_code_can_be_saved(self, courier_code, expected_name):
        """Test that each courier code can be saved properly."""
        from custom_components.greek_courier_tracker.config_flow import (
            GreekCourierTrackerOptionsFlow,
        )
        from custom_components.greek_courier_tracker.const import COURIER_NAMES

        # Verify the courier name exists
        assert courier_code in COURIER_NAMES
        assert COURIER_NAMES[courier_code] == expected_name

        # Verify it can be saved in a tracking entry
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        mock_entry.options = {
            "tracking_numbers": [],
            "scan_interval": 30,
        }
        mock_entry.data = {}

        flow = GreekCourierTrackerOptionsFlow(mock_entry)

        result = await flow.async_step_add_tracking(
            user_input={
                "tracking_number": f"TEST{courier_code}",
                "name": f"Test {courier_code}",
                "courier": courier_code,
                "stop_tracking_delivered": False,
            }
        )

        assert result["type"] == "create_entry"
        assert result["data"]["tracking_numbers"][0]["courier"] == courier_code
