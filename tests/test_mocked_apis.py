"""Mocked API tests for Greek Courier Tracker.

These tests use mocked HTTP responses to test courier implementations
without making actual API calls. This ensures tests are fast, reliable,
and don't require valid tracking numbers or network access.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp

from custom_components.greek_courier_tracker.couriers import (
    ELTACourier,
    ACSCourier,
    SpeedExCourier,
    BoxNowCourier,
    GenikiCourier,
    CourierCenterCourier,
)


@pytest.mark.asyncio
class TestELTAMockedAPI:
    """Mocked API tests for ELTA Courier."""

    async def test_elta_successful_tracking(self):
        """Test ELTA with successful tracking response."""
        courier = ELTACourier()

        mock_response = {
            "status": 1,
            "result": {
                "SE123456789GR": {
                    "status": 1,
                    "result": [
                        {
                            "date": "15-02-2026",
                            "time": "14:30",
                            "place": "ΑΘΗΝΑ",
                            "status": "Αποστολή παραδόθηκε"
                        },
                        {
                            "date": "14-02-2026",
                            "time": "10:15",
                            "place": "ΘΕΣΣΑΛΟΝΙΚΗ",
                            "status": "Αποστολή βρίσκεται σε στάδιο μεταφοράς"
                        }
                    ]
                }
            }
        }

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.text = AsyncMock(
                return_value='{"status": 1, "result": {"SE123456789GR": {"status": 1, "result": [{"date": "15-02-2026", "time": "14:30", "place": "ΑΘΗΝΑ", "status": "Αποστολή παραδόθηκε"}]}}}'
            )

            result = await courier.track("SE123456789GR")

            assert result.success is True
            assert result.courier == "elta"
            assert result.status == "Delivered"
            assert result.status_category == "delivered"
            assert len(result.events) > 0
            assert result.latest_event is not None

    async def test_elta_not_found(self):
        """Test ELTA with tracking number not found."""
        courier = ELTACourier()

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.text = AsyncMock(
                return_value='{"status": 1, "result": {"SE999999999GR": {"status": 0, "result": "Not Found"}}}'
            )

            result = await courier.track("SE999999999GR")

            assert result.success is True
            assert result.status == "Not Found"
            assert len(result.events) == 0

    async def test_elta_error_response(self):
        """Test ELTA with API error."""
        courier = ELTACourier()

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 500

            result = await courier.track("SE123456789GR")

            assert result.success is False
            assert result.status_category == "error"
            assert "HTTP error" in result.error_message


@pytest.mark.asyncio
class TestACSMockedAPI:
    """Mocked API tests for ACS Courier."""

    async def test_acs_successful_tracking(self):
        """Test ACS with successful tracking response."""
        courier = ACSCourier()

        mock_response = {
            "items": [
                {
                    "isDelivered": True,
                    "statusHistory": [
                        {
                            "controlPointDate": "2026-02-15T14:30:00",
                            "controlPoint": "Athens",
                            "description": "Η αποστολή παραδόθηκε"
                        },
                        {
                            "controlPointDate": "2026-02-14T10:15:00",
                            "controlPoint": "Thessaloniki",
                            "description": "Η αποστολή βρίσκεται σε διάκριση"
                        }
                    ]
                }
            ]
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )

            result = await courier.track("1234567890")

            assert result.success is True
            assert result.courier == "acs"
            assert result.status == "Delivered"
            assert result.status_category == "delivered"
            assert len(result.events) > 0

    async def test_acs_not_found(self):
        """Test ACS with tracking number not found."""
        courier = ACSCourier()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value={"items": []}
            )

            result = await courier.track("1234567890")

            assert result.success is True
            assert result.status == "Not Found"
            assert len(result.events) == 0

    async def test_acs_network_error(self):
        """Test ACS with network error."""
        courier = ACSCourier()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.side_effect = aiohttp.ClientError("Network error")

            result = await courier.track("1234567890")

            assert result.success is False
            assert result.status_category == "error"
            assert "Network error" in result.error_message


@pytest.mark.asyncio
class TestBoxNowMockedAPI:
    """Mocked API tests for Box Now."""

    async def test_boxnow_successful_tracking(self):
        """Test Box Now with successful tracking response."""
        courier = BoxNowCourier()

        mock_response = {
            "data": [
                {
                    "state": "delivered",
                    "events": [
                        {
                            "createTime": "2026-02-15T14:30:00.000Z",
                            "type": "delivered",
                            "locationDisplayName": "Central Athens Locker 1234"
                        },
                        {
                            "createTime": "2026-02-14T10:15:00.000Z",
                            "type": "final-destination",
                            "locationDisplayName": "Central Athens Locker 1234"
                        }
                    ]
                }
            ]
        }

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )

            result = await courier.track("BN12345678")

            assert result.success is True
            assert result.courier == "box_now"
            assert result.status == "Delivered"
            assert result.status_category == "delivered"
            assert len(result.events) > 0

    async def test_boxnow_not_found(self):
        """Test Box Now with tracking number not found."""
        courier = BoxNowCourier()

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(
                return_value={"data": []}
            )

            result = await courier.track("BN12345678")

            assert result.success is True
            assert result.status == "Not Found"
            assert len(result.events) == 0


@pytest.mark.asyncio
class TestSpeedExMockedAPI:
    """Mocked API tests for SpeedEx."""

    async def test_speedex_successful_tracking(self):
        """Test SpeedEx with successful tracking response."""
        courier = SpeedExCourier()

        mock_html = """
        <html>
            <body>
                <div class="timeline-card">
                    <h4 class="card-title">Η ΑΠΟΣΤΟΛΗ ΠΑΡΑΔΟΘΗΚΕ</h4>
                    <span class="font-small-3">Αθήνα, 15/02/2026 στις 14:30</span>
                </div>
                <div class="timeline-card">
                    <h4 class="card-title">ΣΕ ΜΕΤΑΦΟΡΑ</h4>
                    <span class="font-small-3">Θεσσαλονίκη, 14/02/2026 στις 10:15</span>
                </div>
            </body>
        </html>
        """

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.text = AsyncMock(
                return_value=mock_html
            )

            result = await courier.track("SP12345678")

            assert result.success is True
            assert result.courier == "speedex"
            assert len(result.events) > 0


@pytest.mark.asyncio
class TestGenikiMockedAPI:
    """Mocked API tests for Geniki Taxydromiki."""

    async def test_geniki_successful_tracking(self):
        """Test Geniki with successful tracking response."""
        courier = GenikiCourier()

        mock_html = """
        <html>
            <body>
                <div class="tracking-checkpoint">
                    <div class="checkpoint-status">ΠΑΡΑΔΟΣΗ</div>
                    <div class="checkpoint-location">Athens</div>
                    <div class="checkpoint-date">Δευτέρα, 15/02/2026</div>
                    <div class="checkpoint-time">14:30</div>
                </div>
                <div class="tracking-checkpoint">
                    <div class="checkpoint-status">ΜΕΤΑΦΟΡΑ</div>
                    <div class="checkpoint-location">Thessaloniki</div>
                    <div class="checkpoint-date">Τρίτη, 14/02/2026</div>
                    <div class="checkpoint-time">10:15</div>
                </div>
            </body>
        </html>
        """

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.text = AsyncMock(
                return_value=mock_html
            )

            result = await courier.track("GT123456789")

            assert result.success is True
            assert result.courier == "geniki"
            assert len(result.events) > 0


@pytest.mark.asyncio
class TestCourierCenterMockedAPI:
    """Mocked API tests for Courier Center."""

    async def test_courier_center_successful_tracking(self):
        """Test Courier Center with successful tracking response."""
        courier = CourierCenterCourier()

        mock_html = """
        <html>
            <body>
                <div class="tr">
                    <div id="date">15-02-2026</div>
                    <div id="time">14:30</div>
                    <div id="area">Athens</div>
                    <div id="action">DeliveryCompleted</div>
                </div>
                <div class="tr">
                    <div id="date">14-02-2026</div>
                    <div id="time">10:15</div>
                    <div id="area">Thessaloniki</div>
                    <div id="action">InTransit</div>
                </div>
            </body>
        </html>
        """

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.text = AsyncMock(
                return_value=mock_html
            )

            result = await courier.track("CC12345678")

            assert result.success is True
            assert result.courier == "courier_center"
            assert len(result.events) > 0


@pytest.mark.asyncio
class TestStatusTranslations:
    """Tests for status translation across all couriers."""

    async def test_elta_status_translation(self):
        """Test ELTA Greek to English status translation."""
        courier = ELTACourier()

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.text = AsyncMock(
                return_value='{"status": 1, "result": {"SE123456789GR": {"status": 1, "result": [{"date": "15-02-2026", "time": "14:30", "place": "ΑΘΗΝΑ", "status": "Αποστολή παραδόθηκε"}]}}}'
            )

            result = await courier.track("SE123456789GR")

            assert result.latest_event is not None
            assert result.latest_event.status_translated == "Delivered"

    async def test_acs_status_translation(self):
        """Test ACS Greek to English status translation."""
        courier = ACSCourier()

        mock_response = {
            "items": [
                {
                    "isDelivered": False,
                    "statusHistory": [
                        {
                            "controlPointDate": "2026-02-14T10:15:00",
                            "controlPoint": "Athens",
                            "description": "Η αποστολή βρίσκεται σε διάκριση"
                        }
                    ]
                }
            ]
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )

            result = await courier.track("1234567890")

            assert result.latest_event is not None
            assert result.latest_event.status_translated == "In Transit"
