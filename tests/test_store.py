"""Unit tests for Lost Entity Find And Replace storage."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap  # noqa: F401

from lost_entity_find_and_replace.const import MAX_PENDING_CHANGES
from lost_entity_find_and_replace.store import EntityFinderStore


class EntityFinderStoreTests(unittest.IsolatedAsyncioTestCase):
    """Tests for pending entity ID change storage."""

    async def asyncSetUp(self) -> None:
        """Create a store with mocked persistence."""
        self.store = EntityFinderStore.__new__(EntityFinderStore)
        self.store.hass = MagicMock()
        self.store._pending = {}
        self.store._ignored = set()
        self.store._pending_store = MagicMock()
        self.store._pending_store.async_save = AsyncMock()
        self.store._ignored_store = MagicMock()
        self.store._ignored_store.async_save = AsyncMock()

    async def test_record_entity_id_change_persists_entry(self) -> None:
        """Recording a change should write to the pending store."""
        await self.store.async_record_entity_id_change(
            "sensor.old", "sensor.new", unique_id="abc"
        )

        pending = self.store.get_pending_changes()
        self.assertIn("sensor.old", pending)
        self.assertEqual(pending["sensor.old"].new_entity_id, "sensor.new")
        self.assertEqual(pending["sensor.old"].unique_id, "abc")
        self.assertTrue(pending["sensor.old"].changed_at)
        self.store._pending_store.async_save.assert_awaited()

    async def test_chain_collapse_updates_intermediate_target(self) -> None:
        """A->B followed by B->C should collapse the original old ID to C."""
        await self.store.async_record_entity_id_change("sensor.a", "sensor.b")
        await self.store.async_record_entity_id_change("sensor.b", "sensor.c")

        pending = self.store.get_pending_changes()
        self.assertEqual(pending["sensor.a"].new_entity_id, "sensor.c")
        self.assertEqual(pending["sensor.b"].new_entity_id, "sensor.c")

    async def test_pending_cap_drops_oldest(self) -> None:
        """Pending changes should stay under the configured cap."""
        for index in range(MAX_PENDING_CHANGES + 3):
            await self.store.async_record_entity_id_change(
                f"sensor.old_{index:02d}",
                f"sensor.new_{index:02d}",
            )
            self.store._pending[f"sensor.old_{index:02d}"]["changed_at"] = (
                f"2026-01-01T00:00:{index:02d}+00:00"
            )

        self.store._enforce_pending_cap()
        self.assertEqual(len(self.store._pending), MAX_PENDING_CHANGES)
        self.assertNotIn("sensor.old_00", self.store._pending)
        self.assertIn(f"sensor.old_{MAX_PENDING_CHANGES + 2:02d}", self.store._pending)

    async def test_async_load_reads_changes_key(self) -> None:
        """Storage should use the changes key for pending entity ID changes."""
        self.store._pending_store.async_load = AsyncMock(
            return_value={
                "changes": {
                    "sensor.old": {
                        "new_entity_id": "sensor.new",
                        "changed_at": "2026-01-01T00:00:00+00:00",
                    }
                }
            }
        )
        self.store._ignored_store.async_load = AsyncMock(return_value={"entity_ids": []})

        await self.store.async_load()

        pending = self.store.get_pending_changes()
        self.assertEqual(pending["sensor.old"].new_entity_id, "sensor.new")

    def test_parse_entity_id_change_from_old_entity_id(self) -> None:
        """Registry events should expose old and new entity IDs."""
        parsed = EntityFinderStore.parse_entity_id_change(
            {
                "action": "update",
                "entity_id": "sensor.kitchen",
                "old_entity_id": "sensor.old_kitchen",
            }
        )
        self.assertEqual(parsed, ("sensor.old_kitchen", "sensor.kitchen"))

    def test_parse_entity_id_change_from_changes(self) -> None:
        """Reset/regenerate events may only include the old ID in changes."""
        parsed = EntityFinderStore.parse_entity_id_change(
            {
                "action": "update",
                "entity_id": "light.living_room",
                "changes": {"entity_id": "light.old_living_room"},
            }
        )
        self.assertEqual(parsed, ("light.old_living_room", "light.living_room"))

    def test_parse_entity_id_change_ignores_unchanged(self) -> None:
        """Unchanged entity IDs should not be treated as changes."""
        parsed = EntityFinderStore.parse_entity_id_change(
            {
                "action": "update",
                "entity_id": "sensor.same",
                "old_entity_id": "sensor.same",
            }
        )
        self.assertIsNone(parsed)

    async def test_apply_registry_event_records_change(self) -> None:
        """Registry update events should create pending changes."""
        registry = MagicMock()
        registry.async_get.return_value = MagicMock(unique_id="uid-1")

        with patch(
            "lost_entity_find_and_replace.store.er.async_get",
            return_value=registry,
        ):
            await self.store.async_apply_registry_event(
                {
                    "action": "update",
                    "entity_id": "sensor.new",
                    "old_entity_id": "sensor.old",
                }
            )

        pending = self.store.get_pending_changes()
        self.assertEqual(pending["sensor.old"].new_entity_id, "sensor.new")


if __name__ == "__main__":
    unittest.main()
