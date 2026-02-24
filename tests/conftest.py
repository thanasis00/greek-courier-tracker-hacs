"""Test configuration for Greek Courier Tracker."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
from datetime import datetime


@pytest.fixture
def mock_aiohttp_response():
    """Create a mock aiohttp response."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "application/json"}
    return mock_response


@pytest.fixture
def mock_session():
    """Create a mock aiohttp ClientSession."""
    session = AsyncMock()
    session.get = AsyncMock()
    session.post = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock()
    return session


@pytest.fixture
def elta_success_response():
    """Mock ELTA API success response."""
    return {
        "status": 1,
        "result": {
            "XX123456789GR": {
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


@pytest.fixture
def elta_not_found_response():
    """Mock ELTA API not found response."""
    return {
        "status": 1,
        "result": {
            "XX999999999GR": {
                "status": 0,
                "result": "Not Found"
            }
        }
    }


@pytest.fixture
def acs_success_response():
    """Mock ACS API success response."""
    return {
        "data": {
            "items": [
                {
                    "date": "15-02-2026",
                    "time": "14:30",
                    "location": "Athens",
                    "status": "Η αποστολή παραδόθηκε",
                    "comments": "Delivered to front desk"
                },
                {
                    "date": "14-02-2026",
                    "time": "10:15",
                    "location": "Thessaloniki",
                    "status": "Η αποστολή βρίσκεται σε διάκριση",
                    "comments": "In transit"
                }
            ]
        }
    }


@pytest.fixture
def boxnow_success_response():
    """Mock Box Now API success response."""
    return {
        "parcelId": "BN12345678",
        "status": "delivered",
        "events": [
            {
                "eventType": "delivered",
                "timestamp": "2026-02-15T14:30:00Z",
                "lockerId": "1234",
                "lockerName": "Central Athens"
            },
            {
                "eventType": "final-destination",
                "timestamp": "2026-02-14T10:15:00Z",
                "lockerId": "1234",
                "lockerName": "Central Athens"
            }
        ]
    }


@pytest.fixture
def speedex_mock_html():
    """Mock SpeedEx HTML response."""
    return """
    <html>
        <body>
            <table class="trackTable">
                <tr>
                    <td>15-02-2026</td>
                    <td>14:30</td>
                    <td>ΑΘΗΝΑ</td>
                    <td>Η ΑΠΟΣΤΟΛΗ ΠΑΡΑΔΟΘΗΚΕ</td>
                </tr>
                <tr>
                    <td>14-02-2026</td>
                    <td>10:15</td>
                    <td>ΘΕΣΣΑΛΟΝΙΚΗ</td>
                    <td>ΣΕ ΜΕΤΑΦΟΡΑ</td>
                </tr>
            </table>
        </body>
    </html>
    """


@pytest.fixture
def geniki_mock_html():
    """Mock Geniki Taxydromiki HTML response."""
    return """
    <html>
        <body>
            <div class="tracking-history">
                <div class="tracking-item">
                    <span class="date">15/02/2026</span>
                    <span class="time">14:30</span>
                    <span class="location">Athens</span>
                    <span class="status">ΠΑΡΑΔΟΣΗ</span>
                </div>
                <div class="tracking-item">
                    <span class="date">14/02/2026</span>
                    <span class="time">10:15</span>
                    <span class="location">Thessaloniki</span>
                    <span class="status">ΜΕΤΑΦΟΡΑ</span>
                </div>
            </div>
        </body>
    </html>
    """
