"""Repairs flow for Entity Finder."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant

from .config_flow import get_enable_bulk_fix
from .const import DOMAIN
from .manager import EntityFinderManager
from .replacer import async_apply_replace, async_preview_replace
from .util import format_references_for_repair


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create a repair flow."""
    return StaleReferencesRepairFlow(hass, issue_id, data or {})


class StaleReferencesRepairFlow(RepairsFlow):
    """Repair flow for stale entity references after an entity ID change."""

    def __init__(
        self,
        hass: HomeAssistant,
        issue_id: str,
        data: dict[str, str | int | float | None],
    ) -> None:
        """Initialize repair flow."""
        self._hass = hass
        self._issue_id = issue_id
        self._data = data
        self._old_entity_id = str(data.get("old_entity_id", ""))
        self._new_entity_id = str(data.get("new_entity_id", ""))
        self._preview = ""
        self._hits = []

    def _get_manager(self) -> EntityFinderManager | None:
        """Return the active manager."""
        for entry in self._hass.config_entries.async_entries(DOMAIN):
            manager = entry.runtime_data
            if isinstance(manager, EntityFinderManager):
                return manager
        return None

    def _placeholders(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Build translation placeholders."""
        manager = self._get_manager()
        hits = manager.get_hits_for_old_entity(self._old_entity_id) if manager else []
        references, manual_note = format_references_for_repair(hits)
        bulk_fix_hint = ""
        for entry in self._hass.config_entries.async_entries(DOMAIN):
            if not get_enable_bulk_fix(self._hass, entry):
                bulk_fix_hint = "_(Auto-Replace is disabled in integration settings.)_\n\n"
            break
        placeholders = {
            "old_entity_id": self._old_entity_id,
            "new_entity_id": self._new_entity_id,
            "references": references,
            "manual_note": f"{manual_note}\n\n" if manual_note else "",
            "bulk_fix_hint": bulk_fix_hint,
        }
        if extra:
            placeholders.update(extra)
        return placeholders

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Choose Ignore or Auto-Replace."""
        return await self.async_step_choose_action(user_input)

    async def async_step_choose_action(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Present repair actions."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "ignore":
                return await self.async_step_ignore()
            if action == "auto_replace":
                entry = next(
                    (
                        item
                        for item in self._hass.config_entries.async_entries(DOMAIN)
                    ),
                    None,
                )
                if entry is None or not get_enable_bulk_fix(self._hass, entry):
                    return await self.async_step_auto_replace_disabled()
                return await self.async_step_preview()

        return self.async_show_form(
            step_id="choose_action",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): vol.In(
                        {"ignore": "Ignore", "auto_replace": "Auto-Replace"}
                    )
                }
            ),
            description_placeholders=self._placeholders(),
        )

    async def async_step_ignore(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Ignore this stale entity ID change."""
        manager = self._get_manager()
        if manager is not None:
            await manager.async_ignore(self._old_entity_id)
        return self.async_create_entry(title="", data={})

    async def async_step_auto_replace_disabled(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Explain that Auto-Replace is disabled."""
        if user_input is not None:
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="auto_replace_disabled",
            data_schema=vol.Schema({}),
            description_placeholders=self._placeholders(),
        )

    async def async_step_preview(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Preview Auto-Replace changes."""
        manager = self._get_manager()
        if manager is None:
            return self.async_abort(reason="not_loaded")

        hits = manager.get_hits_for_old_entity(self._old_entity_id)
        preview, _unique = await async_preview_replace(
            self._hass, hits, self._old_entity_id, self._new_entity_id
        )
        self._preview = preview
        self._hits = hits

        if user_input is not None:
            return await self.async_step_apply()

        return self.async_show_form(
            step_id="preview",
            data_schema=vol.Schema({}),
            description_placeholders=self._placeholders({"preview": preview}),
        )

    async def async_step_apply(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Apply Auto-Replace."""
        result = await async_apply_replace(
            self._hass,
            self._hits,
            self._old_entity_id,
            self._new_entity_id,
        )
        manager = self._get_manager()
        if manager is not None:
            await manager.async_trigger_rescan()
        return await self.async_step_result(result.summary())

    async def async_step_result(
        self, summary: str, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Show Auto-Replace result."""
        if user_input is not None:
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="result",
            data_schema=vol.Schema({}),
            description_placeholders=self._placeholders({"result_summary": summary}),
        )
