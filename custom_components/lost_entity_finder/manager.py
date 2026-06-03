"""Lost Entity Find And Replace manager - entity ID change tracking, scanning, and repairs."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components import automation, script
from homeassistant.components.homeassistant import scene
from homeassistant.components.lovelace.const import EVENT_LOVELACE_UPDATED
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_COMPONENT_LOADED, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_call_later

from .config_flow import get_enable_bulk_fix
from .const import DEBOUNCE_COOLDOWN, DOMAIN, TRANSLATION_KEY_LOST
from .models import ReferenceHit
from .scanner import async_scan_tracked_references
from .store import EntityFinderStore
from .util import format_references_for_repair, slugify_issue_id

_LOGGER = logging.getLogger(__name__)


class EntityFinderManager:
    """Coordinate entity ID change tracking, scanning, and repair issues."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize manager."""
        self.hass = hass
        self.entry = entry
        self.store = EntityFinderStore(hass)
        self._active_issue_ids: set[str] = set()
        self._current_hits: dict[str, list[ReferenceHit]] = {}
        self._unsubs: list[Any] = []
        self._listeners: list[Callable[[], None]] = []
        self._awaiting_scan: set[str] = set()
        self.entity_platform = None
        self._debouncer = Debouncer(
            hass,
            _LOGGER,
            cooldown=DEBOUNCE_COOLDOWN,
            immediate=False,
            function=self._async_run_scan,
        )

    async def async_setup(self) -> None:
        """Set up manager."""
        await self.store.async_load()
        self._unsubs.append(
            self.hass.bus.async_listen(
                EVENT_HOMEASSISTANT_STARTED, self._handle_rescan_event
            )
        )
        self._unsubs.append(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, self._handle_registry_event
            )
        )
        self._unsubs.append(
            self.hass.bus.async_listen(
                EVENT_LOVELACE_UPDATED, self._handle_rescan_event
            )
        )
        self._unsubs.append(
            self.hass.bus.async_listen(
                EVENT_COMPONENT_LOADED, self._handle_component_loaded
            )
        )
        self._unsubs.append(
            self.hass.bus.async_listen("call_service", self._handle_call_service)
        )
        async_call_later(self.hass, 5, self._schedule_scan)

    async def async_unload(self) -> None:
        """Tear down manager."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for issue_id in list(self._active_issue_ids):
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    @callback
    def _handle_rescan_event(self, _event: Event) -> None:
        """Schedule a rescan."""
        self._schedule_scan()

    @callback
    def _handle_component_loaded(self, event: Event) -> None:
        """Schedule rescan when relevant components load."""
        domain = event.data.get("domain")
        if domain in {automation.DOMAIN, script.DOMAIN, scene.DOMAIN, "lovelace"}:
            self._schedule_scan()

    @callback
    def _handle_call_service(self, event: Event) -> None:
        """Schedule rescan after reload services."""
        data = event.data
        domain = data.get("domain")
        service = data.get("service")
        if domain == "homeassistant" and service in {"reload", "reload_all"}:
            self._schedule_scan()
        if service == "reload" and domain in {
            automation.DOMAIN,
            script.DOMAIN,
            scene.DOMAIN,
            "lovelace",
            "group",
        }:
            self._schedule_scan()

    @callback
    def _handle_registry_event(self, event: Event) -> None:
        """Handle entity registry updates."""
        parsed = EntityFinderStore.parse_entity_id_change(event.data)
        if parsed is None:
            return

        old_entity_id, _new_entity_id = parsed

        async def _record_and_scan(_now: Any) -> None:
            await self.store.async_apply_registry_event(event.data)
            self._awaiting_scan.add(old_entity_id)
            self._async_notify_listeners()
            await self._debouncer.async_call()

        async_call_later(self.hass, 0, _record_and_scan)

    @callback
    def _schedule_scan(self, *_args: Any) -> None:
        """Enqueue a debounced scan."""
        self.hass.async_create_task(self._debouncer.async_call())

    async def _async_run_scan(self) -> None:
        """Scan tracked entity ID changes and sync repairs."""
        tracked = self.store.get_tracked_old_ids()
        if not tracked:
            await self._async_sync_repairs({})
            return

        self._current_hits = await async_scan_tracked_references(self.hass, tracked)
        await self._async_sync_repairs(self._current_hits)

    async def _async_sync_repairs(self, hits: dict[str, list[ReferenceHit]]) -> None:
        """Create, update, or delete repair issues."""
        enable_bulk_fix = get_enable_bulk_fix(self.hass, self.entry)
        seen_issue_ids: set[str] = set()

        for old_entity_id, pending in self.store.get_pending_changes().items():
            issue_id = slugify_issue_id(old_entity_id)
            references = hits.get(old_entity_id, [])
            self._awaiting_scan.discard(old_entity_id)

            if not references:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
                await self.store.async_remove_pending(old_entity_id)
                continue

            if self.store.is_ignored(old_entity_id):
                ir.async_ignore_issue(self.hass, DOMAIN, issue_id, True)
                continue

            seen_issue_ids.add(issue_id)
            references_md, manual_note = format_references_for_repair(references)
            bulk_fix_hint = (
                ""
                if enable_bulk_fix
                else "_(Auto-Replace is disabled in integration settings.)_"
            )
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=True,
                is_persistent=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=TRANSLATION_KEY_LOST,
                data={
                    "old_entity_id": old_entity_id,
                    "new_entity_id": pending.new_entity_id,
                },
                translation_placeholders={
                    "old_entity_id": old_entity_id,
                    "new_entity_id": pending.new_entity_id,
                    "references": references_md,
                    "manual_note": f"{manual_note}\n\n" if manual_note else "",
                    "bulk_fix_hint": bulk_fix_hint,
                },
            )

        for issue_id in self._active_issue_ids - seen_issue_ids:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

        self._active_issue_ids = seen_issue_ids
        self._async_notify_listeners()

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to manager state updates."""

        def remove_listener() -> None:
            self._listeners.remove(update_callback)

        self._listeners.append(update_callback)
        return remove_listener

    @callback
    def _async_notify_listeners(self) -> None:
        """Notify entity listeners."""
        for listener in self._listeners:
            listener()

    @callback
    def get_lost_count(self) -> int:
        """Return the number of active (non-ignored) lost entity IDs."""
        return len(self.get_lost_entity_ids())

    @callback
    def get_ignored_lost_count(self) -> int:
        """Return the number of ignored lost entity IDs."""
        return len(self.get_ignored_lost_entity_ids())

    @callback
    def get_lost_entity_ids(self) -> list[str]:
        """Return old entity IDs with unresolved lost entity references."""
        lost: set[str] = set()
        for old_id in self.store.get_pending_changes().keys():
            if self.store.is_ignored(old_id):
                continue
            if self._current_hits.get(old_id):
                lost.add(old_id)
        for old_id in self._awaiting_scan:
            if not self.store.is_ignored(old_id):
                lost.add(old_id)
        return sorted(lost)

    @callback
    def get_ignored_lost_entity_ids(self) -> list[str]:
        """Return ignored old entity IDs with unresolved lost entity references."""
        ignored: set[str] = set()
        for old_id in self.store.get_pending_changes().keys():
            if not self.store.is_ignored(old_id):
                continue
            if self._current_hits.get(old_id):
                ignored.add(old_id)
        for old_id in self._awaiting_scan:
            if self.store.is_ignored(old_id):
                ignored.add(old_id)
        return sorted(ignored)

    @staticmethod
    def _format_references(references: list[ReferenceHit]) -> str:
        """Format reference hits as markdown list."""
        references_md, _manual_note = format_references_for_repair(references)
        return references_md

    def get_hits_for_old_entity(self, old_entity_id: str) -> list[ReferenceHit]:
        """Return latest scan hits for an old entity ID."""
        return list(self._current_hits.get(old_entity_id, []))

    async def async_ignore(self, old_entity_id: str) -> None:
        """Ignore a lost entity ID change repair."""
        await self.store.async_ignore(old_entity_id)
        issue_id = slugify_issue_id(old_entity_id)
        ir.async_ignore_issue(self.hass, DOMAIN, issue_id, True)
        ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        self._async_notify_listeners()

    async def async_ignore_all(self) -> None:
        """Ignore all active lost entity ID repairs."""
        for old_entity_id in self.get_lost_entity_ids():
            await self.async_ignore(old_entity_id)

    async def async_restore_ignored(self) -> None:
        """Restore all ignored lost entity ID repairs."""
        for old_entity_id in self.store.get_ignored_entity_ids():
            issue_id = slugify_issue_id(old_entity_id)
            ir.async_ignore_issue(self.hass, DOMAIN, issue_id, False)
        await self.store.async_clear_ignored()
        await self.async_trigger_rescan()

    async def async_auto_replace_all(self) -> None:
        """Replace all lost entity references when bulk fix is enabled."""
        if not get_enable_bulk_fix(self.hass, self.entry):
            return

        from .replacer import async_apply_replace

        for old_entity_id in list(self.get_lost_entity_ids()):
            pending = self.store.get_pending_changes()[old_entity_id]
            hits = self.get_hits_for_old_entity(old_entity_id)
            await async_apply_replace(
                self.hass,
                hits,
                old_entity_id,
                pending.new_entity_id,
            )
        await self.async_trigger_rescan()

    async def async_trigger_rescan(self) -> None:
        """Run a scan immediately."""
        await self._async_run_scan()
