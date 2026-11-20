"""Tests for updates that only change the place, and shipments that don't move."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from custom_components.greek_courier_tracker import GreekCourierDataUpdateCoordinator
from custom_components.greek_courier_tracker.couriers.base import TrackingEvent, TrackingResult
from custom_components.greek_courier_tracker.tracking import ATHENS, last_movement, no_movement_text

PACKAGE = "custom_components.greek_courier_tracker"
NOW = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
UPDATED = "greek_courier_tracker_shipment_updated"
STATUS = "greek_courier_tracker_status_changed"
NO_MOVEMENT = "greek_courier_tracker_no_movement"


def _result(*events, category="in_transit", stage="in_transit", problem=None, status="In Transit"):
    items = [
        TrackingEvent(date=date, time=time, location=place, status=text) for date, time, place, text in events
    ]
    return TrackingResult(
        success=True, tracking_number="A", courier="elta", courier_name="ELTA Courier", status=status,
        status_category=category, events=items, latest_event=items[0] if items else None,
        stage=stage, problem=problem,
    )


def _coordinator(no_movement_days=0):
    entry = MagicMock(entry_id="e1", data={}, options={"no_movement_days": no_movement_days})
    configs = {"A": {"tracking_number": "A", "name": "Shoes", "courier": "elta", "stop_tracking_delivered": False}}
    hass = MagicMock()
    hass.config.language = "el"
    with patch(f"{PACKAGE}.Store"):
        coordinator = GreekCourierDataUpdateCoordinator(
            hass=hass, tracking_numbers=["A"], tracking_configs=configs, scan_interval=15, entry=entry,
        )
    coordinator._entity_id = lambda number: None
    return coordinator


def _fired(coordinator):
    return [(call.args[0], call.args[1]) for call in coordinator.hass.bus.async_fire.call_args_list]


class TestLastMovement:
    @pytest.mark.parametrize(
        ("date", "time", "expected"),
        [
            ("2026-11-19", "10:30", datetime(2026, 11, 19, 10, 30, tzinfo=ATHENS)),
            ("19-11-2026", "07:05", datetime(2026, 11, 19, 7, 5, tzinfo=ATHENS)),
            ("9/11/2026", "", datetime(2026, 11, 9, tzinfo=ATHENS)),
            ("tomorrow", "10:00", None),
        ],
    )
    def test_formats(self, date, time, expected):
        assert last_movement(_result((date, time, "ΑΘΗΝΑ", "x"))) == expected

    def test_no_events(self):
        assert last_movement(_result()) is None

    def test_text(self):
        assert no_movement_text(3, "el") == "Καμία κίνηση εδώ και 3 ημέρες"
        assert no_movement_text(1, "en") == "No movement for 1 day"


class TestShipmentUpdated:
    def test_same_text_in_another_place(self):
        """Every new scan is an update; only a new text is a status change."""
        coordinator = _coordinator()
        old = _result(("2026-11-17", "10:00", "ΚΔ ΑΘΗΝΑΣ", "Άφιξη σε"))
        new = _result(("2026-11-19", "08:00", "ΚΔ ΘΕΣΣΑΛΟΝΙΚΗΣ", "Άφιξη σε"), ("2026-11-17", "10:00", "ΚΔ ΑΘΗΝΑΣ", "Άφιξη σε"))

        coordinator._fire_status_events({"A": old}, {"A": new})

        [(event_type, data)] = _fired(coordinator)
        assert event_type == UPDATED
        assert data["status_changed"] is False
        assert data["stage_changed"] is False
        assert data["location"] == "ΚΔ ΘΕΣΣΑΛΟΝΙΚΗΣ"

    def test_new_stage(self):
        coordinator = _coordinator()
        old = _result(("2026-11-17", "10:00", "ΑΘΗΝΑ", "Άφιξη σε"))
        new = _result(
            ("2026-11-19", "08:00", "ΑΘΗΝΑ", "Σε διανομέα προς παράδοση"), stage="out_for_delivery",
        )

        coordinator._fire_status_events({"A": old}, {"A": new})

        (updated_type, updated), (status_type, _) = _fired(coordinator)
        assert (updated_type, status_type) == (UPDATED, STATUS)
        assert updated["status_changed"] is True
        assert updated["stage_changed"] is True
        assert updated["old_stage"] == "in_transit"

    def test_nothing_new(self):
        coordinator = _coordinator()
        result = _result(("2026-11-17", "10:00", "ΑΘΗΝΑ", "Άφιξη σε"))

        coordinator._fire_status_events({"A": result}, {"A": _result(("2026-11-17", "10:00", "ΑΘΗΝΑ", "Άφιξη σε"))})

        assert _fired(coordinator) == []


class TestNoMovement:
    @staticmethod
    def _check(coordinator, result):
        with patch(f"{PACKAGE}.dt_util.now", return_value=NOW):
            coordinator._notice_no_movement({"A": result})
        return [data for event_type, data in _fired(coordinator) if event_type == NO_MOVEMENT]

    def test_notice_once_per_latest_event(self):
        coordinator = _coordinator(no_movement_days=3)
        stuck = _result(("2026-11-16", "09:00", "ΚΔ ΑΘΗΝΑΣ", "Άφιξη σε"))

        [notice] = self._check(coordinator, stuck)
        assert notice["days"] == 4
        assert notice["text"] == "Καμία κίνηση εδώ και 4 ημέρες"
        assert notice["name"] == "Shoes"
        assert notice["last_movement"] == "2026-11-16T09:00:00+02:00"

        # Not again for the same update
        assert len(self._check(coordinator, stuck)) == 1
        # A new update that is again old enough gets its own notice
        moved = _result(("2026-11-16", "18:00", "ΚΔ ΘΕΣΣΑΛΟΝΙΚΗΣ", "Άφιξη σε"))
        assert len(self._check(coordinator, moved)) == 2

    @pytest.mark.parametrize(
        ("days", "result"),
        [
            # Off (the default)
            (0, _result(("2026-11-01", "09:00", "ΑΘΗΝΑ", "Άφιξη σε"))),
            # Recent enough
            (3, _result(("2026-11-18", "09:00", "ΑΘΗΝΑ", "Άφιξη σε"))),
            # Done moving
            (3, _result(("2026-11-01", "09:00", "ΑΘΗΝΑ", "Παραδόθηκε"), category="delivered", stage="delivered")),
            (3, _result(("2026-11-01", "09:00", "ΑΘΗΝΑ", "Ακυρώθηκε"), problem="cancelled")),
            # The date can't be read
            (3, _result(("someday", "09:00", "ΑΘΗΝΑ", "Άφιξη σε"))),
        ],
    )
    def test_no_notice(self, days, result):
        assert self._check(_coordinator(no_movement_days=days), result) == []

    def test_sensor_knows_it_is_stalled(self):
        coordinator = _coordinator(no_movement_days=3)
        coordinator.data = {"A": _result(("2026-11-16", "09:00", "ΑΘΗΝΑ", "Άφιξη σε"))}

        assert coordinator.stalled_since("A", NOW) == datetime(2026, 11, 16, 9, 0, tzinfo=ATHENS)
        coordinator.entry.options["no_movement_days"] = 5
        assert coordinator.stalled_since("A", NOW) is None

    def test_removed_shipments_are_forgotten(self):
        coordinator = _coordinator(no_movement_days=3)
        coordinator._no_movement_sent = {"GONE": "x"}

        self._check(coordinator, _result(("2026-11-19", "09:00", "ΑΘΗΝΑ", "Άφιξη σε")))

        assert "GONE" not in coordinator._no_movement_sent
