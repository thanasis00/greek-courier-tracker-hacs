"""Tests for managing tracking numbers: helpers, actions, to-do list, options menu and card."""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.components.todo import TodoItem, TodoItemStatus
from homeassistant.exceptions import ServiceValidationError

from custom_components.greek_courier_tracker.couriers.base import TrackingResult
from custom_components.greek_courier_tracker.tracking import (
    TrackingNumberExistsError,
    TrackingNumberNotFoundError,
    add_tracking_item,
    build_options,
    get_tracking_data,
    parse_tracking_input,
    remove_tracking_items,
    rename_tracking_item,
)

COMPONENT_DIR = Path(__file__).parent.parent / "custom_components" / "greek_courier_tracker"


def _entry(tracking_numbers=None, scan_interval=2, entry_id="entry_1"):
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.domain = "greek_courier_tracker"
    entry.title = "Greek Courier Tracker"
    entry.options = {"tracking_numbers": tracking_numbers or [], "scan_interval": scan_interval}
    entry.data = {}
    return entry


def _item(number, name=None, courier="auto"):
    return {"tracking_number": number, "name": name or number, "stop_tracking_delivered": False, "courier": courier}


def _result(number, category="in_transit", status="In transit"):
    return TrackingResult(
        success=True,
        tracking_number=number,
        courier="skroutz",
        courier_name="Skroutz Last Mile",
        status=status,
        status_category=category,
        events=[],
    )


class TestTrackingHelpers:
    """Tests for the tracking list helpers."""

    @pytest.mark.parametrize("text,expected", [
        ("se123456789gr", ("SE123456789GR", None)),
        ("SE123456789GR New shoes", ("SE123456789GR", "New shoes")),
        ("SE123456789GR: New shoes", ("SE123456789GR", "New shoes")),
        ("  1234567  ", ("1234567", None)),
        ("", ("", None)),
    ])
    def test_parse_tracking_input(self, text, expected):
        """Free text is split into tracking number and optional name."""
        assert parse_tracking_input(text) == expected

    def test_add_tracking_item(self):
        """Adding normalizes the number and defaults the name and courier."""
        result = add_tracking_item([], " ab12 cd34 ")
        assert result == [_item("AB12CD34")]

        result = add_tracking_item(result, "1234567", name="Shoes", courier="svuum")
        assert result[1] == _item("1234567", "Shoes", "svuum")

    def test_add_tracking_item_duplicate(self):
        """Adding an already tracked number fails."""
        with pytest.raises(TrackingNumberExistsError):
            add_tracking_item([_item("1234567")], "1234567")

    def test_remove_tracking_items(self):
        """Removing keeps the other numbers and fails for unknown ones."""
        data = [_item("A1"), _item("B2"), _item("C3")]
        assert remove_tracking_items(data, ["b2", "C3"]) == [_item("A1")]
        with pytest.raises(TrackingNumberNotFoundError):
            remove_tracking_items(data, ["Z9"])

    def test_rename_tracking_item(self):
        """Renaming changes only the name; an empty name falls back to the number."""
        data = [_item("A1"), _item("B2")]
        assert rename_tracking_item(data, "A1", "Shoes")[0]["name"] == "Shoes"
        assert rename_tracking_item(data, "A1", "  ")[0]["name"] == "A1"

    def test_get_tracking_data_migrates_old_format(self):
        """Old entries stored plain strings without courier."""
        entry = _entry()
        entry.options = {}
        entry.data = {"tracking_numbers": ["A1", {"tracking_number": "B2", "name": "Box"}]}
        assert get_tracking_data(entry) == [_item("A1"), _item("B2", "Box")]

    def test_build_options_keeps_scan_interval(self):
        """Saving a new list keeps the scan interval."""
        assert build_options(_entry(scan_interval=5), []) == {"tracking_numbers": [], "scan_interval": 5}


class TestActions:
    """Tests for the add_tracking / remove_tracking actions."""

    @staticmethod
    def _hass(entries):
        hass = MagicMock()
        hass.config_entries.async_entries.return_value = entries
        hass.config_entries.async_get_entry.side_effect = lambda entry_id: next(
            (entry for entry in entries if entry.entry_id == entry_id), None
        )
        return hass

    @staticmethod
    def _call(**data):
        return SimpleNamespace(data=data)

    @pytest.mark.asyncio
    async def test_add_tracking(self):
        """The action appends the number to the entry options."""
        from custom_components.greek_courier_tracker.services import async_add_tracking

        entry = _entry([_item("A1")])
        hass = self._hass([entry])

        await async_add_tracking(hass, self._call(tracking_number="1234567", name="Shoes", courier="svuum"))

        options = hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert options["tracking_numbers"] == [_item("A1"), _item("1234567", "Shoes", "svuum")]
        assert options["scan_interval"] == 2

    @pytest.mark.asyncio
    async def test_add_tracking_duplicate(self):
        """Adding an already tracked number is a validation error."""
        from custom_components.greek_courier_tracker.services import async_add_tracking

        hass = self._hass([_entry([_item("A1")])])
        with pytest.raises(ServiceValidationError):
            await async_add_tracking(hass, self._call(tracking_number="a1"))
        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_tracking_without_entry(self):
        """The integration has to be set up first."""
        from custom_components.greek_courier_tracker.services import async_add_tracking

        with pytest.raises(ServiceValidationError):
            await async_add_tracking(self._hass([]), self._call(tracking_number="A1"))

    @pytest.mark.asyncio
    async def test_add_tracking_to_given_entry(self):
        """config_entry_id picks the entry to change."""
        from custom_components.greek_courier_tracker.services import async_add_tracking

        first, second = _entry(entry_id="first"), _entry(entry_id="second")
        hass = self._hass([first, second])

        await async_add_tracking(hass, self._call(tracking_number="A1", config_entry_id="second"))
        assert hass.config_entries.async_update_entry.call_args.args[0] is second

        with pytest.raises(ServiceValidationError):
            await async_add_tracking(hass, self._call(tracking_number="A1", config_entry_id="missing"))

    @pytest.mark.asyncio
    async def test_remove_tracking(self):
        """The action removes the numbers from the entry options."""
        from custom_components.greek_courier_tracker.services import async_remove_tracking

        hass = self._hass([_entry([_item("A1"), _item("B2")])])
        await async_remove_tracking(hass, self._call(tracking_number=["A1"]))

        options = hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert options["tracking_numbers"] == [_item("B2")]

        with pytest.raises(ServiceValidationError):
            await async_remove_tracking(hass, self._call(tracking_number=["Z9"]))

    def test_schemas(self):
        """The courier must be a known code and the number list is normalized."""
        import voluptuous as vol

        from custom_components.greek_courier_tracker.services import (
            ADD_TRACKING_SCHEMA,
            REMOVE_TRACKING_SCHEMA,
        )

        assert ADD_TRACKING_SCHEMA({"tracking_number": "A1"})["courier"] == "auto"
        assert ADD_TRACKING_SCHEMA({"tracking_number": "A1", "courier": "skroutz"})["courier"] == "skroutz"
        with pytest.raises(vol.Invalid):
            ADD_TRACKING_SCHEMA({"tracking_number": "A1", "courier": "dhl"})
        assert REMOVE_TRACKING_SCHEMA({"tracking_number": "A1"})["tracking_number"] == ["A1"]


class TestShipmentsTodo:
    """Tests for the Shipments to-do list."""

    @staticmethod
    def _todo(entry, data=None):
        from custom_components.greek_courier_tracker.todo import GreekCourierShipmentsTodo

        coordinator = MagicMock()
        coordinator.data = data or {}
        todo = GreekCourierShipmentsTodo(coordinator, entry)
        todo.hass = MagicMock()
        return todo

    def test_todo_items(self):
        """Each tracked number is an item; delivered ones are completed."""
        entry = _entry([_item("A1", "Shoes"), _item("B2"), _item("C3", courier="geniki")])
        todo = self._todo(entry, {
            "A1": _result("A1", "delivered", "Delivered"),
            "B2": _result("B2"),
        })

        items = todo.todo_items
        assert [item.uid for item in items] == ["A1", "B2", "C3"]
        assert items[0].summary == "Shoes"
        assert items[0].status == TodoItemStatus.COMPLETED
        assert items[1].status == TodoItemStatus.NEEDS_ACTION
        assert items[1].description == "B2 · Skroutz Last Mile · In transit"
        assert items[2].description == "C3 · Geniki Taxydromiki"
        assert todo.unique_id == "entry_1_shipments"

    @pytest.mark.asyncio
    async def test_create_item_starts_tracking(self):
        """Adding an item adds the tracking number with the rest as name."""
        entry = _entry([_item("A1")])
        todo = self._todo(entry)

        await todo.async_create_todo_item(TodoItem(summary="se123456789gr New shoes"))

        options = todo.hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert options["tracking_numbers"][-1] == _item("SE123456789GR", "New shoes")

        with pytest.raises(ServiceValidationError):
            await todo.async_create_todo_item(TodoItem(summary="A1"))

    @pytest.mark.asyncio
    async def test_update_item_renames(self):
        """Renaming works, checking items off by hand is refused."""
        entry = _entry([_item("A1")])
        todo = self._todo(entry)

        await todo.async_update_todo_item(
            TodoItem(uid="A1", summary="Shoes", status=TodoItemStatus.NEEDS_ACTION)
        )
        options = todo.hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert options["tracking_numbers"] == [_item("A1", "Shoes")]

        with pytest.raises(ServiceValidationError):
            await todo.async_update_todo_item(
                TodoItem(uid="A1", summary="A1", status=TodoItemStatus.COMPLETED)
            )

    @pytest.mark.asyncio
    async def test_delete_items_stops_tracking(self):
        """Deleting items removes the tracking numbers."""
        entry = _entry([_item("A1"), _item("B2")])
        todo = self._todo(entry)

        await todo.async_delete_todo_items(["A1"])

        options = todo.hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert options["tracking_numbers"] == [_item("B2")]


class TestOptionsMenu:
    """Tests for the Configure menu."""

    @staticmethod
    def _flow(tracking_numbers):
        from custom_components.greek_courier_tracker.config_flow import GreekCourierTrackerOptionsFlow

        return GreekCourierTrackerOptionsFlow(_entry(tracking_numbers))

    @pytest.mark.asyncio
    async def test_menu_options(self):
        """Edit and remove only show up when there is something to edit."""
        result = await self._flow([]).async_step_init()
        assert result["type"] == "menu"
        assert result["menu_options"] == ["add_tracking", "settings"]

        result = await self._flow([_item("A1")]).async_step_init()
        assert result["menu_options"] == ["add_tracking", "edit_select", "delete_select", "settings"]
        assert "A1" in result["description_placeholders"]["tracking_list"]

    @pytest.mark.asyncio
    async def test_edit_via_menu(self):
        """The selected number is remembered for the edit form submit."""
        flow = self._flow([_item("A1"), _item("B2")])

        result = await flow.async_step_edit_select({"tracking_number": "B2"})
        assert result["type"] == "form"
        assert result["step_id"] == "edit_tracking"

        result = await flow.async_step_edit_tracking(
            {"name": "Box", "courier": "acs", "stop_tracking_delivered": True}
        )
        assert result["type"] == "create_entry"
        assert result["data"]["tracking_numbers"][1] == {
            "tracking_number": "B2", "name": "Box", "stop_tracking_delivered": True, "courier": "acs",
        }

    @pytest.mark.asyncio
    async def test_delete_via_menu(self):
        """Selected numbers are removed."""
        flow = self._flow([_item("A1"), _item("B2"), _item("C3")])

        result = await flow.async_step_delete_select({"tracking_numbers": ["A1", "C3"]})
        assert result["type"] == "create_entry"
        assert [item["tracking_number"] for item in result["data"]["tracking_numbers"]] == ["B2"]

    @pytest.mark.asyncio
    async def test_settings(self):
        """The scan interval is saved together with the numbers."""
        flow = self._flow([_item("A1")])

        result = await flow.async_step_settings({"scan_interval": 6, "auto_remove_delivered": 14})
        assert result["type"] == "create_entry"
        assert result["data"] == {
            "tracking_numbers": [_item("A1")], "scan_interval": 6, "auto_remove_delivered": 14,
        }

    @pytest.mark.asyncio
    async def test_add_keeps_other_settings(self):
        """Adding a number doesn't drop the clean-up setting."""
        flow = self._flow([_item("A1")])
        flow.config_entry.options = {**flow.config_entry.options, "auto_remove_delivered": 7}

        result = await flow.async_step_add_tracking(
            {"tracking_number": "B2", "name": "", "courier": "auto", "stop_tracking_delivered": False}
        )
        assert result["data"]["auto_remove_delivered"] == 7


class TestConfigFlowUserStep:
    """Tests for the initial setup step."""

    @staticmethod
    def _flow(existing_entries):
        from custom_components.greek_courier_tracker.config_flow import GreekCourierTrackerConfigFlow

        flow = GreekCourierTrackerConfigFlow()
        flow.hass = MagicMock()
        flow.context = {"source": "user"}
        flow._async_current_entries = MagicMock(return_value=existing_entries)
        return flow

    @pytest.mark.asyncio
    async def test_single_instance(self):
        """A second entry is not created."""
        result = await self._flow([_entry()]).async_step_user()
        assert result["type"] == "abort"
        assert result["reason"] == "single_instance_allowed"

    @pytest.mark.asyncio
    async def test_first_number_is_optional(self):
        """The integration can be set up without a tracking number."""
        result = await self._flow([]).async_step_user({"tracking_numbers": "", "scan_interval": 1})
        assert result["type"] == "create_entry"
        assert result["data"]["tracking_numbers"] == []


class TestFrontendCard:
    """Tests that keep the bundled card in sync with the integration."""

    CARD = COMPONENT_DIR / "frontend" / "greek-courier-tracker-card.js"

    def test_card_lists_all_couriers(self):
        """The card's courier dropdown has the same couriers as the config flow."""
        from custom_components.greek_courier_tracker.config_flow import COURIER_LIST

        source = self.CARD.read_text(encoding="utf-8")
        block = source[source.index("const COURIERS"):source.index("];", source.index("const COURIERS"))]
        card_codes = re.findall(r'\["([a-z_]+)"', block)
        assert card_codes == [code.value for code, _ in COURIER_LIST]

    def test_services_yaml_lists_all_couriers(self):
        """The action's courier selector has the same couriers as the config flow."""
        import yaml

        from custom_components.greek_courier_tracker.config_flow import COURIER_LIST

        services = yaml.safe_load((COMPONENT_DIR / "services.yaml").read_text(encoding="utf-8"))
        options = services["add_tracking"]["fields"]["courier"]["selector"]["select"]["options"]
        assert options == [code.value for code, _ in COURIER_LIST]

    def test_card_file_name_matches_const(self):
        """The registered card URL points to an existing file."""
        from custom_components.greek_courier_tracker.const import CARD_FILENAME

        assert (COMPONENT_DIR / "frontend" / CARD_FILENAME).is_file()

    def test_translations_match(self):
        """English and Greek translations have the same keys as strings.json."""
        import json

        def keys(data, prefix=""):
            return {
                key
                for name, value in data.items()
                for key in (keys(value, f"{prefix}{name}.") if isinstance(value, dict) else {f"{prefix}{name}"})
            }

        strings = keys(json.loads((COMPONENT_DIR / "strings.json").read_text(encoding="utf-8")))
        for language in ("en", "el"):
            translation = json.loads((COMPONENT_DIR / "translations" / f"{language}.json").read_text(encoding="utf-8"))
            assert keys(translation) == strings, language


class TestInPlaceUpdates:
    """Changes to the tracked numbers are applied without reloading the entry."""

    @staticmethod
    def _coordinator(items, data=None, scan_interval=1):
        from unittest.mock import AsyncMock

        from custom_components.greek_courier_tracker import GreekCourierDataUpdateCoordinator

        hass = MagicMock()
        hass.data = {}
        coordinator = GreekCourierDataUpdateCoordinator(
            hass=hass,
            tracking_numbers=[item["tracking_number"] for item in items],
            tracking_configs={item["tracking_number"]: item for item in items},
            scan_interval=scan_interval,
        )
        coordinator.data = data or {}

        async def fetch(numbers, base):
            return {**base, **{number: _result(number, status=f"Fetched {number}") for number in numbers}}

        coordinator._async_fetch = AsyncMock(side_effect=fetch)
        coordinator.async_set_updated_data = MagicMock()
        return coordinator

    @pytest.mark.asyncio
    async def test_apply_adds_and_removes(self):
        """Only the new number is fetched; removed numbers drop out of the data."""
        coordinator = self._coordinator(
            [_item("A1"), _item("B2")], {"A1": _result("A1"), "B2": _result("B2")}
        )

        changes = await coordinator.async_apply_tracking_data([_item("A1"), _item("C3", "Shoes")], 1)

        assert changes.added == [_item("C3", "Shoes")]
        assert changes.removed == ["B2"]
        assert changes.changed == {}
        assert coordinator._async_fetch.await_args.args[0] == ["C3"]
        assert coordinator.tracking_numbers == ["A1", "C3"]

        data = coordinator.async_set_updated_data.call_args.args[0]
        assert set(data) == {"A1", "C3"}
        assert data["A1"].status == "In transit"
        assert data["C3"].status == "Fetched C3"

    @pytest.mark.asyncio
    async def test_apply_refetches_only_on_courier_change(self):
        """A rename doesn't fetch; a new courier does (and drops the old result)."""
        coordinator = self._coordinator(
            [_item("A1"), _item("B2")], {"A1": _result("A1"), "B2": _result("B2")}
        )

        changes = await coordinator.async_apply_tracking_data(
            [_item("A1", "Renamed"), _item("B2", courier="acs")], 1
        )

        assert set(changes.changed) == {"A1", "B2"}
        assert changes.added == [] and changes.removed == []
        assert coordinator._async_fetch.await_args.args[0] == ["B2"]
        # The old result of B2 isn't kept when the courier changes
        assert "B2" not in coordinator._async_fetch.await_args.args[1]

        data = coordinator.async_set_updated_data.call_args.args[0]
        assert data["A1"].status == "In transit"
        assert data["B2"].status == "Fetched B2"

    @pytest.mark.asyncio
    async def test_apply_scan_interval(self):
        """A new scan interval is applied in place."""
        from datetime import timedelta

        coordinator = self._coordinator([_item("A1")], {"A1": _result("A1")})

        await coordinator.async_apply_tracking_data([_item("A1")], 6)

        assert coordinator.update_interval == timedelta(hours=6)
        coordinator._async_fetch.assert_not_awaited()
        coordinator.async_set_updated_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_listener_without_reload(self):
        """The options listener removes, adds and updates sensors instead of reloading."""
        from unittest.mock import AsyncMock, patch

        from custom_components.greek_courier_tracker import TrackingChanges, _async_update_listener

        entry = _entry([_item("A1", "Renamed"), _item("C3")])
        coordinator = MagicMock()
        coordinator.async_apply_tracking_data = AsyncMock(return_value=TrackingChanges(
            added=[_item("C3")], removed=["B2"], changed={"A1": _item("A1", "Renamed")},
        ))
        hass = MagicMock()
        hass.data = {"greek_courier_tracker": {"entry_1": coordinator}}
        hass.config_entries.async_reload = AsyncMock()
        registry = MagicMock()
        registry.async_get_entity_id.return_value = "sensor.greek_courier_tracker_b2"

        with patch("custom_components.greek_courier_tracker.er.async_get", return_value=registry), patch(
            "custom_components.greek_courier_tracker.async_dispatcher_send"
        ) as send:
            await _async_update_listener(hass, entry)

        coordinator.async_apply_tracking_data.assert_awaited_once_with(get_tracking_data(entry), 2)
        registry.async_get_entity_id.assert_called_once_with("sensor", "greek_courier_tracker", "entry_1_B2")
        registry.async_remove.assert_called_once_with("sensor.greek_courier_tracker_b2")
        signals = {call.args[1]: call.args[2] for call in send.call_args_list}
        assert signals["greek_courier_tracker_tracking_added_entry_1"] == [_item("C3")]
        assert signals["greek_courier_tracker_tracking_changed_entry_1"] == {"A1": _item("A1", "Renamed")}
        hass.config_entries.async_reload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_listener_reloads_when_not_loaded(self):
        """Without a running coordinator the entry is simply reloaded."""
        from unittest.mock import AsyncMock

        from custom_components.greek_courier_tracker import _async_update_listener

        hass = MagicMock()
        hass.data = {}
        hass.config_entries.async_reload = AsyncMock()

        await _async_update_listener(hass, _entry())

        hass.config_entries.async_reload.assert_awaited_once_with("entry_1")

    def test_sensor_follows_config_changes(self):
        """A renamed number updates its sensor in place."""
        from custom_components.greek_courier_tracker.sensor import GreekCourierTrackingSensor

        coordinator = MagicMock()
        coordinator.data = {"A1": _result("A1")}
        sensor = GreekCourierTrackingSensor(coordinator, _entry(), "A1", "Old name")
        sensor.async_write_ha_state = MagicMock()

        sensor._async_config_changed({"B2": _item("B2", "Other")})
        sensor.async_write_ha_state.assert_not_called()

        sensor._async_config_changed({"A1": {**_item("A1", "New name"), "stop_tracking_delivered": True}})
        assert sensor.name == "New name"
        assert sensor.extra_state_attributes["tracking_name"] == "New name"
        assert sensor.extra_state_attributes["stop_tracking_delivered"] is True
        sensor.async_write_ha_state.assert_called_once()


class TestOptionsFlowSavesChanges:
    """The options flow must not change the entry's options in place."""

    @staticmethod
    def _flow_and_entry():
        from types import MappingProxyType

        from custom_components.greek_courier_tracker.config_flow import GreekCourierTrackerOptionsFlow

        entry = _entry([_item("A1"), {"tracking_number": "B2", "name": "B2", "stop_tracking_delivered": False}])
        entry.options = MappingProxyType(dict(entry.options))
        return GreekCourierTrackerOptionsFlow(entry), entry

    @pytest.mark.asyncio
    async def test_add_does_not_mutate_entry(self):
        """Otherwise Home Assistant sees equal options and doesn't save them."""
        flow, entry = self._flow_and_entry()
        before = [dict(item) for item in entry.options["tracking_numbers"]]

        result = await flow.async_step_add_tracking(
            {"tracking_number": "C3", "name": "", "courier": "acs", "stop_tracking_delivered": False}
        )

        assert entry.options["tracking_numbers"] == before
        assert result["data"]["tracking_numbers"] != entry.options["tracking_numbers"]
        assert result["data"]["tracking_numbers"][-1]["tracking_number"] == "C3"
        # Old items without courier get one in the saved data only
        assert result["data"]["tracking_numbers"][1]["courier"] == "auto"

    @pytest.mark.asyncio
    async def test_edit_does_not_mutate_entry(self):
        """Editing the courier yields options that differ from the stored ones."""
        flow, entry = self._flow_and_entry()

        await flow.async_step_edit_select({"tracking_number": "A1"})
        result = await flow.async_step_edit_tracking(
            {"name": "A1", "courier": "svuum", "stop_tracking_delivered": False}
        )

        assert entry.options["tracking_numbers"][0]["courier"] == "auto"
        assert result["data"]["tracking_numbers"][0]["courier"] == "svuum"



class TestEfficiency:
    """Auto-detection tries likely couriers first and remembers what it found."""

    @pytest.mark.parametrize("number,first", [
        ("3416482", "svuum"),
        ("E8GYRRONRYKL9", "skroutz"),
        ("SE123456789GR", "elta"),
        ("5194247074", "acs"),
    ])
    def test_couriers_by_likelihood(self, number, first):
        """Couriers whose number format matches come first; all are still tried."""
        from custom_components.greek_courier_tracker.couriers import COURIER_REGISTRY, couriers_by_likelihood

        ordered = couriers_by_likelihood(number)
        assert ordered[0].COURIER_CODE == first
        assert set(ordered) == set(COURIER_REGISTRY.values())

    @pytest.mark.asyncio
    async def test_rate_limited_requests_are_not_retried(self):
        """Retrying a 429 only makes the rate limiting worse."""
        from unittest.mock import AsyncMock

        from custom_components.greek_courier_tracker.couriers import SvuumCourier, _track_with_retry

        courier = SvuumCourier()
        courier.track = AsyncMock(return_value=TrackingResult(
            success=False, tracking_number="1234567", courier="svuum", courier_name="Svuum",
            status="Error", status_category="error", events=[], error_message="HTTP error: 429",
        ))

        result = await _track_with_retry(courier, "1234567")

        assert courier.track.await_count == 1
        assert result.error_message == "HTTP error: 429"

    @pytest.mark.asyncio
    async def test_coordinator_uses_detected_courier(self):
        """An auto number that was found before only asks that courier."""
        from unittest.mock import AsyncMock, patch

        from custom_components.greek_courier_tracker import GreekCourierDataUpdateCoordinator

        hass = MagicMock()
        coordinator = GreekCourierDataUpdateCoordinator(
            hass=hass, tracking_numbers=["A1"], tracking_configs={"A1": _item("A1")}, scan_interval=1,
        )
        previous = _result("A1")
        fresh = _result("A1", status="Out for delivery")

        with patch("custom_components.greek_courier_tracker.async_get_clientsession"), patch(
            "custom_components.greek_courier_tracker._track_with_retry", AsyncMock(return_value=fresh)
        ) as track, patch(
            "custom_components.greek_courier_tracker.track_with_auto_detect", AsyncMock()
        ) as auto_detect:
            data = await coordinator._async_fetch(["A1"], {"A1": previous})

        assert track.await_args.args[0].COURIER_CODE == "skroutz"
        auto_detect.assert_not_awaited()
        assert data["A1"].status == "Out for delivery"

    @pytest.mark.asyncio
    async def test_coordinator_detects_when_nothing_known(self):
        """Without an earlier result all couriers are tried."""
        from unittest.mock import AsyncMock, patch

        from custom_components.greek_courier_tracker import GreekCourierDataUpdateCoordinator

        coordinator = GreekCourierDataUpdateCoordinator(
            hass=MagicMock(), tracking_numbers=["A1"], tracking_configs={"A1": _item("A1")}, scan_interval=1,
        )

        with patch("custom_components.greek_courier_tracker.async_get_clientsession"), patch(
            "custom_components.greek_courier_tracker.track_with_auto_detect",
            AsyncMock(return_value=_result("A1")),
        ) as auto_detect:
            await coordinator._async_fetch(["A1"], {})

        auto_detect.assert_awaited_once()


class TestStatusText:
    """The sensor state follows the Home Assistant language."""

    def test_english(self):
        from custom_components.greek_courier_tracker.tracking import status_text

        assert status_text(_result("A1", status="In Transit"), "en") == "In Transit"
        assert status_text(_result("A1", "delivered", "Delivered"), "en", stopped=True) == "Delivered - Tracking Stopped"

    def test_greek(self):
        from custom_components.greek_courier_tracker.couriers.base import TrackingEvent
        from custom_components.greek_courier_tracker.tracking import status_text

        result = _result("A1", status="The shipment is at the hub")
        assert status_text(result, "el") == "The shipment is at the hub"

        result.latest_event = TrackingEvent(date="", time="", location="", status="Στο κέντρο διαλογής")
        assert status_text(result, "el") == "Στο κέντρο διαλογής"

        result.status_el = "Η αποστολή είναι στο κέντρο διαλογής"
        assert status_text(result, "el") == "Η αποστολή είναι στο κέντρο διαλογής"

        assert status_text(_result("A1", "unknown", "Not Found"), "el") == "Δεν βρέθηκε ακόμα"
        assert status_text(_result("A1", status="In Transit"), "el-GR") == "Σε μεταφορά"
        assert status_text(_result("A1", "delivered", "Delivered"), "el", stopped=True) == (
            "Παραδόθηκε - Τέλος παρακολούθησης"
        )


class TestStatusEventsAndCleanup:
    """Status change events and removal of old deliveries."""

    @staticmethod
    def _coordinator(entry=None):
        from custom_components.greek_courier_tracker import GreekCourierDataUpdateCoordinator

        hass = MagicMock()
        hass.config.language = "en"
        items = get_tracking_data(entry) if entry else [_item("A1", "Shoes")]
        return GreekCourierDataUpdateCoordinator(
            hass=hass,
            tracking_numbers=[item["tracking_number"] for item in items],
            tracking_configs={item["tracking_number"]: item for item in items},
            scan_interval=1,
            entry=entry,
        )

    def test_event_on_status_change(self):
        """A changed status fires greek_courier_tracker_status_changed."""
        coordinator = self._coordinator()

        coordinator._fire_status_events(
            {"A1": _result("A1")}, {"A1": _result("A1", "delivered", "Delivered")}
        )

        event_type, data = coordinator.hass.bus.async_fire.call_args.args
        assert event_type == "greek_courier_tracker_status_changed"
        assert data["tracking_number"] == "A1"
        assert data["name"] == "Shoes"
        assert data["old_status"] == "In transit"
        assert data["status"] == "Delivered"
        assert data["delivered"] is True
        assert data["courier_name"] == "Skroutz Last Mile"

    def test_no_event_without_change(self):
        """Unchanged, new and failed results don't fire events."""
        coordinator = self._coordinator()
        failed = TrackingResult(
            success=False, tracking_number="A1", courier="skroutz", courier_name="Skroutz Last Mile",
            status="Error", status_category="error", events=[],
        )

        coordinator._fire_status_events({"A1": _result("A1")}, {"A1": _result("A1")})
        coordinator._fire_status_events({}, {"A1": _result("A1")})
        coordinator._fire_status_events({"A1": _result("A1")}, {"A1": failed})

        coordinator.hass.bus.async_fire.assert_not_called()

    def test_old_deliveries_are_removed(self):
        """Shipments delivered longer ago than the setting are removed."""
        from datetime import datetime, timedelta

        from custom_components.greek_courier_tracker.couriers.base import TrackingEvent

        entry = _entry([_item("A1"), _item("B2"), _item("C3")])
        entry.options = {**entry.options, "auto_remove_delivered": 7}
        coordinator = self._coordinator(entry)

        def delivered(number, days_ago):
            result = _result(number, "delivered", "Delivered")
            day = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            result.latest_event = TrackingEvent(date=day, time="12:00", location="", status="Delivered")
            return result

        coordinator._remove_expired_deliveries(
            {"A1": delivered("A1", 10), "B2": delivered("B2", 2), "C3": _result("C3")}
        )

        options = coordinator.hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert [item["tracking_number"] for item in options["tracking_numbers"]] == ["B2", "C3"]
        assert options["auto_remove_delivered"] == 7

    def test_cleanup_off_by_default(self):
        """Without the setting nothing is removed."""
        from datetime import datetime, timedelta

        from custom_components.greek_courier_tracker.couriers.base import TrackingEvent

        coordinator = self._coordinator(_entry([_item("A1")]))
        result = _result("A1", "delivered", "Delivered")
        result.latest_event = TrackingEvent(
            date=(datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d"), time="", location="", status="",
        )

        coordinator._remove_expired_deliveries({"A1": result})

        coordinator.hass.config_entries.async_update_entry.assert_not_called()

    def test_build_options_keeps_settings(self):
        """Saving a new list keeps every other option."""
        entry = _entry([_item("A1")])
        entry.options = {**entry.options, "auto_remove_delivered": 5}
        assert build_options(entry, [])["auto_remove_delivered"] == 5


class TestBlueprint:
    """The notification blueprint is valid for Home Assistant."""

    def test_blueprint_is_valid(self):
        from homeassistant.components.blueprint.models import Blueprint
        from homeassistant.util.yaml.loader import load_yaml

        path = Path(__file__).parent.parent / "blueprints" / "automation" / "greek_courier_tracker" / (
            "shipment_status_notification.yaml"
        )
        try:
            from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA

            blueprint = Blueprint(load_yaml(str(path)), expected_domain="automation", schema=BLUEPRINT_SCHEMA)
        except (ImportError, TypeError):
            # Older Home Assistant validates without a schema argument
            blueprint = Blueprint(load_yaml(str(path)), expected_domain="automation")
        assert set(blueprint.inputs) == {"notify_device", "only_delivered"}
