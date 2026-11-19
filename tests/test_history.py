"""Tests for the history of removed shipments (Configure → Settings → keep removed shipments)."""

import json
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.greek_courier_tracker.couriers.base import (
    TrackingEvent,
    TrackingResult,
)
from custom_components.greek_courier_tracker.shipment_history import (
    ShipmentHistory,
    history_message,
    snapshot,
    worth_keeping,
)

from .test_management import COMPONENT_DIR, _entry, _item, _result

MODULE = "custom_components.greek_courier_tracker.shipment_history"
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def _found(number, category="delivered", status="Delivered"):
    result = _result(number, category, status)
    event = TrackingEvent(date="2026-11-18", time="10:30", location="ΑΘΗΝΑ", status="Παραδόθηκε")
    result.events = [event]
    result.latest_event = event
    result.last_updated = "2026-11-18T10:35:00+00:00"
    return result


def _not_found(number):
    return TrackingResult(
        success=True, tracking_number=number, courier="unknown", courier_name="", status="Not Found",
        status_category="unknown", events=[],
    )


def _history(stored=None):
    """A ShipmentHistory whose store and dispatcher are mocks."""
    store = MagicMock()
    store.async_load = AsyncMock(return_value=stored)
    store.async_remove = AsyncMock()
    with patch(f"{MODULE}.Store", return_value=store):
        history = ShipmentHistory(MagicMock(), "entry_1")
    return history, store


def _kept(number, removed_at=NOW):
    return {"tracking_number": number, "name": number, "removed_at": removed_at.isoformat()}


class TestSnapshot:
    """What a kept shipment looks like."""

    def test_snapshot_freezes_the_shipment(self):
        """The snapshot has what the card shows, with the settings of the number."""
        item = snapshot(_item("A1", "Shoes", owner="u1"), _found("A1"), NOW)

        assert item["tracking_number"] == "A1"
        assert item["name"] == "Shoes"
        assert item["owner_user_id"] == "u1"
        assert item["courier"] == "skroutz"
        assert item["status"] == "Delivered"
        assert item["status_el"] == "Παραδόθηκε"
        assert item["delivered"] is True
        assert item["latest_place"] == "ΑΘΗΝΑ"
        assert item["events"] == [{
            "date": "2026-11-18", "time": "10:30", "location": "ΑΘΗΝΑ", "status": "Παραδόθηκε",
            "status_translated": None,
        }]
        assert item["removed_at"] == "2026-11-19T12:00:00+00:00"
        # Stored as JSON in .storage
        json.dumps(item)

    def test_only_found_shipments_are_kept(self):
        """Numbers that no courier found (or errors) have nothing to keep."""
        failed = TrackingResult(
            success=False, tracking_number="A1", courier="skroutz", courier_name="Skroutz Last Mile",
            status="Error", status_category="error", events=[],
        )
        assert worth_keeping(_found("A1"))
        assert worth_keeping(_result("A1"))
        assert not worth_keeping(None)
        assert not worth_keeping(_not_found("A1"))
        assert not worth_keeping(failed)


class TestShipmentHistory:
    """The stored history."""

    @pytest.mark.asyncio
    async def test_load(self):
        """Stored shipments are read back; broken items are skipped."""
        history, _ = _history({"shipments": [_kept("A1"), {"name": "no number"}, "junk"]})
        await history.async_load()
        assert [item["tracking_number"] for item in history.items] == ["A1"]
        assert "A1" in history

    @pytest.mark.asyncio
    async def test_load_empty(self):
        """Nothing stored yet."""
        history, _ = _history(None)
        await history.async_load()
        assert history.items == []

    def test_add_and_delete(self):
        """Adding and deleting save the history and tell the cards."""
        history, store = _history()
        with patch(f"{MODULE}.async_dispatcher_send") as send:
            history.async_add([_kept("A1", NOW - timedelta(days=1)), _kept("B2")])
            history.async_add([])
            assert [item["tracking_number"] for item in history.items] == ["B2", "A1"]

            assert history.async_delete(["A1", "C3"]) == ["A1"]
            assert history.async_delete(["C3"]) == []

        assert [item["tracking_number"] for item in history.items] == ["B2"]
        assert store.async_delay_save.call_count == 2
        assert send.call_count == 2
        assert store.async_delay_save.call_args.args[0]() == {"shipments": [_kept("B2")]}

    def test_add_replaces(self):
        """A number removed again replaces its older copy."""
        history, _ = _history()
        with patch(f"{MODULE}.async_dispatcher_send"):
            history.async_add([{**_kept("A1"), "name": "Old"}])
            history.async_add([{**_kept("A1"), "name": "New"}])
        assert [item["name"] for item in history.items] == ["New"]

    def test_purge(self):
        """Shipments removed more than the set days ago are deleted; 0 keeps them all."""
        history, _ = _history()
        with patch(f"{MODULE}.async_dispatcher_send"):
            history.async_add([
                _kept("OLD", NOW - timedelta(days=31)),
                _kept("NEW", NOW - timedelta(days=29)),
                {"tracking_number": "UNDATED", "removed_at": "not a date"},
            ])
            assert history.async_purge(0, NOW) == []
            assert history.async_purge(30, NOW) == ["OLD"]
        assert {item["tracking_number"] for item in history.items} == {"NEW", "UNDATED"}

    @pytest.mark.asyncio
    async def test_remove(self):
        """Removing the entry deletes the stored file."""
        history, store = _history()
        await history.async_remove()
        store.async_remove.assert_awaited_once()


class TestKeepInHistory:
    """Removed shipments go to the history when the setting is on."""

    @staticmethod
    def _coordinator(items, keep=True, days=0):
        from custom_components.greek_courier_tracker import (
            GreekCourierDataUpdateCoordinator,
        )

        entry = _entry(items)
        entry.options = {**entry.options, "keep_history": keep, "history_days": days}
        history, _ = _history()
        hass = MagicMock()
        hass.config.language = "en"
        hass.data = {}
        coordinator = GreekCourierDataUpdateCoordinator(
            hass=hass,
            tracking_numbers=[item["tracking_number"] for item in items],
            tracking_configs={item["tracking_number"]: item for item in items},
            scan_interval=1,
            entry=entry,
            history=history,
        )
        return coordinator, history

    def test_keeps_found_shipments(self):
        """Found shipments are kept; numbers never found are not."""
        coordinator, history = self._coordinator([_item("A1", "Shoes"), _item("B2")])

        with patch(f"{MODULE}.async_dispatcher_send"):
            coordinator.keep_in_history({
                "A1": (_item("A1", "Shoes"), _found("A1")),
                "B2": (_item("B2"), _not_found("B2")),
                "C3": (_item("C3"), None),
            })

        assert [item["tracking_number"] for item in history.items] == ["A1"]
        assert history.items[0]["name"] == "Shoes"

    def test_off_deletes_as_before(self):
        """With the setting off nothing is kept."""
        coordinator, history = self._coordinator([_item("A1")], keep=False)
        coordinator.keep_in_history({"A1": (_item("A1"), _found("A1"))})
        assert history.items == []

    def test_already_kept_is_not_replaced(self):
        """The listener doesn't keep again what the clean-up of deliveries just kept."""
        coordinator, history = self._coordinator([_item("A1")])
        with patch(f"{MODULE}.async_dispatcher_send"):
            history.async_add([{**_kept("A1"), "name": "First"}])
            coordinator.keep_in_history({"A1": (_item("A1", "Second"), _found("A1"))})
        assert [item["name"] for item in history.items] == ["First"]

    def test_old_deliveries_are_kept(self):
        """The clean-up of deliveries keeps the shipments before removing them."""
        coordinator, history = self._coordinator([_item("A1"), _item("B2")])
        coordinator.entry.options = {**coordinator.entry.options, "auto_remove_delivered": 7}
        old = _found("A1")
        old.latest_event = TrackingEvent(
            date=(datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d"), time="", location="", status="",
        )

        with patch(f"{MODULE}.async_dispatcher_send"):
            coordinator._remove_expired_deliveries({"A1": old, "B2": _result("B2")})

        assert [item["tracking_number"] for item in history.items] == ["A1"]
        options = coordinator.hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert [item["tracking_number"] for item in options["tracking_numbers"]] == ["B2"]

    @pytest.mark.asyncio
    async def test_apply_reports_removed_items(self):
        """Applying a new list gives the settings and last result of each removed number."""
        coordinator, _ = self._coordinator([_item("A1", "Shoes"), _item("B2")])
        coordinator.data = {"A1": _found("A1"), "B2": _result("B2")}
        coordinator._async_fetch = AsyncMock()
        coordinator.async_set_updated_data = MagicMock()

        changes = await coordinator.async_apply_tracking_data([_item("B2")], 1)

        config, result = changes.removed_items["A1"]
        assert config == _item("A1", "Shoes")
        assert result.status == "Delivered"
        assert list(changes.removed_items) == ["A1"]

    @pytest.mark.asyncio
    async def test_remove_then_listener_keeps_it(self):
        """End to end: the options listener keeps a removed shipment, and drops it when re-added."""
        from custom_components.greek_courier_tracker import _async_update_listener

        coordinator, history = self._coordinator([_item("A1", "Shoes"), _item("B2")])
        coordinator.data = {"A1": _found("A1"), "B2": _result("B2")}
        coordinator._async_fetch = AsyncMock(side_effect=lambda numbers, base: {
            **base, **{number: _result(number) for number in numbers}
        })
        coordinator.async_set_updated_data = MagicMock()
        hass = coordinator.hass
        hass.data = {"greek_courier_tracker": {"entry_1": coordinator}}
        entry = coordinator.entry

        with patch("custom_components.greek_courier_tracker.er.async_get"), patch(
            "custom_components.greek_courier_tracker.async_dispatcher_send"
        ), patch(f"{MODULE}.async_dispatcher_send"):
            entry.options = {**entry.options, "tracking_numbers": [_item("B2")]}
            await _async_update_listener(hass, entry)
            assert [item["tracking_number"] for item in history.items] == ["A1"]
            assert history.items[0]["status"] == "Delivered"

            entry.options = {**entry.options, "tracking_numbers": [_item("B2"), _item("A1")]}
            await _async_update_listener(hass, entry)
            assert history.items == []


class TestDeleteHistoryAction:
    """The delete_history action."""

    @staticmethod
    def _hass(history):
        hass = MagicMock()
        hass.data = {"greek_courier_tracker": {"entry_1": SimpleNamespace(history=history, entry=_entry())}}
        return hass

    @pytest.mark.asyncio
    async def test_deletes(self):
        """Kept shipments are deleted for good."""
        from custom_components.greek_courier_tracker.services import (
            async_delete_history,
        )

        history, _ = _history()
        with patch(f"{MODULE}.async_dispatcher_send"):
            history.async_add([_kept("A1"), _kept("B2")])
            await async_delete_history(self._hass(history), SimpleNamespace(data={"tracking_number": ["a 1"]}))
        assert [item["tracking_number"] for item in history.items] == ["B2"]

    @pytest.mark.asyncio
    async def test_unknown_number(self):
        """Nothing is deleted when a number isn't in the history."""
        from custom_components.greek_courier_tracker.services import (
            async_delete_history,
        )

        history, _ = _history()
        with patch(f"{MODULE}.async_dispatcher_send"):
            history.async_add([_kept("A1")])
            with pytest.raises(ServiceValidationError):
                await async_delete_history(
                    self._hass(history), SimpleNamespace(data={"tracking_number": ["A1", "ZZ9"]})
                )
        assert [item["tracking_number"] for item in history.items] == ["A1"]


class TestHistoryForTheCard:
    """What the card gets over the websocket."""

    def test_message(self):
        """The kept shipments of the loaded entries, and whether removing keeps them."""
        history, _ = _history()
        with patch(f"{MODULE}.async_dispatcher_send"):
            history.async_add([_kept("A1", NOW - timedelta(days=2)), _kept("B2")])
        entry = _entry()
        entry.options = {**entry.options, "keep_history": True}
        hass = MagicMock()
        hass.data = {"greek_courier_tracker": {"entry_1": SimpleNamespace(history=history, entry=entry)}}

        message = history_message(hass)
        assert [item["tracking_number"] for item in message["shipments"]] == ["B2", "A1"]
        assert message["keep_history"] is True

        entry.options = {**entry.options, "keep_history": False}
        assert history_message(hass)["keep_history"] is False

    def test_no_entries(self):
        """Before the entry is loaded the card gets an empty history."""
        hass = MagicMock()
        hass.data = {}
        assert history_message(hass) == {"shipments": [], "keep_history": False}

    def test_card_uses_the_same_names(self):
        """The card subscribes to the registered command and calls the registered action."""
        from custom_components.greek_courier_tracker import services
        from custom_components.greek_courier_tracker.shipment_history import (
            websocket_subscribe_history,
        )

        card = (COMPONENT_DIR / "frontend" / "greek-courier-tracker-card.js").read_text(encoding="utf-8")
        command = websocket_subscribe_history._ws_command  # type: ignore[attr-defined]
        assert command == "greek_courier_tracker/history/subscribe"
        assert "type: `${DOMAIN}/history/subscribe`" in card
        assert re.search(rf'"{services.SERVICE_DELETE_HISTORY}"', card)


class TestHistorySettings:
    """Configure → Settings."""

    @staticmethod
    def _flow(options=None):
        from custom_components.greek_courier_tracker.config_flow import (
            GreekCourierTrackerOptionsFlow,
        )

        entry = _entry([_item("A1")])
        entry.options = {**entry.options, **(options or {})}
        return GreekCourierTrackerOptionsFlow(entry)

    @pytest.mark.asyncio
    async def test_form_defaults(self):
        """Off and forever by default; the saved values otherwise."""
        result = await self._flow().async_step_settings()
        defaults = {str(key): key.default() for key in result["data_schema"].schema}
        assert defaults["keep_history"] is False
        assert defaults["history_days"] == 0

        result = await self._flow({"keep_history": True, "history_days": 90}).async_step_settings()
        defaults = {str(key): key.default() for key in result["data_schema"].schema}
        assert defaults["keep_history"] is True
        assert defaults["history_days"] == 90

    @pytest.mark.asyncio
    async def test_saved(self):
        """Both settings are saved with the others."""
        result = await self._flow().async_step_settings({
            "scan_interval_minutes": 60, "auto_remove_delivered": 0, "keep_history": True, "history_days": 365,
        })
        assert result["data"]["keep_history"] is True
        assert result["data"]["history_days"] == 365
        assert result["data"]["tracking_numbers"] == [_item("A1")]
