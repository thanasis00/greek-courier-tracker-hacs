"""Keep the notification blueprint people imported up to date.

The blueprint ships with the integration (blueprints/ in this package, a copy of
the one at the root of the repository). People import it from GitHub once and
Home Assistant keeps their copy as it was. After every start the integration
looks for imported copies (by their source_url) older than the bundled one and
raises a Repairs issue that lists what changed. Its fix replaces those copies and
reloads the automations that use them, as "Re-import blueprint" does.

The version is the "Version N." line at the end of the blueprint description:
Home Assistant keeps the description when it saves a blueprint, and allows no
other field for it. Versions from before that line are told apart by their inputs.
"""

from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util.yaml import load_yaml

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

BUNDLED_BLUEPRINT = Path(__file__).parent / "blueprints" / "shipment_status_notification.yaml"
BLUEPRINT_FILENAME = "shipment_status_notification.yaml"
REPOSITORY = "thanasis00/greek-courier-tracker-hacs"
ISSUE_ID = "blueprint_outdated"
VERSION_LINE = re.compile(r"\bVersion (\d+)\.")

# Versions without the "Version N." line, by their inputs
LEGACY_VERSIONS: dict[frozenset[str], int] = {
    frozenset({"notify_device", "only_delivered"}): 1,
    frozenset({"notify_device", "only_own", "only_delivered"}): 2,
}

# What each version brought, for the Repairs issue (add one with every new version)
CHANGES: dict[int, dict[str, list[str]]] = {
    2: {
        "en": [
            "Notify several phones from one automation.",
            "New option “Only their own shipments”: each phone gets only the shipments of "
            "the person signed in to the Companion app on it.",
        ],
        "el": [
            "Ειδοποίηση σε πολλά κινητά από έναν αυτοματισμό.",
            "Νέα επιλογή «Only their own shipments»: κάθε κινητό παίρνει μόνο τις αποστολές "
            "του ατόμου που είναι συνδεδεμένο στην εφαρμογή Companion.",
        ],
    },
    3: {
        "en": [
            "New option “Also when something goes wrong” (on): even with “Only when delivered”, "
            "you hear about a failed delivery attempt, a return, a cancellation or a changed delivery.",
            "When something goes wrong, the message starts with ⚠️ and what happened.",
        ],
        "el": [
            "Νέα επιλογή «Also when something goes wrong» (ενεργή): ακόμα και με «Only when delivered» "
            "μαθαίνεις για αποτυχημένη απόπειρα παράδοσης, επιστροφή, ακύρωση ή αλλαγή παράδοσης.",
            "Όταν κάτι πάει στραβά, το μήνυμα ξεκινά με ⚠️ και τι έγινε.",
        ],
    },
}


@dataclass
class ImportedCopy:
    """A copy of the blueprint in the configuration."""

    path: str  # relative to blueprints/automation, as Home Assistant names it
    version: int  # 0 when unknown
    source_url: str


def blueprint_version(data: dict[str, Any]) -> int:
    """Version of a blueprint (0 when it can't be told)."""
    metadata = data.get("blueprint") or {}
    match = VERSION_LINE.search(str(metadata.get("description") or ""))
    if match:
        return int(match.group(1))
    return LEGACY_VERSIONS.get(frozenset(metadata.get("input") or {}), 0)


def is_our_blueprint(data: Any) -> bool:
    """Whether a blueprint was imported from this repository."""
    if not isinstance(data, dict):
        return False
    source_url = str((data.get("blueprint") or {}).get("source_url") or "")
    return REPOSITORY in source_url and source_url.endswith(BLUEPRINT_FILENAME)


def find_imported_copies(folder: Path) -> list[ImportedCopy]:
    """Find the copies of the blueprint under blueprints/automation (blocking)."""
    copies = []
    if not folder.is_dir():
        return copies
    for file in sorted(folder.rglob("*.yaml")):
        try:
            data = load_yaml(str(file))
        except Exception:  # someone else's broken blueprint is not our business
            continue
        if is_our_blueprint(data):
            copies.append(
                ImportedCopy(
                    path=file.relative_to(folder).as_posix(),
                    version=blueprint_version(data),
                    source_url=str(data["blueprint"]["source_url"]),
                )
            )
    return copies


def changes_since(version: int, language: str | None) -> str:
    """The changes after a version, as a Markdown list in Greek or English."""
    lang = "el" if (language or "").lower().startswith("el") else "en"
    return "\n".join(
        f"- {line}"
        for number, texts in sorted(CHANGES.items())
        if number > version
        for line in texts[lang]
    )


def _load_bundled() -> dict[str, Any]:
    return load_yaml(str(BUNDLED_BLUEPRINT))


def _automation_folder(hass: HomeAssistant) -> Path:
    return Path(hass.config.path("blueprints", "automation"))


async def _async_outdated(hass: HomeAssistant) -> tuple[int, list[ImportedCopy]]:
    """The bundled version and the copies older than it."""
    bundled = await hass.async_add_executor_job(_load_bundled)
    version = blueprint_version(bundled)
    copies = await hass.async_add_executor_job(find_imported_copies, _automation_folder(hass))
    return version, [item for item in copies if item.version < version]


async def async_check_blueprint(hass: HomeAssistant) -> None:
    """Raise (or clear) the Repairs issue about an outdated blueprint."""
    try:
        version, outdated = await _async_outdated(hass)
    except Exception as err:
        _LOGGER.warning("Could not check the notification blueprint: %s", err)
        return

    if not outdated:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
        return

    oldest = min(item.version for item in outdated)
    _LOGGER.info(
        "The notification blueprint has version %s, imported copies are older: %s",
        version, [item.path for item in outdated],
    )
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_ID,
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_ID,
        translation_placeholders={
            "version": str(version),
            "files": ", ".join(f"`{item.path}`" for item in outdated),
            "changes": changes_since(oldest, getattr(hass.config, "language", None)),
        },
    )


def _blueprint(data: dict[str, Any], source_url: str) -> Any:
    """A Home Assistant blueprint of the bundled data, keeping the copy's source_url."""
    from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
    from homeassistant.components.blueprint import Blueprint

    data = copy.deepcopy(data)
    try:
        blueprint = Blueprint(data, expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)
    except TypeError:  # older Home Assistant, without the schema argument
        blueprint = Blueprint(data, expected_domain="automation")
    blueprint.update_metadata(source_url=source_url)
    return blueprint


async def async_update_blueprints(hass: HomeAssistant) -> list[str]:
    """Replace the outdated copies with the bundled blueprint; return their paths."""
    from homeassistant.components.automation.helpers import async_get_blueprints

    _version, outdated = await _async_outdated(hass)
    bundled = await hass.async_add_executor_job(_load_bundled)
    domain_blueprints = async_get_blueprints(hass)
    reload_needed = False

    for item in outdated:
        blueprint = _blueprint(bundled, item.source_url)
        try:
            # Also reloads the automations that use it
            await domain_blueprints.async_add_blueprint(blueprint, item.path, allow_override=True)
        except TypeError:  # older Home Assistant: write the file ourselves
            target = _automation_folder(hass) / item.path
            await hass.async_add_executor_job(target.write_text, blueprint.yaml(), "utf-8")
            reload_needed = True
        _LOGGER.info("Updated the notification blueprint %s", item.path)

    if reload_needed:
        await domain_blueprints.async_reset_cache()
        await hass.services.async_call("automation", "reload", blocking=True)

    ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
    return [item.path for item in outdated]
