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
    SkroutzCourier,
    SvuumCourier,
)


@pytest.fixture(autouse=True)
def acs_token():
    """ACS first reads a public token from its website; skip that in these tests."""
    with patch.object(ACSCourier, "_get_token", AsyncMock(return_value="test-token")):
        yield


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

    async def test_acs_unknown_number(self):
        """ACS answers unknown numbers with an item without history."""
        courier = ACSCourier()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={
                "count": 1,
                "items": [{
                    "trackingNumber": "1234567890",
                    "notes": "Η αποστολή δεν βρέθηκε",
                    "isDelivered": False,
                    "statusHistory": [],
                }],
            })

            result = await courier.track("1234567890")

            assert result.success is True
            assert result.status == "Not Found"

    async def test_acs_sends_token_headers(self):
        """The API needs the page token, the country and the site origin."""
        courier = ACSCourier()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(return_value={"items": []})

            await courier.track("1234567890")

            headers = mock_get.call_args.kwargs["headers"]
            assert headers["X-Encrypted-Key"] == "test-token"
            assert headers["X-Country"] == "GR"
            assert headers["Origin"] == "https://www.acscourier.net"

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
            assert len(result.events) == 2
            assert result.status_category == "delivered"
            assert result.latest_event.location == "Αθήνα"
            assert (result.latest_event.date, result.latest_event.time) == ("15/02/2026", "14:30")

    async def test_speedex_timeline_page(self):
        """Parse the current speedex.gr timeline (oldest first, date and place on separate lines)."""
        courier = SpeedExCourier()

        def card(title, date_time, place, phone="", maps=""):
            return f"""
            <li class="timeline-item">
                <div class="timeline-card card border-grey border-lighten-2 col-md-8">
                    <div class="card-header">
                        <h4 class="card-title">
                            {title}
                        </h4>
                        <p class="card-subtitle text-muted mb-0 pt-1">
                            <span class="font-small-3">
                                {date_time}
                            </span>
                        </p>
                        <p class="card-subtitle text-muted mb-0 pt-1"><span class="font-small-3">
                            {place}
                        </span></p>
                        <p class="card-subtitle text-muted mb-0 pt-1"><span class="font-small-3">
                            {phone}
                        </span></p>
                        {maps}
                    </div>
                </div>
            </li>"""

        mock_html = f"""
        <html><head><style>.timeline-item:nth-child(even) > .timeline-card {{ float: right; }}</style></head>
        <body><ul class="timeline">
            {card("ΑΝΑΜΟΝΗ ΑΝΑΘΕΣΗΣ ΑΠΟ ΑΠΟΣΤΟΛΕΑ", "19/10/2026\n στις\n 15:34", ", ")}
            {card("ΠΑΡΑΛΑΒΗ ΣΤΟ ΚΑΤΑΣΤΗΜΑ", "20/10/2026\n στις\n 12:56", "ΣΙΔΗΡΟΚΑΣΤΡΟΥ 1-3 , ΒΟΤΑΝΙΚΟΣ, ΑΘΗΝΑ",
                  "210 5200120", "<p class='card-subtitle'><span class='font-small-3'><a href='https://www.google.com/maps?q=37.98,23.70'>View on Google Maps</a></span></p>")}
            {card("ΕΙΣΑΓΩΓΗ ΣΕ Δ/Κ", "20/10/2026\n στις\n 19:38", ", ΚΗΦΙΣΙΑ")}
            {card("ΕΞΑΓΩΓΗ ΑΠΌ Δ/Κ", "21/10/2026\n στις\n 07:07", ", ΚΗΦΙΣΙΑ")}
        </ul></body></html>
        """

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.text = AsyncMock(
                return_value=mock_html
            )

            result = await courier.track("700049628797")

        assert result.success is True
        assert result.status_category == "in_transit"
        assert result.status == "Left the Hub"
        assert [event.status for event in result.events] == [
            "ΕΞΑΓΩΓΗ ΑΠΌ Δ/Κ",
            "ΕΙΣΑΓΩΓΗ ΣΕ Δ/Κ",
            "ΠΑΡΑΛΑΒΗ ΣΤΟ ΚΑΤΑΣΤΗΜΑ",
            "ΑΝΑΜΟΝΗ ΑΝΑΘΕΣΗΣ ΑΠΟ ΑΠΟΣΤΟΛΕΑ",
        ]
        latest = result.latest_event
        assert (latest.date, latest.time, latest.location) == ("21/10/2026", "07:07", "ΚΗΦΙΣΙΑ")
        assert result.events[2].location == "ΣΙΔΗΡΟΚΑΣΤΡΟΥ 1-3, ΒΟΤΑΝΙΚΟΣ, ΑΘΗΝΑ"
        assert result.events[2].status_translated == "Picked Up"
        assert result.events[3].location == ""

    async def test_speedex_delivered_card(self):
        """The last card, "Η ΑΠΟΣΤΟΛΗ ΠΑΡΑΔΟΘΗΚΕ", is styled differently by the website."""
        courier = SpeedExCourier()
        mock_html = """
        <style>.delivered-speedex { background-color: #0074bb !important; }</style>
        <li class="timeline-item"><div class="timeline-card card border-grey border-lighten-2 col-md-8">
            <h4 class="card-title">ΕΞΑΓΩΓΗ ΑΠΌ Δ/Κ</h4>
            <span class="font-small-3">21/10/2026 στις 07:07</span><span class="font-small-3">, ΚΗΦΙΣΙΑ</span>
        </div></li>
        <li class="timeline-item"><div class="timeline-card card delivered-speedex col-md-8">
            <h4 class="card-title delivered-title">
                Η ΑΠΟΣΤΟΛΗ ΠΑΡΑΔΟΘΗΚΕ
            </h4>
            <p class="card-subtitle delivered-subtitle"><span class="font-small-3">22/10/2026
                στις
                    11:40</span></p>
            <p class="card-subtitle delivered-subtitle"><span class="font-small-3">, ΑΘΗΝΑ</span></p>
        </div></li>
        """

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.text = AsyncMock(
                return_value=mock_html
            )

            result = await courier.track("700049628797")

        assert result.status_category == "delivered"
        assert result.status == "Delivered"
        latest = result.latest_event
        assert (latest.status, latest.date, latest.time, latest.location) == (
            "Η ΑΠΟΣΤΟΛΗ ΠΑΡΑΔΟΘΗΚΕ", "22/10/2026", "11:40", "ΑΘΗΝΑ"
        )

    async def test_speedex_css_alone_is_not_delivered(self):
        """Every page has the "delivered-speedex" style rule; only an element with it counts."""
        courier = SpeedExCourier()
        mock_html = """
        <style>.delivered-speedex { background-color: #0074bb !important; }</style>
        <div class="timeline-card"><h4 class="card-title">ΕΙΣΑΓΩΓΗ ΣΕ ΚΑΤΑΣΤΗΜΑ</h4>
        <span class="font-small-3">21/10/2026 στις 09:00</span><span class="font-small-3">, ΑΘΗΝΑ</span></div>
        """

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.text = AsyncMock(
                return_value=mock_html
            )

            result = await courier.track("700049628797")

        assert result.status_category == "in_transit"
        assert result.status == "Arrived at Store"

    async def test_speedex_created_and_not_found(self):
        """A voucher the sender hasn't handed over yet is "created"; unknown numbers are not found."""
        courier = SpeedExCourier()
        created_html = """
        <div class="timeline-card"><h4 class="card-title">ΑΝΑΜΟΝΗ ΑΝΑΘΕΣΗΣ ΑΠΟ ΑΠΟΣΤΟΛΕΑ</h4>
        <span class="font-small-3">19/10/2026 στις 15:34</span><span class="font-small-3">, </span></div>
        """
        not_found_html = '<div class="col-md-4 text-center alert alert-warning mt-3">Δεν βρέθηκαν αποτελέσματα.</div>'

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.text = AsyncMock(
                side_effect=[created_html, not_found_html]
            )

            created = await courier.track("700049628797")
            not_found = await courier.track("700000000001")

        assert created.status_category == "created"
        assert created.status == "Shipment Created"
        assert not_found.status == "Not Found"
        assert not_found.events == []


def _geniki_response(tracking_number, *checkpoints):
    """Build a taxydromiki.com track-site.php response (checkpoints oldest first)."""
    if not checkpoints:
        return {
            "success": True,
            tracking_number: {"TrackAndTraceResult": {"Result": 9, "Checkpoints": {}}},
        }
    return {
        "success": True,
        tracking_number: {
            "TrackAndTraceResult": {
                "Result": 0,
                "Checkpoints": {
                    "Checkpoint": [
                        {"StatusCode": code, "StatusDate": date, "Status": status, "Shop": shop}
                        for code, date, status, shop in checkpoints
                    ]
                },
            }
        },
    }


@pytest.mark.asyncio
class TestGenikiMockedAPI:
    """Mocked API tests for Geniki Taxydromiki."""

    async def test_geniki_delivered(self):
        """Test Geniki with a delivered shipment (Greek and English requests)."""
        courier = GenikiCourier()

        response_el = _geniki_response(
            "1234567890",
            ("C_NW", "2026-02-13T09:00:00", "ΔΗΜΙΟΥΡΓΙΑ ΑΠΟΣΤΟΛΗΣ", "ΑΘΗΝΑ"),
            ("C_W3", "2026-02-14T10:15:00", "ΠΑΡΑΛΑΒΗ ΑΠΟΣΤΟΛΗΣ", "ΑΘΗΝΑ"),
            ("C_W2", "2026-02-15T14:30:00.1234567", "ΠΑΡΑΔΟΣΗ", "ΘΕΣΣΑΛΟΝΙΚΗ"),
        )
        response_en = _geniki_response(
            "1234567890",
            ("C_NW", "2026-02-13T09:00:00", "Shipment created", "ATHENS"),
            ("C_W3", "2026-02-14T10:15:00", "Shipment picked up", "ATHENS"),
            ("C_W2", "2026-02-15T14:30:00.1234567", "Delivered", "THESSALONIKI"),
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(
                side_effect=[response_el, response_en]
            )

            result = await courier.track("1234567890")

            assert mock_post.call_count == 2
            assert result.success is True
            assert result.courier == "geniki"
            assert result.status == "Delivered"
            assert result.status_category == "delivered"
            assert len(result.events) == 3
            # Newest event first
            assert result.latest_event.status == "ΠΑΡΑΔΟΣΗ"
            assert result.latest_event.location == "ΘΕΣΣΑΛΟΝΙΚΗ"
            assert result.latest_event.date == "2026-02-15"
            assert result.latest_event.time == "14:30"
            assert result.events[-1].status_translated == "Shipment created"

    async def test_geniki_cancelled_pair_hidden(self):
        """Test that an event cancelled by a later one is hidden, as on the website."""
        courier = GenikiCourier()

        response = _geniki_response(
            "1234567890",
            ("C_NW", "2026-02-13T09:00:00", "ΔΗΜΙΟΥΡΓΙΑ ΑΠΟΣΤΟΛΗΣ", "ΑΘΗΝΑ"),
            ("C_K8", "2026-02-14T10:00:00", "ΠΑΡΑΛΑΒΗ ΑΠΟ ΚΑΤΑΣΤΗΜΑ", "ΑΘΗΝΑ"),
            ("C_K9", "2026-02-14T10:05:00", "ΑΚΥΡΩΣΗ ΠΑΡΑΛΑΒΗΣ", "ΑΘΗΝΑ"),
            ("C_A1", "2026-02-14T12:00:00", "ΑΦΙΞΗ ΣΤΟ ΚΕΝΤΡΟ ΔΙΑΛΟΓΗΣ", "ΑΣΠΡΟΠΥΡΓΟΣ"),
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(
                side_effect=[response, response]
            )

            result = await courier.track("1234567890")

            assert [event.status for event in result.events] == [
                "ΑΦΙΞΗ ΣΤΟ ΚΕΝΤΡΟ ΔΙΑΛΟΓΗΣ",
                "ΔΗΜΙΟΥΡΓΙΑ ΑΠΟΣΤΟΛΗΣ",
            ]
            assert result.status_category == "in_transit"

    async def test_geniki_created(self):
        """Test Geniki with a voucher that was only created."""
        courier = GenikiCourier()

        response = _geniki_response(
            "1234567890",
            ("C_NW", "2026-02-13T09:00:00", "ΔΗΜΙΟΥΡΓΙΑ ΑΠΟΣΤΟΛΗΣ", "ΑΘΗΝΑ"),
        )
        # A single checkpoint may come back as an object instead of a list
        checkpoints = response["1234567890"]["TrackAndTraceResult"]["Checkpoints"]
        checkpoints["Checkpoint"] = checkpoints["Checkpoint"][0]

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(
                side_effect=[response, response]
            )

            result = await courier.track("1234567890")

            assert len(result.events) == 1
            assert result.status_category == "created"

    async def test_geniki_english_unavailable(self):
        """Test that Greek statuses are translated locally if the English request fails."""
        courier = GenikiCourier()

        response_el = _geniki_response(
            "1234567890",
            ("C_W2", "2026-02-15T14:30:00", "ΠΑΡΑΔΟΣΗ", "ΘΕΣΣΑΛΟΝΙΚΗ"),
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(
                side_effect=[response_el, aiohttp.ClientError("Network error")]
            )

            result = await courier.track("1234567890")

            assert result.success is True
            assert result.status == "Delivered"
            assert result.latest_event.status_translated == "Delivered"

    async def test_geniki_not_found(self):
        """Test Geniki with an unknown tracking number (empty checkpoints)."""
        courier = GenikiCourier()

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=_geniki_response("1234567890")
            )

            result = await courier.track("1234567890")

            # No English request for unknown numbers
            assert mock_post.call_count == 1
            assert result.success is True
            assert result.status == "Not Found"
            assert len(result.events) == 0

    async def test_geniki_server_error(self):
        """Test Geniki with a server error."""
        courier = GenikiCourier()

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 500

            result = await courier.track("1234567890")

            assert result.success is False
            assert result.status_category == "error"
            assert "HTTP error" in result.error_message


COURIER_CENTER_WAYBILL_HTML = """
<html><body>
  <div class="info">
    <div class="id"><strong>Αριθμός Φορτωτικής:</strong> <span>013700000001</span></div>
    <div class="status"><strong>Κατάσταση:</strong> <span>(30) DeliveryCompleted</span></div>
  </div>
  <div class="track-table">
    <div class="tr header"><div class="td date">Ημερομηνία</div><div class="td action">Ενέργεια</div></div>
    <div class="tr">
      <div class="td date">14/2/2026</div><div class="td date-skip skip"></div>
      <div class="td time">10:15</div><div class="td action">Η αποστολή παρελήφθη</div>
      <div class="td adapter"></div><div class="td area">ΑΘΗΝΑ</div>
    </div>
    <div class="tr">
      <div class="td date">15/2/2026</div><div class="td date-skip skip"></div>
      <div class="td time">14:30</div><div class="td action">Η αποστολή παραδόθηκε</div>
      <div class="td adapter"></div><div class="td area">ΘΕΣΣΑΛΟΝΙΚΗ</div>
    </div>
  </div>
</body></html>
"""


def _courier_center_list_html(*rows):
    """A receipt number that matches several waybills."""
    cells = "".join(
        f'<div class="tr"><div class="td">REF</div><div class="td">{waybill}</div>'
        f'<div class="td">(15) NewShipment</div><div class="td date">{sent}</div>'
        f'<div class="td date">{sent}</div><div class="td"></div></div>'
        for waybill, sent in rows
    )
    return (
        '<div class="table"><div class="tr header"><div class="th">Αριθμός Αποδεικτικού</div>'
        '<div class="th">Αριθμός Φορτωτικής</div><div class="th">Κατάσταση</div>'
        f'<div class="th">Αποστολή</div><div class="th">Παράδοση</div></div>{cells}</div>'
    )


@pytest.mark.asyncio
class TestCourierCenterMockedAPI:
    """Mocked API tests for Courier Center."""

    async def test_courier_center_successful_tracking(self):
        """A waybill page with status and history."""
        courier = CourierCenterCourier()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.text = AsyncMock(
                return_value=COURIER_CENTER_WAYBILL_HTML
            )

            result = await courier.track("013700000001")

            assert result.success is True
            assert result.courier == "courier_center"
            assert result.status == "Delivered"
            assert result.status_category == "delivered"
            assert len(result.events) == 2
            # Newest first
            assert result.latest_event.status == "Η αποστολή παραδόθηκε"
            assert result.latest_event.location == "ΘΕΣΣΑΛΟΝΙΚΗ"
            assert result.latest_event.time == "14:30"
            assert result.status_el == "Η αποστολή παραδόθηκε"

    async def test_courier_center_unknown_number(self):
        """Unknown numbers show an error heading."""
        courier = CourierCenterCourier()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.text = AsyncMock(
                return_value='<h4 class="error">Υπήρξε πρόβλημα με την αναζήτηση</h4>'
            )

            result = await courier.track("ZZ99999999")

            assert result.success is True
            assert result.status == "Not Found"

    async def test_courier_center_receipt_number_follows_latest_waybill(self):
        """A receipt number lists waybills; the newest one is tracked."""
        from datetime import datetime, timedelta

        courier = CourierCenterCourier()
        recent = (datetime.now() - timedelta(days=2)).strftime("%d/%m/%Y")
        older = (datetime.now() - timedelta(days=9)).strftime("%d/%m/%Y")

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.text = AsyncMock(side_effect=[
                _courier_center_list_html(("013700000002", older), ("013700000001", recent)),
                COURIER_CENTER_WAYBILL_HTML,
            ])

            result = await courier.track("1234567890")

            assert mock_get.call_args.kwargs["params"] == {"tracknr": "013700000001"}
            assert result.tracking_number == "1234567890"
            assert result.status_category == "delivered"

    async def test_courier_center_old_receipt_number_is_not_found(self):
        """Old waybills of a receipt number belong to past orders."""
        courier = CourierCenterCourier()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.text = AsyncMock(
                return_value=_courier_center_list_html(("013700000001", "28/4/2025"))
            )

            result = await courier.track("1234567890")

            assert result.status == "Not Found"
            assert mock_get.call_count == 1


@pytest.mark.asyncio
class TestSkroutzMockedAPI:
    """Mocked API tests for Skroutz Last Mile."""

    async def test_skroutz_in_transit(self):
        """Test Skroutz Last Mile with a picked up shipment."""
        courier = SkroutzCourier()

        mock_response = {
            "status": "picked_up",
            "pickedUpAt": "2026-02-14T10:36:52.928Z",
            "deliveredAt": None,
            "trackingDetails": [
                {
                    "description": "Shipment was picked up",
                    "notes": "",
                    "createdAt": "2026-02-14T10:36:52.932Z",
                    "description_gr": "Παραλάβαμε το δέμα από το κατάστημα",
                    "description_en": "We have picked up the shipment from the sender",
                    "trackingState": "PICKED_UP",
                },
                {
                    "description": "Scanned",
                    "notes": "SLM HUB Αιγάλεω",
                    "createdAt": "2026-02-14T16:52:19.642Z",
                    "description_gr": "Η αποστολή βρίσκεται στο SLM HUB Αιγάλεω",
                    "description_en": "The shipment is at SLM HUB Αιγάλεω",
                    "trackingState": "SCANNED",
                },
            ],
            "statusTextGr": "Η αποστολή βρίσκεται στο κέντρο διαλογής της Skroutz Last Mile",
            "statusTextEn": "The shipment is at the Skroutz Last Mile sorting centre",
            "eta": {"startTime": "2026-02-16T10:00:00.000Z", "endTime": "2026-02-16T14:00:00.000Z"},
            "deliveryPromiseTo": "2026-02-17",
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )

            result = await courier.track("ab12cd34ef56g")

            assert result.success is True
            assert result.courier == "skroutz"
            assert result.tracking_number == "AB12CD34EF56G"
            assert result.status == "The shipment is at the Skroutz Last Mile sorting centre"
            assert result.status_category == "in_transit"
            assert len(result.events) == 2
            # Newest event first, converted to Athens local time (UTC+2 in February)
            assert result.latest_event.location == "SLM HUB Αιγάλεω"
            assert result.latest_event.status == "Η αποστολή βρίσκεται στο SLM HUB Αιγάλεω"
            assert result.latest_event.status_translated == "The shipment is at SLM HUB Αιγάλεω"
            assert result.latest_event.date == "2026-02-14"
            assert result.latest_event.time == "18:52"
            assert result.status_el == "Η αποστολή βρίσκεται στο κέντρο διαλογής της Skroutz Last Mile"
            # Delivery window start in Athens time
            assert result.estimated_delivery == "2026-02-16T12:00+02:00"

    async def test_skroutz_delivered(self):
        """Test Skroutz Last Mile with a delivered shipment."""
        courier = SkroutzCourier()

        mock_response = {
            "status": "delivered",
            "pickedUpAt": "2026-02-14T10:36:52.928Z",
            "deliveredAt": "2026-02-15T12:00:00.000Z",
            "trackingDetails": [
                {
                    "createdAt": "2026-02-15T12:00:00.000Z",
                    "description_gr": "Η αποστολή παραδόθηκε",
                    "description_en": "The shipment was delivered",
                },
            ],
            "statusTextEn": "Delivered",
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )

            result = await courier.track("AB12CD34EF56G")

            assert result.success is True
            assert result.status_category == "delivered"

    async def test_skroutz_created(self):
        """Test Skroutz Last Mile with a shipment not picked up yet."""
        courier = SkroutzCourier()

        mock_response = {
            "status": "created",
            "pickedUpAt": None,
            "deliveredAt": None,
            "trackingDetails": [],
            "statusTextEn": "The shipment has been created",
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )

            result = await courier.track("AB12CD34EF56G")

            assert result.success is True
            assert result.status == "The shipment has been created"
            assert result.status_category == "created"

    async def test_skroutz_not_found(self):
        """Test Skroutz Last Mile with an unknown tracking number (HTTP 400)."""
        courier = SkroutzCourier()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 400

            result = await courier.track("AB12CD34EF56G")

            assert result.success is True
            assert result.status == "Not Found"
            assert len(result.events) == 0

    async def test_skroutz_server_error(self):
        """Test Skroutz Last Mile with a server error."""
        courier = SkroutzCourier()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 500

            result = await courier.track("AB12CD34EF56G")

            assert result.success is False
            assert result.status_category == "error"
            assert "HTTP error" in result.error_message


@pytest.mark.asyncio
class TestSvuumMockedAPI:
    """Mocked API tests for Svuum."""

    @staticmethod
    def _response(*timeline):
        return [
            {
                "referenceNumber": "1234567",
                "processTimeLineLogsList": list(timeline),
                "processMasterId": 5630,
                "proceMasterCode": "Website Tracking",
            }
        ]

    async def test_svuum_in_transit(self):
        """Test Svuum with a shipment at the central warehouse."""
        courier = SvuumCourier()

        mock_response = self._response(
            {
                "status": "Επιτυχής Παραλαβή Στην Κεντρική Αποθήκη Tης Svuum",
                "statusTime": "Feb-14-2026 05:40 PM",
                "statusCode": "S210",
            },
            {
                "status": "Η Παραγγελία Βρίσκεται Aκόμα Στο Eshop",
                "statusTime": "Feb-14-2026 03:57 PM",
                "statusCode": "S010",
            },
        )

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )

            result = await courier.track("1234567")

            assert result.success is True
            assert result.courier == "svuum"
            assert result.status == "Received at Svuum Central Warehouse"
            assert result.status_category == "in_transit"
            assert len(result.events) == 2
            assert result.latest_event.date == "2026-02-14"
            assert result.latest_event.time == "17:40"
            assert result.events[1].status_translated == "Order Still at the E-shop"

    async def test_svuum_created(self):
        """Test Svuum with an order still at the e-shop."""
        courier = SvuumCourier()

        mock_response = self._response(
            {
                "status": "Η Παραγγελία Βρίσκεται Aκόμα Στο Eshop",
                "statusTime": "Feb-14-2026 12:05 AM",
                "statusCode": "S010",
            },
        )

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )

            result = await courier.track("1234567")

            assert result.status_category == "created"
            assert result.latest_event.time == "00:05"

    async def test_svuum_delivered(self):
        """Test Svuum with a delivered shipment."""
        courier = SvuumCourier()

        mock_response = self._response(
            {"status": "Επιτυχής Παράδοση", "statusTime": "Feb-15-2026 11:00 AM", "statusCode": "S999"},
        )

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )

            result = await courier.track("1234567")

            assert result.status == "Επιτυχής Παράδοση"
            assert result.status_category == "delivered"

    async def test_svuum_failed_delivery_not_delivered(self):
        """Test that a failed delivery attempt is not reported as delivered."""
        courier = SvuumCourier()

        mock_response = self._response(
            {"status": "Ανεπιτυχής Παράδοση", "statusTime": "Feb-15-2026 11:00 AM", "statusCode": "S998"},
        )

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )

            result = await courier.track("1234567")

            assert result.status_category == "in_transit"

    async def test_svuum_not_found(self):
        """Test Svuum with an unknown tracking number (empty list)."""
        courier = SvuumCourier()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=[]
            )

            result = await courier.track("1234567")

            assert result.success is True
            assert result.status == "Not Found"
            assert len(result.events) == 0

    async def test_svuum_server_error(self):
        """Test Svuum with a server error."""
        courier = SvuumCourier()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 500

            result = await courier.track("1234567")

            assert result.success is False
            assert result.status_category == "error"
            assert "HTTP error" in result.error_message


@pytest.mark.asyncio
class TestAutoDetect:
    """Tests for auto-detection across couriers."""

    async def test_auto_detect_skips_empty_unknown_results(self):
        """An empty "Unknown" result must not stop auto-detection."""
        from custom_components.greek_courier_tracker.couriers import (
            COURIER_REGISTRY,
            GenikiCourier,
            track_with_auto_detect,
        )
        from custom_components.greek_courier_tracker.couriers.base import (
            TrackingEvent,
            TrackingResult,
        )

        empty_result = TrackingResult(
            success=True,
            tracking_number="1234567",
            courier="geniki",
            courier_name="Geniki Taxydromiki",
            status="Unknown",
            status_category="unknown",
            events=[],
        )
        event = TrackingEvent(date="2026-02-14", time="17:40", location="", status="In transit")
        real_result = TrackingResult(
            success=True,
            tracking_number="1234567",
            courier="svuum",
            courier_name="Svuum",
            status="In transit",
            status_category="in_transit",
            events=[event],
            latest_event=event,
        )

        with patch.dict(
            COURIER_REGISTRY, {"geniki": GenikiCourier, "svuum": SvuumCourier}, clear=True
        ), patch.object(
            GenikiCourier, "track", AsyncMock(return_value=empty_result)
        ), patch.object(
            SvuumCourier, "track", AsyncMock(return_value=real_result)
        ), patch("asyncio.sleep", AsyncMock()):
            result = await track_with_auto_detect("1234567")

        assert result.courier == "svuum"
        assert result.status == "In transit"


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
