"""Repairs flow for Lost Entity Find And Replace."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .config_flow import get_enable_bulk_fix
from .const import DOMAIN
from .manager import EntityFinderManager
from .models import ReferenceHit
from .replacer import async_apply_replace, async_preview_replace
from .scanner import async_scan_tracked_references
from .util import format_references_for_repair, has_auto_replaceable_hits


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
        self._allow_ignore = bool(int(data.get("allow_ignore", 1)))
        self._preview = ""
        self._result_summary = ""
        self._hits = []

    def _get_manager(self) -> EntityFinderManager | None:
        """Return the active manager."""
        for entry in self._hass.config_entries.async_entries(DOMAIN):
            manager = entry.runtime_data
            if isinstance(manager, EntityFinderManager):
                return manager
        return None

    def _bulk_fix_enabled(self) -> bool:
        """Return whether Auto-Replace is enabled in integration settings."""
        for entry in self._hass.config_entries.async_entries(DOMAIN):
            return get_enable_bulk_fix(self._hass, entry)
        return False

    def _can_offer_auto_replace(self, hits: list[ReferenceHit]) -> bool:
        """Return True when Auto-Replace can change at least one reference."""
        return self._bulk_fix_enabled() and has_auto_replaceable_hits(hits)

    async def _async_get_hits(self) -> list[ReferenceHit]:
        """Return current reference hits for this repair."""
        manager = self._get_manager()
        hits = manager.get_hits_for_old_entity(self._old_entity_id) if manager else []
        if not hits:
            hits = (
                await async_scan_tracked_references(self._hass, {self._old_entity_id})
            ).get(self._old_entity_id, [])
        return hits

    def _placeholders(
        self,
        hits: list[ReferenceHit] | None = None,
        extra: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Build translation placeholders."""
        if hits is None:
            manager = self._get_manager()
            hits = (
                manager.get_hits_for_old_entity(self._old_entity_id) if manager else []
            )
        references, manual_note = format_references_for_repair(hits)
        bulk_fix_hint = ""
        if has_auto_replaceable_hits(hits) and not self._bulk_fix_enabled():
            bulk_fix_hint = "_(Auto-Replace is disabled in integration settings.)_\n\n"
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
        """Choose Ignore/Auto-Replace, or force Auto-Replace only."""
        if not self._allow_ignore:
            self._hits = await self._async_get_hits()
            if self._can_offer_auto_replace(self._hits):
                return await self.async_step_preview()
            if has_auto_replaceable_hits(self._hits) and not self._bulk_fix_enabled():
                return await self.async_step_auto_replace_disabled()
            return await self.async_step_manual_only()
        return await self.async_step_choose_action(user_input)

    async def async_step_choose_action(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Present repair actions."""
        self._hits = await self._async_get_hits()

        if user_input is not None:
            action = user_input.get("action")
            if action == "ignore":
                return await self.async_step_ignore()
            if action == "auto_replace":
                if not self._can_offer_auto_replace(self._hits):
                    return await self.async_step_manual_only()
                return await self.async_step_preview()

        actions: dict[str, str] = {"ignore": "Ignore"}
        if self._can_offer_auto_replace(self._hits):
            actions["auto_replace"] = "Auto-Replace"

        return self.async_show_form(
            step_id="choose_action",
            data_schema=vol.Schema({vol.Required("action"): vol.In(actions)}),
            description_placeholders=self._placeholders(self._hits),
        )

    async def async_step_manual_only(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Show manual-only guidance when nothing can be auto-replaced."""
        if user_input is not None:
            return self.async_create_entry(title="", data={})

        if not self._hits:
            self._hits = await self._async_get_hits()

        return self.async_show_form(
            step_id="manual_only",
            data_schema=vol.Schema({}),
            description_placeholders=self._placeholders(self._hits),
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
            description_placeholders=self._placeholders(
                await self._async_get_hits()
            ),
        )

    async def async_step_preview(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Preview Auto-Replace changes."""
        if not self._hits:
            self._hits = await self._async_get_hits()

        if not self._can_offer_auto_replace(self._hits):
            return await self.async_step_manual_only()

        preview, _unique = await async_preview_replace(
            self._hass, self._hits, self._old_entity_id, self._new_entity_id
        )
        self._preview = preview

        if not self._hits:
            self._result_summary = "No references found to update for this repair."
            ir.async_delete_issue(self._hass, DOMAIN, self._issue_id)
            return await self.async_step_result()

        if user_input is not None:
            return await self.async_step_apply()

        return self.async_show_form(
            step_id="preview",
            data_schema=vol.Schema({}),
            description_placeholders=self._placeholders(
                self._hits, {"preview": preview}
            ),
        )

    async def async_step_apply(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Apply Auto-Replace."""
        if not self._hits:
            self._result_summary = "No references found to update for this repair."
            ir.async_delete_issue(self._hass, DOMAIN, self._issue_id)
            return await self.async_step_result()

        result = await async_apply_replace(
            self._hass,
            self._hits,
            self._old_entity_id,
            self._new_entity_id,
        )
        self._result_summary = result.summary()
        manager = self._get_manager()
        if manager is not None:
            await manager.async_trigger_rescan()
        ir.async_delete_issue(self._hass, DOMAIN, self._issue_id)
        return await self.async_step_result()

    async def async_step_result(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Show Auto-Replace result."""
        if user_input is not None:
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="result",
            data_schema=vol.Schema({}),
            description_placeholders=self._placeholders(
                {"result_summary": self._result_summary}
            ),
        )
