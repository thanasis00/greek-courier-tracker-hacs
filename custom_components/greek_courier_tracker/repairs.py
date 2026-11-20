"""Repairs: fixes the integration offers in Settings → Repairs."""

from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant

from .blueprint_update import ISSUE_ID, async_update_blueprints


class BlueprintUpdateFlow(ConfirmRepairFlow):
    """Show what changed in the blueprint and update it on confirm."""

    async def async_step_confirm(self, user_input: dict[str, str] | None = None) -> Any:
        if user_input is not None:
            await async_update_blueprints(self.hass)
            return self.async_create_entry(data={})
        return await super().async_step_confirm()


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the fix flow of an issue."""
    if issue_id == ISSUE_ID:
        return BlueprintUpdateFlow()
    return ConfirmRepairFlow()
