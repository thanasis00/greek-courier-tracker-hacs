"""Tests for the stages and problems of a shipment (progress bar and notes)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.greek_courier_tracker import GreekCourierDataUpdateCoordinator
from custom_components.greek_courier_tracker.couriers import (
    ACSCourier,
    BoxNowCourier,
    CourierCenterCourier,
    ELTACourier,
    GenikiCourier,
    SkroutzCourier,
    SpeedExCourier,
    SvuumCourier,
)
from custom_components.greek_courier_tracker.couriers.base import (
    TrackingEvent,
    TrackingResult,
    summarize_progress,
)

PACKAGE = "custom_components.greek_courier_tracker"


def _event(stage=None, problem=None, status="x"):
    return TrackingEvent(date="", time="", location="", status=status, stage=stage, problem=problem)


class TestSummarizeProgress:
    """How the events of a shipment (newest first) become a stage and a problem."""

    def test_stage_is_the_furthest_reached(self):
        events = [_event("in_transit"), _event("out_for_delivery"), _event("created")]
        assert summarize_progress(events) == ("out_for_delivery", None)

    def test_problem_of_the_latest_event(self):
        events = [_event("out_for_delivery", "attempt_failed"), _event("out_for_delivery"), _event("in_transit")]
        assert summarize_progress(events) == ("out_for_delivery", "attempt_failed")

    def test_newer_progress_clears_a_problem(self):
        events = [_event("ready_for_pickup"), _event("out_for_delivery", "attempt_failed")]
        assert summarize_progress(events) == ("ready_for_pickup", None)

    def test_unknown_events_keep_a_problem(self):
        events = [_event(), _event("out_for_delivery", "attempt_failed")]
        assert summarize_progress(events) == ("out_for_delivery", "attempt_failed")

    def test_delivery_clears_a_problem(self):
        events = [_event("delivered"), _event(None, "rerouted")]
        assert summarize_progress(events) == ("delivered", None)

    def test_a_return_is_not_cleared_by_later_events(self):
        events = [_event("in_transit"), _event(None, "returning"), _event("out_for_delivery")]
        assert summarize_progress(events) == ("out_for_delivery", "returning")

    def test_delivered_after_a_return_is_back_at_the_sender(self):
        events = [_event("delivered"), _event("in_transit"), _event(None, "returning"), _event("in_transit")]
        assert summarize_progress(events) == ("in_transit", "returned")

    @pytest.mark.parametrize(
        ("count", "fallback", "expected"),
        [(1, None, "created"), (2, None, "in_transit"), (1, "in_transit", "in_transit")],
    )
    def test_unknown_events_fall_back(self, count, fallback, expected):
        assert summarize_progress([_event()] * count, fallback) == (expected, None)

    def test_no_events(self):
        assert summarize_progress([]) == (None, None)


class TestClassify:
    """Common phrases, matched without Greek accents."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Η ΑΠΟΣΤΟΛΗ ΔΕΝ ΠΑΡΑΔΟΘΗΚΕ", ("out_for_delivery", "attempt_failed")),
            ("Ανεπιτυχής Παράδοση", ("out_for_delivery", "attempt_failed")),
            ("Επιτυχής Παράδοση", ("delivered", None)),
            ("Απουσία παραλήπτη", ("out_for_delivery", "attempt_failed")),
            ("Επαναδρομολόγηση παράδοσης", (None, "rerouted")),
            ("Νέα ημερομηνία παράδοσης", (None, "rerouted")),
            ("Ελλιπής διεύθυνση", (None, "held")),
            ("Επιστροφή στον αποστολέα", (None, "returning")),
            ("Η αποστολή επιστράφηκε στον αποστολέα", (None, "returned")),
            ("Σε διανομή", ("out_for_delivery", None)),
            ("Διαθέσιμο για παραλαβή", ("ready_for_pickup", None)),
            ("Delivery failed", ("out_for_delivery", "attempt_failed")),
            ("Out for delivery", ("out_for_delivery", None)),
            ("Κάτι άγνωστο", (None, None)),
        ],
    )
    def test_common_phrases(self, text, expected):
        assert SvuumCourier().classify(text) == expected


class TestELTA:
    @staticmethod
    def _track(*statuses):
        events = [{"date": "09-11-2026", "time": "10:00", "place": "ΑΘΗΝΑ", "status": s} for s in statuses]
        data = {"status": 1, "result": {"PW268817420GR": {"status": 1, "result": events}}}
        return ELTACourier()._parse_response("PW268817420GR", data)

    def test_failed_attempt(self):
        result = self._track(
            "Απουσία παραλήπτη - Επικοινωνία με το κατάστημα",
            "Σε διανομέα προς παράδοση",
            "Αποστολή βρίσκεται σε στάδιο μεταφοράς",
        )
        assert (result.stage, result.problem, result.status_category) == (
            "out_for_delivery", "attempt_failed", "in_transit",
        )
        assert result.events[0].problem == "attempt_failed"

    def test_ready_at_the_store_after_a_failed_attempt(self):
        result = self._track(
            "Αποστολή βρίσκεται στο κατάστημα-Δυνατότητα παραλαβής",
            "Απουσία παραλήπτη - Επικοινωνία με το κατάστημα",
            "Σε διανομέα προς παράδοση",
        )
        assert (result.stage, result.problem) == ("ready_for_pickup", None)

    def test_stages(self):
        assert self._track("Δημιουργία ΣΥ.ΔΕ.ΤΑ.").stage == "created"
        assert self._track("Παραλαβή από αποστολέα", "Δημιουργία ΣΥ.ΔΕ.ΤΑ.").stage == "in_transit"
        assert self._track("Αποστολή παραδόθηκε", "Σε διανομέα προς παράδοση").stage == "delivered"


class TestBoxNow:
    @staticmethod
    def _parse(state, *types):
        events = [
            {"type": event_type, "createTime": f"2026-11-1{index}T10:00:00Z", "locationDisplayName": "Locker"}
            for index, event_type in enumerate(types)
        ]
        return BoxNowCourier()._parse_response("1234567890", {"data": [{"state": state, "events": events}]})

    @pytest.mark.parametrize(
        ("state", "stage", "problem", "status"),
        [
            ("new", "created", None, "New Order"),
            ("wait-for-load", "in_transit", None, "Awaiting Courier Collection"),
            ("in-final-destination", "ready_for_pickup", None, "At Destination Locker"),
            ("delivered", "delivered", None, "Delivered"),
            ("expired-return", "created", "expired", "Expired"),
            ("cancelled", "created", "cancelled", "Cancelled"),
            ("cancelled-return", "created", "cancelled", "Cancelled"),
            ("returned", "created", "returned", "Returned"),
        ],
    )
    def test_states(self, state, stage, problem, status):
        result = self._parse(state)
        assert (result.stage, result.problem, result.status) == (stage, problem, status)

    def test_expired_at_the_locker(self):
        result = self._parse("expired-return", "new", "in-depot", "in-final-destination", "expired-return")
        assert (result.stage, result.problem, result.status_category) == ("ready_for_pickup", "expired", "in_transit")


class TestGeniki:
    @staticmethod
    def _parse(*checkpoints):
        items = [
            {"StatusCode": code, "StatusDate": f"2026-11-1{index}T10:00:00", "Status": status, "Shop": "ΑΘΗΝΑ"}
            for index, (code, status) in enumerate(checkpoints)
        ]
        return GenikiCourier()._parse_checkpoints("1234567890", items, [], {})

    def test_error_code_is_a_problem(self):
        result = self._parse(("C_NW", "ΔΗΜΙΟΥΡΓΙΑ"), ("C_W3", "ΠΑΡΑΛΑΒΗ"), ("C_EA_AG", "ΚΑΤΙ ΑΓΝΩΣΤΟ"))
        assert (result.stage, result.problem) == ("in_transit", "attempt_failed")

    def test_error_text_tells_the_problem(self):
        result = self._parse(("C_W3", "ΠΑΡΑΛΑΒΗ"), ("C_EA_DA", "ΕΛΛΙΠΗΣ ΔΙΕΥΘΥΝΣΗ"))
        assert result.problem == "held"

    def test_delivery_after_a_problem(self):
        result = self._parse(("C_W3", "ΠΑΡΑΛΑΒΗ"), ("C_EA_AG", "ΑΠΩΝ ΠΑΡΑΛΗΠΤΗΣ"), ("C_W2", "ΠΑΡΑΔΟΣΗ"))
        assert (result.stage, result.problem, result.status_category) == ("delivered", None, "delivered")

    def test_out_for_delivery_from_the_text(self):
        result = self._parse(("C_W3", "ΠΑΡΑΛΑΒΗ"), ("C_S1", "ΣΕ ΔΙΑΝΟΜΗ"))
        assert result.stage == "out_for_delivery"


class TestCourierCenter:
    @staticmethod
    def _parse(code, *actions):
        rows = "".join(
            f'<div class="tr"><div class="td date">1{index}/11/2026</div><div class="td time">10:00</div>'
            f'<div class="td action">{action}</div><div class="td area">ΑΘΗΝΑ</div></div>'
            for index, action in enumerate(actions)
        )
        html = (
            f'<div class="status"><span>(1) {code}</span></div>'
            f'<div class="track-table"><div class="tr header"></div>{rows}</div>'
        )
        return CourierCenterCourier()._parse_html("013700000001", html)

    def test_out_for_delivery(self):
        result = self._parse("OutForDelivery", "Παραλαβή", "Αναχώρηση")
        assert (result.stage, result.problem) == ("out_for_delivery", None)

    def test_return_to_sender(self):
        result = self._parse("ReturnBackToShipper", "Παραλαβή", "Αναχώρηση")
        assert (result.stage, result.problem, result.status) == ("in_transit", "returning", "Returning to Sender")


class TestACS:
    @staticmethod
    def _parse(**parcel):
        history = [
            {"controlPointDate": "2026-11-10T10:00:00", "controlPoint": "ΑΘΗΝΑ", "description": "Η αποστολή παρελήφθη"},
            {"controlPointDate": "2026-11-11T10:00:00", "controlPoint": "ΑΘΗΝΑ", "description": "Η αποστολή βρίσκεται σε διάκριση"},
        ]
        return ACSCourier()._parse_response("1234567890", {"items": [{"statusHistory": history, **parcel}]})

    def test_in_transit_with_expected_delivery(self):
        result = self._parse(expectedDeliveryDate="2026-11-13T00:00:00")
        assert (result.stage, result.problem, result.estimated_delivery) == ("in_transit", None, "2026-11-13")

    def test_returning(self):
        result = self._parse(isReturned=True)
        assert (result.stage, result.problem, result.status) == ("in_transit", "returning", "Returning to Sender")

    def test_delivered_back_to_the_sender(self):
        result = self._parse(isReturned=True, isDelivered=True)
        assert (result.problem, result.status, result.status_category) == ("returned", "Returned", "in_transit")

    def test_delivered(self):
        result = self._parse(isDelivered=True, expectedDeliveryDate="2026-11-13T00:00:00")
        assert (result.stage, result.status, result.estimated_delivery) == ("delivered", "Delivered", None)


class TestSkroutz:
    def test_cancelled(self):
        data = {"status": "created", "isCompleteCancelled": True, "trackingDetails": []}
        result = SkroutzCourier()._parse_response("E8GYRRONRYKL9", data)
        assert (result.stage, result.problem) == ("created", "cancelled")

    def test_failed_delivery_status(self):
        data = {"status": "failed_delivery", "pickedUpAt": "2026-11-10T10:00:00Z", "trackingDetails": []}
        result = SkroutzCourier()._parse_response("E8GYRRONRYKL9", data)
        assert (result.stage, result.problem) == ("out_for_delivery", "attempt_failed")


class TestSpeedEx:
    def test_not_delivered_is_a_failed_attempt(self):
        courier = SpeedExCourier()
        events = [
            TrackingEvent(date="", time="", location="", status=status)
            for status in ("Η ΑΠΟΣΤΟΛΗ ΔΕΝ ΠΑΡΑΔΟΘΗΚΕ", "ΕΙΣΑΓΩΓΗ ΣΕ ΚΑΤΑΣΤΗΜΑ", "ΠΑΡΑΛΑΒΗ ΣΤΟ ΚΑΤΑΣΤΗΜΑ")
        ]
        courier.classify_events(events)
        assert courier.progress(events) == ("out_for_delivery", "attempt_failed")


class TestSvuum:
    def test_failed_delivery(self):
        data = [{
            "referenceNumber": "1234567",
            "processTimeLineLogsList": [
                {"status": "Ανεπιτυχής Παράδοση", "statusTime": "Feb-15-2026 11:00 AM", "statusCode": "S998"},
                {"status": "Επιτυχής Παραλαβή Στην Κεντρική Αποθήκη", "statusTime": "Feb-14-2026 05:40 PM", "statusCode": "S210"},
            ],
        }]
        result = SvuumCourier()._parse_response("1234567", data)
        assert (result.stage, result.problem, result.status_category) == (
            "out_for_delivery", "attempt_failed", "in_transit",
        )


def _found(number, stage, problem=None, category="in_transit"):
    return TrackingResult(
        success=True, tracking_number=number, courier="svuum", courier_name="Svuum",
        status="Moved", status_category=category, events=[], stage=stage, problem=problem,
    )


class TestCoordinator:
    """The coordinator keeps the progress and announces problems."""

    @staticmethod
    def _coordinator():
        configs = {"A": {"tracking_number": "A", "name": "Shoes", "courier": "svuum", "stop_tracking_delivered": False}}
        hass = MagicMock()
        hass.config.language = "el"
        return GreekCourierDataUpdateCoordinator(
            hass=hass, tracking_numbers=["A"], tracking_configs=configs, scan_interval=15,
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("before", "after", "expected"),
        [
            # A courier answering with fewer events doesn't undo a step
            (_found("A", "out_for_delivery"), _found("A", "in_transit"), "out_for_delivery"),
            (_found("A", "in_transit"), _found("A", "out_for_delivery"), "out_for_delivery"),
            # A return starts the trip back
            (_found("A", "out_for_delivery"), _found("A", "in_transit", "returning"), "in_transit"),
        ],
    )
    async def test_stage_never_goes_back(self, before, after, expected):
        coordinator = self._coordinator()
        with patch(f"{PACKAGE}._track_with_retry", AsyncMock(return_value=after)), \
                patch(f"{PACKAGE}.asyncio.sleep", AsyncMock()), patch(f"{PACKAGE}.async_get_clientsession"):
            data = await coordinator._async_fetch(["A"], {"A": before})

        assert data["A"].stage == expected

    def test_event_has_the_problem(self):
        coordinator = self._coordinator()
        coordinator._fire_status_events(
            {"A": _found("A", "out_for_delivery")}, {"A": _found("A", "out_for_delivery", "attempt_failed")}
        )

        _, data = coordinator.hass.bus.async_fire.call_args.args
        assert data["stage"] == "out_for_delivery"
        assert data["problem"] == "attempt_failed"
        assert data["old_problem"] is None
        assert data["problem_text"] == "Αποτυχημένη απόπειρα παράδοσης"

    def test_a_new_problem_alone_fires_an_event(self):
        coordinator = self._coordinator()
        coordinator._fire_status_events(
            {"A": _found("A", "in_transit")}, {"A": _found("A", "in_transit", "held")}
        )
        fired = [call.args[0] for call in coordinator.hass.bus.async_fire.call_args_list]
        assert fired == ["greek_courier_tracker_shipment_updated", "greek_courier_tracker_status_changed"]
