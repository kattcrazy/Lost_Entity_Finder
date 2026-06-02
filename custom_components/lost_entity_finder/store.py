"""Persistent storage for Lost Entity Find And Replace."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import (
    MAX_IGNORED,
    MAX_PENDING_CHANGES,
    STORAGE_KEY_IGNORED,
    STORAGE_KEY_PENDING,
    STORAGE_VERSION,
)
from .models import PendingEntityIdChange

_LOGGER = logging.getLogger(__name__)


class EntityFinderStore:
    """Manage pending entity ID changes and ignored entity IDs."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize stores."""
        self.hass = hass
        self._pending_store = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY_PENDING,
        )
        self._ignored_store = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY_IGNORED,
        )
        self._pending: dict[str, dict[str, Any]] = {}
        self._ignored: set[str] = set()

    async def async_load(self) -> None:
        """Load both stores."""
        pending_data = await self._pending_store.async_load() or {}
        self._pending = pending_data.get("changes", {})
        ignored_data = await self._ignored_store.async_load() or {}
        self._ignored = set(ignored_data.get("entity_ids", []))

    async def async_save_pending(self) -> None:
        """Persist pending entity ID changes."""
        await self._pending_store.async_save({"changes": self._pending})

    async def async_save_ignored(self) -> None:
        """Persist ignored entity IDs."""
        await self._ignored_store.async_save({"entity_ids": sorted(self._ignored)})

    @callback
    def get_pending_changes(self) -> dict[str, PendingEntityIdChange]:
        """Return pending entity ID changes keyed by old entity ID."""
        result: dict[str, PendingEntityIdChange] = {}
        for old_id, data in self._pending.items():
            result[old_id] = PendingEntityIdChange(
                old_entity_id=old_id,
                new_entity_id=data["new_entity_id"],
                changed_at=data.get("changed_at", ""),
                unique_id=data.get("unique_id"),
            )
        return result

    @callback
    def get_tracked_old_ids(self) -> set[str]:
        """Return old entity IDs being tracked."""
        return set(self._pending.keys())

    @callback
    def is_ignored(self, old_entity_id: str) -> bool:
        """Return True if the old entity ID is ignored."""
        return old_entity_id in self._ignored

    @callback
    def get_new_entity_id(self, old_entity_id: str) -> str | None:
        """Return the new entity ID for a tracked old ID."""
        entry = self._pending.get(old_entity_id)
        if not entry:
            return None
        return entry.get("new_entity_id")

    async def async_record_entity_id_change(
        self,
        old_entity_id: str,
        new_entity_id: str,
        unique_id: str | None = None,
    ) -> None:
        """Record an entity ID change, collapsing chains when needed."""
        now = datetime.now(timezone.utc).isoformat()

        # Chain collapse: if new_entity_id was previously tracked as an old ID's target,
        # update any entry pointing to new_entity_id as its new target.
        for old_id, data in list(self._pending.items()):
            if data.get("new_entity_id") == old_entity_id and old_id != old_entity_id:
                data["new_entity_id"] = new_entity_id
                data["changed_at"] = now

        if old_entity_id in self._pending:
            self._pending[old_entity_id]["new_entity_id"] = new_entity_id
            self._pending[old_entity_id]["changed_at"] = now
            if unique_id:
                self._pending[old_entity_id]["unique_id"] = unique_id
        else:
            self._pending[old_entity_id] = {
                "new_entity_id": new_entity_id,
                "changed_at": now,
                "unique_id": unique_id,
            }

        self._enforce_pending_cap()
        await self.async_save_pending()

    async def async_remove_pending(self, old_entity_id: str) -> None:
        """Remove a pending entity ID change."""
        if old_entity_id in self._pending:
            del self._pending[old_entity_id]
            await self.async_save_pending()

    async def async_ignore(self, old_entity_id: str) -> None:
        """Ignore repairs for an old entity ID."""
        self._ignored.add(old_entity_id)
        if len(self._ignored) > MAX_IGNORED:
            self._ignored = set(sorted(self._ignored)[-MAX_IGNORED:])
        await self.async_save_ignored()

    async def async_unignore(self, old_entity_id: str) -> None:
        """Stop ignoring an old entity ID."""
        self._ignored.discard(old_entity_id)
        await self.async_save_ignored()

    @callback
    def get_ignored_entity_ids(self) -> set[str]:
        """Return ignored old entity IDs."""
        return set(self._ignored)

    async def async_clear_ignored(self) -> None:
        """Clear all ignored old entity IDs."""
        self._ignored.clear()
        await self.async_save_ignored()

    def _enforce_pending_cap(self) -> None:
        """Keep pending entity ID changes under the safety cap."""
        if len(self._pending) <= MAX_PENDING_CHANGES:
            return
        sorted_items = sorted(
            self._pending.items(),
            key=lambda item: item[1].get("changed_at", ""),
        )
        self._pending = dict(sorted_items[-MAX_PENDING_CHANGES:])

    @staticmethod
    def parse_entity_id_change(
        event_data: dict[str, Any],
    ) -> tuple[str, str] | None:
        """Extract an entity ID change from a registry update event."""
        if event_data.get("action") != "update":
            return None

        new_entity_id = event_data.get("entity_id")
        if not new_entity_id:
            return None

        old_entity_id = event_data.get("old_entity_id")
        if not old_entity_id:
            changes = event_data.get("changes") or {}
            old_entity_id = changes.get("entity_id")

        if not old_entity_id or old_entity_id == new_entity_id:
            return None

        return old_entity_id, new_entity_id

    @callback
    def handle_registry_event(self, event_data: dict[str, Any]) -> bool:
        """Return True when the registry event is an entity ID change."""
        return self.parse_entity_id_change(event_data) is not None

    async def async_apply_registry_event(self, event_data: dict[str, Any]) -> None:
        """Apply an entity ID change from a registry event."""
        parsed = self.parse_entity_id_change(event_data)
        if parsed is None:
            return

        old_entity_id, new_entity_id = parsed
        registry = er.async_get(self.hass)
        entry = registry.async_get(new_entity_id)
        unique_id = entry.unique_id if entry else None
        await self.async_record_entity_id_change(
            old_entity_id, new_entity_id, unique_id
        )
