"""Tests for keeping the imported notification blueprint up to date."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.greek_courier_tracker import blueprint_update
from custom_components.greek_courier_tracker.blueprint_update import (
    BUNDLED_BLUEPRINT,
    CHANGES,
    ISSUE_ID,
    async_check_blueprint,
    async_update_blueprints,
    blueprint_version,
    changes_since,
    find_imported_copies,
)
from custom_components.greek_courier_tracker.repairs import BlueprintUpdateFlow, async_create_fix_flow

ROOT_BLUEPRINT = (
    Path(__file__).parent.parent / "blueprints" / "automation" / "greek_courier_tracker"
    / "shipment_status_notification.yaml"
)
SOURCE_URL = (
    "https://github.com/thanasis00/greek-courier-tracker-hacs/blob/main/blueprints/automation/"
    "greek_courier_tracker/shipment_status_notification.yaml"
)

# Version 2, as Home Assistant saved it when it was imported
VERSION_2 = f"""blueprint:
  name: Greek Courier Tracker - shipment updates
  description: Sends a notification to your phones.
  domain: automation
  source_url: {SOURCE_URL}
  input:
    notify_device:
      selector:
        device:
          integration: mobile_app
          multiple: true
    only_own:
      default: false
      selector:
        boolean: {{}}
    only_delivered:
      default: false
      selector:
        boolean: {{}}
trigger:
- platform: event
  event_type: greek_courier_tracker_status_changed
variables:
  only_own: !input only_own
  only_delivered: !input only_delivered
  phones: !input notify_device
action: []
"""

SOMEONE_ELSES = """blueprint:
  name: Motion light
  domain: automation
  source_url: https://github.com/home-assistant/core/blob/dev/motion_light.yaml
  input: {}
trigger: []
action: []
"""


def _hass(config_dir: Path, language="el"):
    hass = MagicMock()
    hass.config.path = lambda *parts: str(config_dir.joinpath(*parts))
    hass.config.language = language

    async def run(func, *args):
        return func(*args)

    hass.async_add_executor_job = run
    hass.services.async_call = AsyncMock()
    return hass


def _write(config_dir: Path, path: str, text: str) -> Path:
    file = config_dir / "blueprints" / "automation" / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
    return file


class TestVersions:
    def test_bundled_blueprint_is_the_published_one(self):
        """The package carries the same blueprint as the import link."""
        assert BUNDLED_BLUEPRINT.read_text(encoding="utf-8") == ROOT_BLUEPRINT.read_text(encoding="utf-8")

    def test_bundled_version_has_its_changes(self):
        """A new version needs its "Version N." line and its entry in CHANGES."""
        from homeassistant.util.yaml import load_yaml

        version = blueprint_version(load_yaml(str(BUNDLED_BLUEPRINT)))
        assert version == max(CHANGES)
        assert all(set(texts) == {"en", "el"} for texts in CHANGES.values())

    @pytest.mark.parametrize(
        ("description", "inputs", "expected"),
        [
            ("Sends a notification. Version 7.", ["notify_device"], 7),
            ("Sends a notification.", ["notify_device", "only_delivered"], 1),
            ("Sends a notification.", ["notify_device", "only_own", "only_delivered"], 2),
            ("Edited by hand.", ["something_else"], 0),
        ],
    )
    def test_blueprint_version(self, description, inputs, expected):
        data = {"blueprint": {"description": description, "input": {name: {} for name in inputs}}}
        assert blueprint_version(data) == expected

    def test_changes_since(self):
        assert changes_since(2, "el") == "\n".join(f"- {line}" for line in CHANGES[3]["el"])
        assert changes_since(0, "en").count("\n- ") == len(CHANGES[2]["en"]) + len(CHANGES[3]["en"]) - 1
        assert changes_since(max(CHANGES), "en") == ""


class TestFindCopies:
    def test_only_our_blueprints(self, tmp_path):
        _write(tmp_path, "thanasis00/shipment_status_notification.yaml", VERSION_2)
        _write(tmp_path, "homeassistant/motion_light.yaml", SOMEONE_ELSES)
        _write(tmp_path, "broken/broken.yaml", "blueprint: [")

        copies = find_imported_copies(tmp_path / "blueprints" / "automation")

        assert [(item.path, item.version, item.source_url) for item in copies] == [
            ("thanasis00/shipment_status_notification.yaml", 2, SOURCE_URL)
        ]

    def test_no_blueprints_folder(self, tmp_path):
        assert find_imported_copies(tmp_path / "missing") == []


@pytest.mark.asyncio
class TestRepairsIssue:
    async def test_issue_lists_the_changes(self, tmp_path):
        _write(tmp_path, "thanasis00/shipment_status_notification.yaml", VERSION_2)
        hass = _hass(tmp_path)

        with patch.object(blueprint_update.ir, "async_create_issue") as create:
            await async_check_blueprint(hass)

        kwargs = create.call_args.kwargs
        assert create.call_args.args[1:] == ("greek_courier_tracker", ISSUE_ID)
        assert kwargs["is_fixable"] is True
        assert kwargs["translation_placeholders"] == {
            "version": str(max(CHANGES)),
            "files": "`thanasis00/shipment_status_notification.yaml`",
            "changes": changes_since(2, "el"),
        }

    async def test_no_issue_when_up_to_date(self, tmp_path):
        _write(tmp_path, "thanasis00/shipment_status_notification.yaml", ROOT_BLUEPRINT.read_text(encoding="utf-8"))
        hass = _hass(tmp_path)

        with patch.object(blueprint_update.ir, "async_create_issue") as create, \
                patch.object(blueprint_update.ir, "async_delete_issue") as delete:
            await async_check_blueprint(hass)

        create.assert_not_called()
        delete.assert_called_once_with(hass, "greek_courier_tracker", ISSUE_ID)

    async def test_no_issue_without_an_imported_blueprint(self, tmp_path):
        hass = _hass(tmp_path)

        with patch.object(blueprint_update.ir, "async_create_issue") as create, \
                patch.object(blueprint_update.ir, "async_delete_issue"):
            await async_check_blueprint(hass)

        create.assert_not_called()

    async def test_fix_replaces_the_copy(self, tmp_path):
        _write(tmp_path, "thanasis00/shipment_status_notification.yaml", VERSION_2)
        hass = _hass(tmp_path)
        domain_blueprints = MagicMock(async_add_blueprint=AsyncMock(return_value=True))

        with patch(
            "homeassistant.components.automation.helpers.async_get_blueprints", return_value=domain_blueprints
        ), patch.object(blueprint_update.ir, "async_delete_issue") as delete:
            updated = await async_update_blueprints(hass)

        assert updated == ["thanasis00/shipment_status_notification.yaml"]
        blueprint, path = domain_blueprints.async_add_blueprint.await_args.args
        assert path == "thanasis00/shipment_status_notification.yaml"
        assert domain_blueprints.async_add_blueprint.await_args.kwargs == {"allow_override": True}
        assert blueprint_version(blueprint.data) == max(CHANGES)
        assert blueprint.metadata["source_url"] == SOURCE_URL
        delete.assert_called_once_with(hass, "greek_courier_tracker", ISSUE_ID)

    async def test_fix_on_older_home_assistant(self, tmp_path):
        """Without allow_override the file is written and the automations reloaded."""
        file = _write(tmp_path, "thanasis00/shipment_status_notification.yaml", VERSION_2)
        hass = _hass(tmp_path)
        domain_blueprints = MagicMock(
            async_add_blueprint=AsyncMock(side_effect=TypeError("unexpected keyword")),
            async_reset_cache=AsyncMock(),
        )

        with patch(
            "homeassistant.components.automation.helpers.async_get_blueprints", return_value=domain_blueprints
        ), patch.object(blueprint_update.ir, "async_delete_issue"):
            await async_update_blueprints(hass)

        assert "Version 3." in file.read_text(encoding="utf-8")
        hass.services.async_call.assert_awaited_once_with("automation", "reload", blocking=True)

    async def test_fix_flow(self):
        flow = await async_create_fix_flow(MagicMock(), ISSUE_ID, None)
        assert isinstance(flow, BlueprintUpdateFlow)
        flow.hass = MagicMock()

        with patch(
            "custom_components.greek_courier_tracker.repairs.async_update_blueprints", AsyncMock()
        ) as update:
            result = await flow.async_step_confirm({})

        update.assert_awaited_once_with(flow.hass)
        assert result["type"] == "create_entry"
