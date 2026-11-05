"""Tests for how often and how the couriers are asked."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.greek_courier_tracker import GreekCourierDataUpdateCoordinator
from custom_components.greek_courier_tracker.couriers import (
    ACSCourier,
    GenikiCourier,
    SvuumCourier,
    _track_with_retry,
    is_refused,
    track_with_auto_detect,
)
from custom_components.greek_courier_tracker.couriers.base import TrackingResult
from custom_components.greek_courier_tracker.scheduling import CourierSchedule, courier_interval
from custom_components.greek_courier_tracker.tracking import build_options, get_scan_interval

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
PACKAGE = "custom_components.greek_courier_tracker"


def _found(number, courier="svuum", category="in_transit", status="In Transit"):
    return TrackingResult(
        success=True, tracking_number=number, courier=courier, courier_name=courier,
        status=status, status_category=category, events=[],
    )


def _refused(number, code=429, courier="svuum"):
    return TrackingResult(
        success=False, tracking_number=number, courier=courier, courier_name=courier,
        status="Error", status_category="error", events=[], error_message=f"HTTP error: {code}",
    )


def _not_found(number, courier="svuum"):
    return TrackingResult(
        success=True, tracking_number=number, courier=courier, courier_name=courier,
        status="Not Found", status_category="unknown", events=[],
    )


def _coordinator(couriers: dict[str, str], scan_interval=15):
    """Build a coordinator from {tracking number: courier}."""
    configs = {
        number: {"tracking_number": number, "name": number, "courier": courier, "stop_tracking_delivered": False}
        for number, courier in couriers.items()
    }
    return GreekCourierDataUpdateCoordinator(
        hass=MagicMock(), tracking_numbers=list(configs), tracking_configs=configs, scan_interval=scan_interval,
    )


@pytest.fixture(autouse=True)
def no_waiting():
    """Don't wait out the spacing between requests, and use a clock tests can move."""
    with patch(f"{PACKAGE}.asyncio.sleep", AsyncMock()), patch(f"{PACKAGE}.async_get_clientsession"):
        yield


def _at(moment):
    return patch(f"{PACKAGE}.dt_util.utcnow", return_value=moment)


class TestCourierInterval:
    """The wait grows with the requests a courier needs."""

    @pytest.mark.parametrize(
        ("count", "minutes"), [(1, 15), (2, 30), (3, 45), (4, 60), (8, 60), (20, 60)]
    )
    def test_one_request_per_number(self, count, minutes):
        assert courier_interval("elta", count, 15) == timedelta(minutes=minutes)

    @pytest.mark.parametrize(("count", "minutes"), [(1, 15), (10, 15), (11, 30), (25, 45)])
    def test_batches_count_once(self, count, minutes):
        assert courier_interval("acs", count, 15, batch_size=10) == timedelta(minutes=minutes)

    def test_longer_base_is_kept_above_the_cap(self):
        assert courier_interval("elta", 3, 180) == timedelta(minutes=180)

    def test_unknown_courier_waits_at_least_an_hour(self):
        assert courier_interval("auto", 1, 15) == timedelta(minutes=60)


class TestCourierSchedule:
    def test_due_until_polled(self):
        schedule = CourierSchedule()
        assert schedule.is_due("elta", NOW)

        schedule.mark_polled("elta", timedelta(minutes=15), NOW)

        assert not schedule.is_due("elta", NOW + timedelta(minutes=14))
        # The jitter only ever makes a cycle longer, at most by a tenth
        assert not schedule.is_due("elta", NOW + timedelta(minutes=15) - timedelta(seconds=1))
        assert schedule.is_due("elta", NOW + timedelta(minutes=16, seconds=30))

    def test_backoff_doubles_up_to_the_maximum(self):
        schedule = CourierSchedule()
        delays = [schedule.record_blocked("elta", NOW) for _ in range(6)]
        assert [delay.total_seconds() / 60 for delay in delays] == [30, 60, 120, 240, 360, 360]

    def test_backoff_respects_retry_after(self):
        schedule = CourierSchedule()
        assert schedule.record_blocked("elta", NOW, retry_after=7200) == timedelta(hours=2)
        assert not schedule.is_due("elta", NOW + timedelta(hours=1))
        assert schedule.is_due("elta", NOW + timedelta(hours=2))

    def test_success_forgets_the_refusals(self):
        schedule = CourierSchedule()
        schedule.record_blocked("elta", NOW)
        schedule.record_success("elta")
        assert schedule.record_blocked("elta", NOW) == timedelta(minutes=30)

    def test_reconcile_applies_a_shorter_interval(self):
        schedule = CourierSchedule()
        schedule.mark_polled("elta", timedelta(hours=2), NOW)
        schedule.reconcile({"elta": timedelta(minutes=15)}, NOW)
        assert schedule.is_due("elta", NOW + timedelta(minutes=17))

    def test_reconcile_gives_a_new_courier_a_full_cycle(self):
        schedule = CourierSchedule()
        schedule.reconcile({"acs": timedelta(minutes=15)}, NOW)
        assert not schedule.is_due("acs", NOW + timedelta(minutes=14))

    def test_next_wake_is_never_immediate(self):
        schedule = CourierSchedule()
        schedule.mark_polled("elta", timedelta(minutes=15), NOW)
        assert schedule.next_wake(["elta"], NOW + timedelta(hours=1), timedelta(minutes=15)) == timedelta(seconds=60)

    def test_next_wake_waits_for_a_blocked_courier(self):
        schedule = CourierSchedule()
        schedule.mark_polled("elta", timedelta(minutes=15), NOW)
        schedule.record_blocked("elta", NOW)
        assert schedule.next_wake(["elta"], NOW, timedelta(minutes=15)) == timedelta(minutes=30)


class TestScanIntervalSetting:
    @staticmethod
    def _entry(data=None, options=None):
        entry = MagicMock()
        entry.data = data or {}
        entry.options = options or {}
        return entry

    @pytest.mark.parametrize(
        ("hours", "minutes"), [(1, 15), (0, 15), (2, 120), (6, 360), (100, 1440)]
    )
    def test_old_hours(self, hours, minutes):
        assert get_scan_interval(self._entry({"scan_interval": hours})) == minutes
        assert get_scan_interval(self._entry({}, {"scan_interval": hours})) == minutes

    def test_minutes_win_over_old_hours(self):
        entry = self._entry({"scan_interval": 6}, {"scan_interval": 6, "scan_interval_minutes": 45})
        assert get_scan_interval(entry) == 45

    @pytest.mark.parametrize(("stored", "minutes"), [(0, 15), (5, 15), (30, 30), (99999, 1440)])
    def test_limits(self, stored, minutes):
        assert get_scan_interval(self._entry({"scan_interval_minutes": stored})) == minutes

    def test_nothing_stored(self):
        assert get_scan_interval(self._entry()) == 15

    def test_saving_drops_the_old_key(self):
        options = build_options(self._entry({}, {"scan_interval": 6}), [])
        assert options == {"tracking_numbers": [], "scan_interval_minutes": 360}

    def test_forms_refuse_short_intervals(self):
        import voluptuous as vol

        from custom_components.greek_courier_tracker.config_flow import SCAN_INTERVAL_VALIDATOR

        assert SCAN_INTERVAL_VALIDATOR(15) == 15
        for value in (0, 14, 1441):
            with pytest.raises(vol.Invalid):
                SCAN_INTERVAL_VALIDATOR(value)


class TestCoordinatorSchedule:
    """Which numbers are asked on every wake-up."""

    @pytest.mark.asyncio
    async def test_couriers_have_their_own_cycle(self):
        """With 15 minutes, a lone Svuum number is asked twice as often as two ELTA ones."""
        coordinator = _coordinator({"A": "svuum", "B": "elta", "C": "elta"})
        asked = []

        async def track(courier, number):
            asked.append(number)
            return _found(number, courier.COURIER_CODE)

        with patch(f"{PACKAGE}._track_with_retry", track):
            with _at(NOW):
                coordinator.data = await coordinator._async_update_data()
            assert sorted(asked) == ["A", "B", "C"]
            assert timedelta(minutes=15) <= coordinator.update_interval <= timedelta(minutes=17)

            asked.clear()
            with _at(NOW + timedelta(minutes=17)):
                coordinator.data = await coordinator._async_update_data()
            assert asked == ["A"]

            asked.clear()
            with _at(NOW + timedelta(minutes=34)):
                coordinator.data = await coordinator._async_update_data()
            assert sorted(asked) == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_requests_to_one_courier_are_not_simultaneous(self):
        coordinator = _coordinator({"A": "elta", "B": "elta", "C": "elta"})
        running = 0
        most = 0

        async def track(courier, number):
            nonlocal running, most
            running += 1
            most = max(most, running)
            await asyncio.get_running_loop().run_in_executor(None, lambda: None)
            running -= 1
            return _found(number, "elta")

        with patch(f"{PACKAGE}._track_with_retry", track), _at(NOW), patch(
            f"{PACKAGE}.asyncio.sleep", AsyncMock()
        ) as sleep:
            await coordinator._async_fetch(["A", "B", "C"], {})

        assert most == 1
        assert sleep.await_count == 2
        sleep.assert_awaited_with(1.0)

    @pytest.mark.asyncio
    async def test_delivered_numbers_are_not_asked(self):
        """Without the stop option too, and they don't slow down the others."""
        coordinator = _coordinator({"A": "elta", "B": "elta"})
        coordinator.data = {"B": _found("B", "elta", "delivered", "Delivered")}
        track = AsyncMock(return_value=_found("A", "elta"))

        with patch(f"{PACKAGE}._track_with_retry", track), _at(NOW):
            data = await coordinator._async_update_data()

        assert [call.args[1] for call in track.await_args_list] == ["A"]
        assert data["B"].status == "Delivered"
        assert coordinator.update_interval <= timedelta(minutes=17)

    @pytest.mark.asyncio
    async def test_only_delivered_still_runs_the_clean_up(self):
        coordinator = _coordinator({"B": "elta"})
        coordinator.data = {"B": _found("B", "elta", "delivered", "Delivered")}
        coordinator._remove_expired_deliveries = MagicMock()

        with _at(NOW):
            await coordinator._async_update_data()

        coordinator._remove_expired_deliveries.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_courier_waits_an_hour(self):
        coordinator = _coordinator({"A": "auto"})
        detect = AsyncMock(return_value=_not_found("A"))

        with patch(f"{PACKAGE}.track_with_auto_detect", detect):
            with _at(NOW):
                coordinator.data = await coordinator._async_update_data()
            with _at(NOW + timedelta(minutes=30)):
                coordinator.data = await coordinator._async_update_data()
            assert detect.await_count == 1

            with _at(NOW + timedelta(minutes=67)):
                coordinator.data = await coordinator._async_update_data()
            assert detect.await_count == 2

    @pytest.mark.asyncio
    async def test_found_number_doesnt_fall_back_to_all_couriers(self):
        """An error from the known courier isn't a reason to ask the other seven."""
        coordinator = _coordinator({"A": "auto"})
        previous = _found("A", "svuum")
        coordinator.data = {"A": previous}
        detect = AsyncMock()

        with patch(f"{PACKAGE}._track_with_retry", AsyncMock(return_value=_refused("A", 500))), patch(
            f"{PACKAGE}.track_with_auto_detect", detect
        ), _at(NOW):
            data = await coordinator._async_update_data()

        detect.assert_not_awaited()
        assert data["A"] is previous

    @pytest.mark.asyncio
    async def test_a_shorter_setting_applies_right_away(self):
        coordinator = _coordinator({"A": "elta"}, scan_interval=120)
        coordinator.data = {"A": _found("A", "elta")}
        coordinator.async_set_updated_data = MagicMock()
        with patch(f"{PACKAGE}._track_with_retry", AsyncMock(return_value=_found("A", "elta"))), _at(NOW):
            coordinator.data = await coordinator._async_update_data()
        assert coordinator.update_interval > timedelta(minutes=100)

        item = coordinator.tracking_configs["A"]
        with _at(NOW):
            await coordinator.async_apply_tracking_data([item], 15)

        assert coordinator.update_interval <= timedelta(minutes=17)


class TestRefusals:
    """A courier that refuses a request is left alone."""

    @pytest.mark.parametrize("code", [403, 429, 503])
    def test_refusal_codes(self, code):
        assert is_refused(_refused("A", code))

    def test_other_errors_are_not_refusals(self):
        assert not is_refused(_refused("A", 500))
        assert not is_refused(_found("A"))

    @pytest.mark.asyncio
    @pytest.mark.parametrize("code", [403, 429, 503])
    async def test_refusals_are_not_retried(self, code):
        courier = SvuumCourier()
        courier.track = AsyncMock(return_value=_refused("A", code))
        await _track_with_retry(courier, "A")
        courier.track.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stops_at_the_first_refusal(self):
        coordinator = _coordinator({"A": "elta", "B": "elta", "C": "elta"})
        track = AsyncMock(side_effect=[_found("A", "elta"), _refused("B", 403, "elta"), _found("C", "elta")])

        with patch(f"{PACKAGE}._track_with_retry", track), _at(NOW):
            data = await coordinator._async_fetch(["A", "B", "C"], {})

        assert track.await_count == 2
        assert "C" not in data

    @pytest.mark.asyncio
    async def test_blocked_courier_is_skipped_until_it_passes(self):
        coordinator = _coordinator({"A": "elta", "B": "svuum"})
        previous = {"A": _found("A", "elta"), "B": _found("B", "svuum")}
        coordinator.data = previous
        asked = []

        async def track(courier, number):
            asked.append(number)
            return _refused(number, 429, "elta") if number == "A" else _found(number)

        with patch(f"{PACKAGE}._track_with_retry", track):
            with _at(NOW):
                coordinator.data = await coordinator._async_update_data()
            assert sorted(asked) == ["A", "B"]
            assert coordinator.data["A"] is previous["A"]

            # The other courier carries on, the refusing one waits 30 minutes
            asked.clear()
            with _at(NOW + timedelta(minutes=20)):
                coordinator.data = await coordinator._async_update_data()
            assert asked == ["B"]

            asked.clear()
            with _at(NOW + timedelta(minutes=31)):
                coordinator.data = await coordinator._async_update_data()
            assert "A" in asked

    @pytest.mark.asyncio
    async def test_retry_after_is_kept(self):
        coordinator = _coordinator({"A": "elta"})

        async def track(courier, number):
            courier.retry_after = 7200.0
            return _refused(number, 429, "elta")

        with patch(f"{PACKAGE}._track_with_retry", track), _at(NOW):
            await coordinator._async_fetch(["A"], {})

        assert coordinator._schedule.is_blocked("elta", NOW + timedelta(minutes=119))

    def test_retry_after_is_read_from_the_response(self):
        courier = SvuumCourier()
        courier._note_refusal(MagicMock(headers={"Retry-After": "120"}))
        assert courier.retry_after == 120
        courier._note_refusal(MagicMock(headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}))
        assert courier.retry_after is None
        courier._note_refusal(MagicMock(headers={}))
        assert courier.retry_after is None

    @pytest.mark.asyncio
    async def test_auto_detect_skips_blocked_and_reports_refusals(self):
        refused = []

        async def track(courier, number):
            return _refused(number, 403, courier.COURIER_CODE)

        with patch(f"{PACKAGE}.couriers._track_with_retry", track):
            await track_with_auto_detect("A", None, skip={"elta"}, on_refused=refused.append)

        codes = {str(getattr(courier.COURIER_CODE, "value", courier.COURIER_CODE)) for courier in refused}
        assert len(codes) == 7
        assert "elta" not in codes

    @pytest.mark.asyncio
    async def test_acs_keeps_its_token_on_a_refusal(self):
        """A 429 has nothing to do with the token, and asking again is what it complains about."""
        courier = ACSCourier(MagicMock())
        courier._search = AsyncMock(return_value=(429, None))
        result = await courier.track("1234567890")
        courier._search.assert_awaited_once()
        assert result.error_message == "HTTP error: 429"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("code", [401, 404, 406])
    async def test_acs_renews_an_expired_token(self, code):
        courier = ACSCourier(MagicMock())
        courier._search = AsyncMock(side_effect=[(code, None), (200, {"items": []})])
        result = await courier.track("1234567890")
        assert courier._search.await_args.kwargs == {"refresh_token": True}
        assert result.status == "Not Found"


def _acs_item(number):
    return {
        "trackingNumber": number,
        "isDelivered": False,
        "statusHistory": [
            {"controlPointDate": "2026-11-05T10:00:00", "controlPoint": "ΑΘΗΝΑ", "description": "Η αποστολή παρελήφθη"}
        ],
    }


def _geniki_number(*statuses):
    checkpoints = [
        {"Status": status, "StatusDate": "2026-11-05T10:00:00", "Shop": "ΑΘΗΝΑ", "StatusCode": "C_W3"}
        for status in statuses
    ]
    return {"TrackAndTraceResult": {"Result": 0, "Checkpoints": {"Checkpoint": checkpoints}}}


class TestBatches:
    """Couriers that answer for several numbers with one request."""

    @pytest.mark.asyncio
    async def test_acs_splits_the_answer_by_number(self):
        courier = ACSCourier(MagicMock())
        courier._search = AsyncMock(return_value=(200, {"items": [_acs_item("2222222222"), _acs_item("1111111111")]}))

        results = await courier.track_many(["1111111111", "2222222222", "3333333333"])

        courier._search.assert_awaited_once()
        assert courier._search.await_args.args[1] == "1111111111,2222222222,3333333333"
        assert results["1111111111"].tracking_number == "1111111111"
        assert results["1111111111"].success and results["1111111111"].events
        assert results["2222222222"].events
        assert results["3333333333"].status == "Not Found"

    @pytest.mark.asyncio
    async def test_acs_error_applies_to_all(self):
        courier = ACSCourier(MagicMock())
        courier._search = AsyncMock(return_value=(429, None))

        results = await courier.track_many(["1111111111", "2222222222"])

        courier._search.assert_awaited_once()
        assert all(is_refused(result) for result in results.values())

    @pytest.mark.asyncio
    async def test_geniki_asks_once_per_language(self):
        courier = GenikiCourier(MagicMock())
        answer = {"success": True, "111": _geniki_number("ΠΑΡΑΛΑΒΗ"), "222": {"TrackAndTraceResult": {"Result": 9, "Checkpoints": {}}}}
        english = {"success": True, "111": _geniki_number("Picked up")}
        courier._fetch = AsyncMock(side_effect=[(200, answer), (200, english)])

        results = await courier.track_many(["111", "222"])

        assert [(call.args[1], call.args[2]) for call in courier._fetch.await_args_list] == [
            ("111,222", "el"), ("111,222", "en"),
        ]
        assert results["111"].status == "Picked up"
        assert results["222"].status == "Not Found"

    @pytest.mark.asyncio
    async def test_geniki_nothing_found_skips_the_english_request(self):
        courier = GenikiCourier(MagicMock())
        courier._fetch = AsyncMock(return_value=(200, {"success": True}))

        results = await courier.track_many(["111", "222"])

        courier._fetch.assert_awaited_once()
        assert results["111"].status == "Not Found"

    @pytest.mark.asyncio
    async def test_geniki_keeps_greek_when_english_fails(self):
        courier = GenikiCourier(MagicMock())
        answer = {"111": _geniki_number("ΠΑΡΑΛΑΒΗ"), "222": _geniki_number("ΜΕΤΑΦΟΡΑ")}
        courier._fetch = AsyncMock(side_effect=[(200, answer), (500, None)])

        results = await courier.track_many(["111", "222"])

        assert results["111"].status == "Picked Up"
        assert results["222"].status == "In Transit"

    @pytest.mark.asyncio
    async def test_coordinator_asks_once_for_all(self):
        coordinator = _coordinator({"1111111111": "acs", "2222222222": "acs"})
        many = AsyncMock(side_effect=lambda numbers: {n: _found(n, "acs") for n in numbers})
        single = AsyncMock()

        with patch.object(ACSCourier, "track_many", many), patch(f"{PACKAGE}._track_with_retry", single), _at(NOW):
            data = await coordinator._async_fetch(["1111111111", "2222222222"], {})

        many.assert_awaited_once()
        single.assert_not_awaited()
        assert set(data) == {"1111111111", "2222222222"}

    @pytest.mark.asyncio
    async def test_batches_keep_the_interval_short(self):
        """Ten ACS numbers fit one request, so they are checked as often as one."""
        numbers = {f"{index:010d}": "acs" for index in range(10)}
        coordinator = _coordinator(numbers)
        many = AsyncMock(side_effect=lambda batch: {n: _found(n, "acs") for n in batch})

        with patch.object(ACSCourier, "track_many", many), _at(NOW):
            await coordinator._async_update_data()

        many.assert_awaited_once()
        assert coordinator.update_interval <= timedelta(minutes=17)

    @pytest.mark.asyncio
    async def test_more_numbers_than_fit_are_split(self):
        numbers = {f"{index:010d}": "acs" for index in range(12)}
        coordinator = _coordinator(numbers)
        many = AsyncMock(side_effect=lambda batch: {n: _found(n, "acs") for n in batch})

        with patch.object(ACSCourier, "track_many", many), _at(NOW):
            await coordinator._async_fetch(list(numbers), {})

        assert [len(call.args[0]) for call in many.await_args_list] == [10, 2]

    @pytest.mark.asyncio
    async def test_single_number_uses_the_normal_request(self):
        coordinator = _coordinator({"1111111111": "acs"})
        many = AsyncMock()
        single = AsyncMock(return_value=_found("1111111111", "acs"))

        with patch.object(ACSCourier, "track_many", many), patch(f"{PACKAGE}._track_with_retry", single), _at(NOW):
            await coordinator._async_fetch(["1111111111"], {})

        many.assert_not_awaited()
        single.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_batch_falls_back_to_single_requests(self):
        """The format isn't documented: if it stops working, shipments still update."""
        coordinator = _coordinator({"A": "acs", "B": "acs"})
        many = AsyncMock(side_effect=lambda numbers: {n: _refused(n, 400, "acs") for n in numbers})
        single = AsyncMock(side_effect=lambda courier, number: _found(number, "acs"))

        with patch.object(ACSCourier, "track_many", many), patch(f"{PACKAGE}._track_with_retry", single), _at(NOW):
            data = await coordinator._async_fetch(["A", "B"], {})

        assert single.await_count == 2
        assert data["A"].success and data["B"].success

    @pytest.mark.asyncio
    async def test_crashed_batch_falls_back_to_single_requests(self):
        coordinator = _coordinator({"A": "acs", "B": "acs"})
        many = AsyncMock(side_effect=ValueError("bad answer"))
        single = AsyncMock(side_effect=lambda courier, number: _found(number, "acs"))

        with patch.object(ACSCourier, "track_many", many), patch(f"{PACKAGE}._track_with_retry", single), _at(NOW):
            data = await coordinator._async_fetch(["A", "B"], {})

        assert single.await_count == 2
        assert set(data) == {"A", "B"}

    @pytest.mark.asyncio
    async def test_known_shipment_missing_from_a_batch_is_asked_alone(self):
        coordinator = _coordinator({"A": "acs", "B": "acs"})
        base = {"A": _found("A", "acs"), "B": _found("B", "acs")}
        many = AsyncMock(return_value={"A": _found("A", "acs", status="Moved"), "B": _not_found("B", "acs")})
        single = AsyncMock(return_value=_found("B", "acs", status="Moved too"))

        with patch.object(ACSCourier, "track_many", many), patch(f"{PACKAGE}._track_with_retry", single), _at(NOW):
            data = await coordinator._async_fetch(["A", "B"], base)

        assert [call.args[1] for call in single.await_args_list] == ["B"]
        assert data["B"].status == "Moved too"

    @pytest.mark.asyncio
    async def test_new_number_not_found_in_a_batch_is_not_asked_again(self):
        coordinator = _coordinator({"A": "acs", "B": "acs"})
        many = AsyncMock(return_value={"A": _not_found("A", "acs"), "B": _not_found("B", "acs")})
        single = AsyncMock()

        with patch.object(ACSCourier, "track_many", many), patch(f"{PACKAGE}._track_with_retry", single), _at(NOW):
            await coordinator._async_fetch(["A", "B"], {})

        single.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refused_batch_backs_off_without_single_requests(self):
        coordinator = _coordinator({"A": "acs", "B": "acs"})
        many = AsyncMock(side_effect=lambda numbers: {n: _refused(n, 429, "acs") for n in numbers})
        single = AsyncMock()

        with patch.object(ACSCourier, "track_many", many), patch(f"{PACKAGE}._track_with_retry", single), _at(NOW):
            await coordinator._async_fetch(["A", "B"], {})

        single.assert_not_awaited()
        assert coordinator._schedule.is_blocked("acs", NOW + timedelta(minutes=29))
