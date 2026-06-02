"""Unit tests for Lost Entity Find And Replace manager helpers."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap  # noqa: F401

mock_config_flow = types.ModuleType("lost_entity_finder.config_flow")
mock_config_flow.get_enable_bulk_fix = lambda _hass, _entry: False
sys.modules["lost_entity_finder.config_flow"] = mock_config_flow

mock_scanner = types.ModuleType("lost_entity_finder.scanner")
mock_scanner.async_scan_tracked_references = MagicMock(return_value={})
sys.modules["lost_entity_finder.scanner"] = mock_scanner

from lost_entity_finder.manager import EntityFinderManager  # noqa: E402
from lost_entity_finder.models import PendingEntityIdChange, ReferenceHit  # noqa: E402


class EntityFinderManagerTests(unittest.TestCase):
    """Tests for lost-entity counting logic."""

    def setUp(self) -> None:
        """Create a manager with a mocked store."""
        self.manager = EntityFinderManager.__new__(EntityFinderManager)
        self.manager.hass = MagicMock()
        self.manager.entry = MagicMock()
        self.manager.store = MagicMock()
        self.manager._active_issue_ids = set()
        self.manager._current_hits = {}
        self.manager._unsubs = []
        self.manager._listeners = []
        self.manager._awaiting_scan = set()
        self.manager.entity_platform = None
        self.manager._debouncer = MagicMock()

    def test_get_lost_entity_ids_includes_scan_hits(self) -> None:
        """Lost count should include old IDs with active references."""
        self.manager.store.get_pending_changes.return_value = {
            "sensor.old": PendingEntityIdChange(
                old_entity_id="sensor.old",
                new_entity_id="sensor.new",
                changed_at="2026-01-01T00:00:00+00:00",
            )
        }
        self.manager.store.is_ignored.return_value = False
        self.manager._current_hits = {
            "sensor.old": [
                ReferenceHit(
                    resource_type="automation",
                    label="Test",
                    edit_url="/config/automation/edit/test",
                    resource_id="test",
                )
            ]
        }

        self.assertEqual(self.manager.get_lost_entity_ids(), ["sensor.old"])
        self.assertEqual(self.manager.get_lost_count(), 1)

    def test_get_lost_entity_ids_includes_awaiting_scan(self) -> None:
        """Lost count should include changes recorded before the first scan."""
        self.manager.store.get_pending_changes.return_value = {
            "sensor.old": PendingEntityIdChange(
                old_entity_id="sensor.old",
                new_entity_id="sensor.new",
                changed_at="2026-01-01T00:00:00+00:00",
            )
        }
        self.manager.store.is_ignored.return_value = False
        self.manager._current_hits = {}
        self.manager._awaiting_scan = {"sensor.old"}

        self.assertEqual(self.manager.get_lost_entity_ids(), ["sensor.old"])

    def test_get_lost_entity_ids_excludes_ignored(self) -> None:
        """Ignored entity ID changes should not appear in the lost count."""
        self.manager.store.get_pending_changes.return_value = {
            "sensor.old": PendingEntityIdChange(
                old_entity_id="sensor.old",
                new_entity_id="sensor.new",
                changed_at="2026-01-01T00:00:00+00:00",
            )
        }
        self.manager.store.is_ignored.return_value = True
        self.manager._current_hits = {
            "sensor.old": [
                ReferenceHit(
                    resource_type="automation",
                    label="Test",
                    edit_url="/config/automation/edit/test",
                    resource_id="test",
                )
            ]
        }
        self.manager._awaiting_scan = {"sensor.old"}

        self.assertEqual(self.manager.get_lost_entity_ids(), [])


if __name__ == "__main__":
    unittest.main()
