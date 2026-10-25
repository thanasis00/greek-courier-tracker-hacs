"""Tests for managing tracking numbers: helpers, actions, to-do list, options menu and card."""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.todo import TodoItem, TodoItemStatus
from homeassistant.core import Context, State
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
    set_tracking_owner,
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


def _item(number, name=None, courier="auto", owner=None):
    return {
        "tracking_number": number, "name": name or number, "stop_tracking_delivered": False,
        "courier": courier, "owner": owner,
    }


def _user(user_id, name, active=True, system=False):
    return SimpleNamespace(id=user_id, name=name, is_active=active, system_generated=system)


PEOPLE = [
    State("person.athanasios", "home", {"user_id": "u1", "friendly_name": "Athanasios"}),
    State("person.maria", "home", {"user_id": "u2", "friendly_name": "Maria"}),
    State("person.guest", "home", {"friendly_name": "Guest"}),
]


def _people_hass():
    """A hass mock with people and users."""
    hass = MagicMock()
    hass.states.async_all.side_effect = lambda domain=None: [
        state for state in PEOPLE if domain is None or state.domain == domain
    ]
    hass.states.get.side_effect = lambda entity_id: next(
        (state for state in PEOPLE if state.entity_id == entity_id), None
    )
    users = [_user("u1", "athanasios"), _user("u2", "maria"), _user("sys", "Supervisor", system=True)]
    hass.auth.async_get_users = AsyncMock(return_value=users)
    hass.auth.async_get_user = AsyncMock(
        side_effect=lambda user_id: next((user for user in users if user.id == user_id), None)
    )
    return hass


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

    def test_add_tracking_item_owner(self):
        """The owner is a user ID; an empty one means shared."""
        assert add_tracking_item([], "A1", owner="u1")[0]["owner"] == "u1"
        assert add_tracking_item([], "A1", owner="")[0]["owner"] is None

    def test_set_tracking_owner(self):
        """Changing the owner keeps everything else; unknown numbers fail."""
        data = [_item("A1", "Shoes", owner="u1"), _item("B2")]
        assert set_tracking_owner(data, ["a1"], "u2") == [_item("A1", "Shoes", owner="u2"), _item("B2")]
        assert set_tracking_owner(data, ["A1"], None)[0] == _item("A1", "Shoes")
        with pytest.raises(TrackingNumberNotFoundError):
            set_tracking_owner(data, ["Z9"], "u1")

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

    def test_get_tracking_data_keeps_owner(self):
        """The owner survives reading the entry."""
        assert get_tracking_data(_entry([_item("A1", owner="u1")]))[0]["owner"] == "u1"

    def test_build_options_keeps_scan_interval(self):
        """Saving a new list keeps the scan interval."""
        assert build_options(_entry(scan_interval=5), []) == {"tracking_numbers": [], "scan_interval": 5}


class TestActions:
    """Tests for the add_tracking / remove_tracking actions."""

    @staticmethod
    def _hass(entries):
        hass = _people_hass()
        hass.config_entries.async_entries.return_value = entries
        hass.config_entries.async_get_entry.side_effect = lambda entry_id: next(
            (entry for entry in entries if entry.entry_id == entry_id), None
        )
        return hass

    @staticmethod
    def _call(user_id=None, **data):
        return SimpleNamespace(data=data, context=Context(user_id=user_id))

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
    async def test_add_tracking_owner(self):
        """The caller owns the shipment unless an owner (or "" for shared) is given."""
        from custom_components.greek_courier_tracker.services import async_add_tracking

        hass = self._hass([_entry()])

        async def owner_of(**data):
            await async_add_tracking(hass, self._call(tracking_number="A1", **data))
            return hass.config_entries.async_update_entry.call_args.kwargs["options"]["tracking_numbers"][0]["owner"]

        assert await owner_of(user_id="u1") == "u1"
        assert await owner_of() is None
        assert await owner_of(user_id="u1", owner="person.maria") == "u2"
        assert await owner_of(user_id="u1", owner="u2") == "u2"
        assert await owner_of(user_id="u1", owner="") is None
        with pytest.raises(ServiceValidationError):
            await owner_of(owner="person.guest")
        with pytest.raises(ServiceValidationError):
            await owner_of(owner="nobody")

    @pytest.mark.asyncio
    async def test_set_owner(self):
        """set_owner changes the owner; without one the shipment is shared."""
        from custom_components.greek_courier_tracker.services import async_set_owner

        hass = self._hass([_entry([_item("A1", owner="u1"), _item("B2")])])

        await async_set_owner(hass, self._call(tracking_number=["A1", "B2"], owner="person.maria"))
        options = hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert [item["owner"] for item in options["tracking_numbers"]] == ["u2", "u2"]

        await async_set_owner(hass, self._call(tracking_number=["A1"]))
        options = hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert options["tracking_numbers"][0]["owner"] is None

        with pytest.raises(ServiceValidationError):
            await async_set_owner(hass, self._call(tracking_number=["Z9"], owner="person.maria"))

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

    @pytest.mark.asyncio
    async def test_remove_tracking_finds_entry(self):
        """Without config_entry_id each number is removed from the entry that tracks it."""
        from custom_components.greek_courier_tracker.services import async_remove_tracking

        first = _entry([_item("A1")], entry_id="first")
        second = _entry([_item("B2"), _item("C3")], entry_id="second")
        hass = self._hass([first, second])

        await async_remove_tracking(hass, self._call(tracking_number=["b2"]))
        update = hass.config_entries.async_update_entry
        assert update.call_count == 1
        assert update.call_args.args[0] is second
        assert update.call_args.kwargs["options"]["tracking_numbers"] == [_item("C3")]

        update.reset_mock()
        await async_remove_tracking(hass, self._call(tracking_number=["A1", "C3"]))
        changed = {call.args[0].entry_id: call.kwargs["options"]["tracking_numbers"] for call in update.call_args_list}
        assert changed == {"first": [], "second": [_item("B2")]}

        # Nothing changes when one of the numbers isn't tracked anywhere
        update.reset_mock()
        with pytest.raises(ServiceValidationError, match="Z9 is not tracked"):
            await async_remove_tracking(hass, self._call(tracking_number=["A1", "Z9"]))
        update.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_tracking_given_entry(self):
        """With config_entry_id only that entry is searched."""
        from custom_components.greek_courier_tracker.services import async_remove_tracking

        hass = self._hass([_entry([_item("A1")], entry_id="first"), _entry([_item("B2")], entry_id="second")])
        with pytest.raises(ServiceValidationError):
            await async_remove_tracking(hass, self._call(tracking_number=["B2"], config_entry_id="first"))
        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_owner_finds_entry(self):
        """set_owner changes the number in the entry that tracks it."""
        from custom_components.greek_courier_tracker.services import async_set_owner

        first = _entry([_item("A1")], entry_id="first")
        second = _entry([_item("B2")], entry_id="second")
        hass = self._hass([first, second])

        await async_set_owner(hass, self._call(tracking_number=["B2"], owner="person.maria"))
        update = hass.config_entries.async_update_entry
        assert update.call_count == 1
        assert update.call_args.args[0] is second
        assert update.call_args.kwargs["options"]["tracking_numbers"] == [_item("B2", owner="u2")]

        update.reset_mock()
        with pytest.raises(ServiceValidationError):
            await async_set_owner(hass, self._call(tracking_number=["Z9"], owner="person.maria"))
        update.assert_not_called()

    def test_schemas(self):
        """The courier must be a known code and the number list is normalized."""
        import voluptuous as vol

        from custom_components.greek_courier_tracker.services import (
            ADD_TRACKING_SCHEMA,
            REMOVE_TRACKING_SCHEMA,
            SET_OWNER_SCHEMA,
        )

        assert ADD_TRACKING_SCHEMA({"tracking_number": "A1"})["courier"] == "auto"
        assert ADD_TRACKING_SCHEMA({"tracking_number": "A1", "courier": "skroutz"})["courier"] == "skroutz"
        with pytest.raises(vol.Invalid):
            ADD_TRACKING_SCHEMA({"tracking_number": "A1", "courier": "dhl"})
        assert REMOVE_TRACKING_SCHEMA({"tracking_number": "A1"})["tracking_number"] == ["A1"]
        assert "owner" not in ADD_TRACKING_SCHEMA({"tracking_number": "A1"})
        assert ADD_TRACKING_SCHEMA({"tracking_number": "A1", "owner": None})["owner"] is None
        assert SET_OWNER_SCHEMA({"tracking_number": "A1", "owner": "person.maria"})["tracking_number"] == ["A1"]


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
    async def test_create_item_owner(self):
        """The user who adds the item owns the shipment."""
        todo = self._todo(_entry())
        todo.async_set_context(Context(user_id="u2"))

        await todo.async_create_todo_item(TodoItem(summary="B2"))

        options = todo.hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert options["tracking_numbers"][-1] == _item("B2", owner="u2")

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

        flow = GreekCourierTrackerOptionsFlow(_entry(tracking_numbers))
        flow.hass = _people_hass()
        return flow

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
            "tracking_number": "B2", "name": "Box", "stop_tracking_delivered": True, "courier": "acs", "owner": None,
        }

    @staticmethod
    def _suggested(result, field):
        key = next(key for key in result["data_schema"].schema if key == field)
        return (key.description or {}).get("suggested_value")

    @pytest.mark.asyncio
    async def test_add_owner(self):
        """The form suggests the signed-in user; the picked owner is saved."""
        flow = self._flow([])

        with patch("custom_components.greek_courier_tracker.config_flow.request_user_id", return_value="u1"):
            result = await flow.async_step_add_tracking()
        assert self._suggested(result, "owner") == "u1"
        owner_selector = next(value for key, value in result["data_schema"].schema.items() if key == "owner")
        assert [option["label"] for option in owner_selector.config["options"]] == ["Athanasios", "Maria"]

        result = await flow.async_step_add_tracking(
            {"tracking_number": "B2", "name": "", "courier": "auto", "owner": "u2", "stop_tracking_delivered": False}
        )
        assert result["data"]["tracking_numbers"][-1]["owner"] == "u2"

    @pytest.mark.asyncio
    async def test_add_without_owner_is_shared(self):
        """Clearing the owner field makes a shared shipment."""
        result = await self._flow([]).async_step_add_tracking(
            {"tracking_number": "B2", "name": "", "courier": "auto", "stop_tracking_delivered": False}
        )
        assert result["data"]["tracking_numbers"][-1]["owner"] is None

    @pytest.mark.asyncio
    async def test_edit_owner(self):
        """The edit form shows the owner, which can be changed or cleared."""
        flow = self._flow([_item("A1", owner="u1")])

        result = await flow.async_step_edit_select({"tracking_number": "A1"})
        assert self._suggested(result, "owner") == "u1"

        result = await flow.async_step_edit_tracking(
            {"name": "A1", "courier": "auto", "owner": "u2", "stop_tracking_delivered": False}
        )
        assert result["data"]["tracking_numbers"][0]["owner"] == "u2"

        flow = self._flow([_item("A1", owner="u1")])
        await flow.async_step_edit_select({"tracking_number": "A1"})
        result = await flow.async_step_edit_tracking({"name": "A1", "courier": "auto", "stop_tracking_delivered": False})
        assert result["data"]["tracking_numbers"][0]["owner"] is None

    @pytest.mark.asyncio
    async def test_menu_shows_owner(self):
        """The list of shipments names their owners."""
        result = await self._flow([_item("A1", "Shoes", owner="u2"), _item("B2")]).async_step_init()
        assert "• Shoes (A1) · Auto-detect (try all) · Maria" in result["description_placeholders"]["tracking_list"]

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


class TestMergeEntries:
    """Entries left over from older versions are merged into the first one."""

    @staticmethod
    def _entry(entry_id, items, source="user", disabled_by=None, **options):
        entry = _entry(items, entry_id=entry_id)
        entry.options = {**entry.options, **options}
        entry.source = source
        entry.disabled_by = disabled_by
        return entry

    @staticmethod
    def _registry_entry(entry_id, suffix, domain="sensor"):
        unique_id = f"{entry_id}_{suffix}"
        return SimpleNamespace(
            entity_id=f"{domain}.{unique_id.lower()}", domain=domain, unique_id=unique_id, config_entry_id=entry_id,
        )

    @staticmethod
    async def _merge(entries, registry_entries=()):
        from custom_components.greek_courier_tracker import _async_merge_entries

        order = []
        hass = MagicMock()
        hass.config_entries.async_entries.return_value = entries
        hass.config_entries.async_remove = AsyncMock(side_effect=order.append)
        registry = MagicMock()
        registry.async_update_entity.side_effect = lambda entity_id, **changes: order.append(entity_id)
        device_registry = MagicMock()
        device_registry.async_get_device.return_value = SimpleNamespace(id="device_first")

        with patch("custom_components.greek_courier_tracker.er.async_get", return_value=registry), patch(
            "custom_components.greek_courier_tracker.er.async_entries_for_config_entry",
            side_effect=lambda _, entry_id: [item for item in registry_entries if item.config_entry_id == entry_id],
        ), patch("custom_components.greek_courier_tracker.dr.async_get", return_value=device_registry):
            await _async_merge_entries(hass)

        device_registry.async_get_device.assert_called_with(identifiers={("greek_courier_tracker", "first")})
        return hass, registry, order

    @pytest.mark.asyncio
    async def test_merge(self):
        """Shipments, settings and sensors move to the first entry; the others are removed."""
        entries = [
            self._entry("first", [_item("A1", "Shoes")]),
            self._entry("second", [_item("B2"), _item("A1")], scan_interval=1, auto_remove_delivered=5),
            self._entry("third", [_item("C3", owner="u1"), _item("B2")]),
        ]
        registry_entries = [
            self._registry_entry("first", "A1"),
            self._registry_entry("first", "shipments", "todo"),
            self._registry_entry("second", "B2"),
            self._registry_entry("second", "A1"),
            self._registry_entry("second", "shipments", "todo"),
            self._registry_entry("third", "C3"),
            self._registry_entry("third", "B2"),
            self._registry_entry("third", "shipments", "todo"),
        ]

        hass, registry, order = await self._merge(entries, registry_entries)

        update = hass.config_entries.async_update_entry
        update.assert_called_once()
        assert update.call_args.args[0] is entries[0]
        assert update.call_args.kwargs["options"] == {
            "tracking_numbers": [_item("A1", "Shoes"), _item("B2"), _item("C3", owner="u1")],
            "scan_interval": 2,
            "auto_remove_delivered": 5,
        }

        # Only the sensors of moved numbers switch entry (duplicates and to-do lists go with their entry),
        # and before the entries are removed
        assert order == ["sensor.second_b2", "sensor.third_c3", "second", "third"]
        assert registry.async_update_entity.call_args_list[0].kwargs == {
            "config_entry_id": "first", "device_id": "device_first", "new_unique_id": "first_B2",
        }
        assert registry.async_update_entity.call_args_list[1].kwargs["new_unique_id"] == "first_C3"

    @pytest.mark.asyncio
    async def test_nothing_to_merge(self):
        """One entry, plus disabled or ignored ones, is left alone."""
        from custom_components.greek_courier_tracker import _async_merge_entries

        hass = MagicMock()
        hass.config_entries.async_entries.return_value = [
            self._entry("first", [_item("A1")]),
            self._entry("second", [_item("B2")], disabled_by="user"),
            self._entry("third", [_item("C3")], source="ignore"),
        ]
        hass.config_entries.async_remove = AsyncMock()

        await _async_merge_entries(hass)

        hass.config_entries.async_update_entry.assert_not_called()
        hass.config_entries.async_remove.assert_not_awaited()


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

    def test_services_are_described(self):
        """Every registered action is in services.yaml and the translations."""
        import json

        import yaml

        from custom_components.greek_courier_tracker import services as module

        registered = {module.SERVICE_ADD_TRACKING, module.SERVICE_REMOVE_TRACKING, module.SERVICE_SET_OWNER}
        described = yaml.safe_load((COMPONENT_DIR / "services.yaml").read_text(encoding="utf-8"))
        strings = json.loads((COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))["services"]
        assert set(described) == registered
        assert set(strings) == registered
        for service, spec in described.items():
            assert set(spec["fields"]) == set(strings[service]["fields"]), service

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

    def test_sensor_owner(self):
        """The sensor shows the owner and follows owner changes."""
        from custom_components.greek_courier_tracker.sensor import GreekCourierTrackingSensor

        coordinator = MagicMock()
        coordinator.data = {"A1": _result("A1")}
        sensor = GreekCourierTrackingSensor(coordinator, _entry(), "A1", "Shoes", owner="u1")
        sensor.hass = _people_hass()
        sensor.async_write_ha_state = MagicMock()
        assert sensor.extra_state_attributes["owner_user_id"] == "u1"
        assert sensor.extra_state_attributes["owner"] == "Athanasios"

        sensor._async_config_changed({"A1": _item("A1", "Shoes", owner="u2")})
        assert sensor.extra_state_attributes["owner"] == "Maria"

        sensor._async_config_changed({"A1": _item("A1", "Shoes")})
        assert sensor.extra_state_attributes["owner_user_id"] is None
        assert sensor.extra_state_attributes["owner"] is None


class TestOptionsFlowSavesChanges:
    """The options flow must not change the entry's options in place."""

    @staticmethod
    def _flow_and_entry():
        from types import MappingProxyType

        from custom_components.greek_courier_tracker.config_flow import GreekCourierTrackerOptionsFlow

        entry = _entry([_item("A1"), {"tracking_number": "B2", "name": "B2", "stop_tracking_delivered": False}])
        entry.options = MappingProxyType(dict(entry.options))
        flow = GreekCourierTrackerOptionsFlow(entry)
        flow.hass = _people_hass()
        return flow, entry

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

    def test_event_owner(self):
        """The event names the owner and their phones; shared shipments have none."""
        from custom_components.greek_courier_tracker import GreekCourierDataUpdateCoordinator

        hass = _people_hass()
        hass.config.language = "en"
        items = [_item("A1", "Shoes", owner="u2"), _item("B2")]
        coordinator = GreekCourierDataUpdateCoordinator(
            hass=hass,
            tracking_numbers=["A1", "B2"],
            tracking_configs={item["tracking_number"]: item for item in items},
            scan_interval=1,
        )

        with patch(
            "custom_components.greek_courier_tracker.owner_device_ids", return_value=["maria_phone"]
        ) as devices:
            coordinator._fire_status_events(
                {"A1": _result("A1"), "B2": _result("B2")},
                {"A1": _result("A1", "delivered", "Delivered"), "B2": _result("B2", "delivered", "Delivered")},
            )

        devices.assert_called_once_with(hass, "u2")
        owned, shared = (call.args[1] for call in hass.bus.async_fire.call_args_list)
        assert owned["owner_user_id"] == "u2"
        assert owned["owner"] == "Maria"
        assert owned["owner_device_ids"] == ["maria_phone"]
        assert shared["owner_user_id"] is None
        assert shared["owner"] is None
        assert shared["owner_device_ids"] is None

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


class TestOwners:
    """Owners of shipments and their phones."""

    def test_owner_name(self):
        """The name comes from the person linked to the user."""
        from custom_components.greek_courier_tracker.owners import owner_name

        hass = _people_hass()
        assert owner_name(hass, "u2") == "Maria"
        assert owner_name(hass, "unknown") is None
        assert owner_name(hass, None) is None

    def test_owner_device_ids(self):
        """A phone belongs to the user signed in to the Companion app on it."""
        from custom_components.greek_courier_tracker.owners import owner_device_ids

        hass = MagicMock()
        hass.config_entries.async_entries.return_value = [
            SimpleNamespace(entry_id="app1", data={"user_id": "u1"}),
            SimpleNamespace(entry_id="app2", data={"user_id": "u2"}),
            SimpleNamespace(entry_id="app3", data={"user_id": "u2"}),
        ]
        devices = {"app1": ["phone1"], "app2": ["phone2"], "app3": ["tablet2"]}

        with patch("custom_components.greek_courier_tracker.owners.dr.async_get"), patch(
            "custom_components.greek_courier_tracker.owners.dr.async_entries_for_config_entry",
            side_effect=lambda registry, entry_id: [SimpleNamespace(id=device) for device in devices[entry_id]],
        ):
            assert owner_device_ids(hass, "u2") == ["phone2", "tablet2"]
            assert owner_device_ids(hass, "u3") == []

        hass.config_entries.async_entries.assert_called_with("mobile_app")

    @pytest.mark.asyncio
    async def test_owner_options(self):
        """Active, non-system users can own shipments, sorted by name."""
        from custom_components.greek_courier_tracker.owners import async_owner_options

        assert await async_owner_options(_people_hass()) == [
            {"value": "u1", "label": "Athanasios"},
            {"value": "u2", "label": "Maria"},
        ]

    def test_request_user_id(self):
        """Forms in Settings know who is filling them in."""
        from custom_components.greek_courier_tracker.owners import current_request, request_user_id

        assert request_user_id() is None
        token = current_request.set({"hass_user": SimpleNamespace(id="u1")})
        try:
            assert request_user_id() == "u1"
        finally:
            current_request.reset(token)


class TestBlueprint:
    """The notification blueprint is valid for Home Assistant."""

    PATH = Path(__file__).parent.parent / "blueprints" / "automation" / "greek_courier_tracker" / (
        "shipment_status_notification.yaml"
    )

    def test_blueprint_is_valid(self):
        from homeassistant.components.blueprint.models import Blueprint
        from homeassistant.util.yaml.loader import load_yaml

        path = self.PATH
        try:
            from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA

            blueprint = Blueprint(load_yaml(str(path)), expected_domain="automation", schema=BLUEPRINT_SCHEMA)
        except (ImportError, TypeError):
            # Older Home Assistant validates without a schema argument
            blueprint = Blueprint(load_yaml(str(path)), expected_domain="automation")
        assert set(blueprint.inputs) == {"notify_device", "only_own", "only_delivered"}
        assert blueprint.inputs["notify_device"]["selector"]["device"]["multiple"] is True

    @pytest.mark.parametrize("phones,only_own,data,expected", [
        # Every phone, unless only their own shipments are wanted
        (["a", "b"], False, {"owner_device_ids": ["a"]}, ["a", "b"]),
        (["a", "b"], True, {"owner_device_ids": ["a"]}, ["a"]),
        # Shared shipments go to every phone, as do events of older versions
        (["a", "b"], True, {"owner_device_ids": None}, ["a", "b"]),
        (["a", "b"], True, {}, ["a", "b"]),
        # The owner has no phone among the selected ones
        (["a", "b"], True, {"owner_device_ids": ["c"]}, []),
        # Automations made when only one phone could be picked
        ("a", False, {"owner_device_ids": None}, ["a"]),
        ("a", True, {"owner_device_ids": ["b"]}, []),
    ])
    def test_targets(self, phones, only_own, data, expected):
        """The phones that get a notification."""
        import ast

        import jinja2
        from homeassistant.util.yaml.loader import load_yaml

        template = load_yaml(str(self.PATH))["variables"]["targets"]
        rendered = jinja2.Environment().from_string(template).render(
            phones=phones, only_own=only_own, trigger={"event": {"data": data}}
        )
        assert ast.literal_eval(rendered.strip()) == expected
