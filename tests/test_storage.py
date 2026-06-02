"""Unit tests for .storage scanning."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap  # noqa: F401

from entity_finder.scanners import storage  # noqa: E402
from entity_finder.util import manual_reference_reason  # noqa: E402
from entity_finder.models import ReferenceHit  # noqa: E402


class StorageScannerHelperTests(unittest.TestCase):
    """Tests for .storage helper functions."""

    def test_should_skip_core_registry_files(self) -> None:
        """Core registry files should not be scanned."""
        self.assertTrue(storage.should_skip_storage_file("core.entity_registry"))
        self.assertTrue(storage.should_skip_storage_file("automation.storage"))

    def test_should_scan_third_party_storage(self) -> None:
        """Third-party storage files should be scanned."""
        self.assertFalse(storage.should_skip_storage_file("scheduler.storage"))

    def test_storage_label_and_edit_url(self) -> None:
        """Storage hits should have readable labels and integration links."""
        self.assertEqual(
            storage.storage_label_from_filename("scheduler.storage"),
            "Scheduler (.storage/scheduler.storage)",
        )
        self.assertEqual(
            storage.storage_edit_url_from_filename("scheduler.storage"),
            "/config/integrations/integration/scheduler",
        )

    def test_manual_reason_for_storage(self) -> None:
        """Storage hits should explain why auto-replace is unavailable."""
        hit = ReferenceHit(
            resource_type="storage",
            label="Scheduler (.storage/scheduler.storage)",
            edit_url="/config/integrations/integration/scheduler",
            resource_id="scheduler.storage",
            auto_replaceable=False,
        )
        self.assertEqual(manual_reference_reason(hit), "third-party storage")


class StorageScannerAsyncTests(unittest.IsolatedAsyncioTestCase):
    """Tests for async .storage scanning."""

    async def asyncSetUp(self) -> None:
        """Create a temporary .storage directory."""
        self.storage_dir = Path(self._temp_dir()) / ".storage"
        self.storage_dir.mkdir(parents=True)
        self.hass = MagicMock()
        self.hass.config.path.side_effect = lambda subpath="": (
            str(self.storage_dir) if subpath == ".storage" else str(self.storage_dir.parent)
        )

        async def _run_executor(func, *args, **kwargs):
            return func(*args, **kwargs)

        self.hass.async_add_executor_job = _run_executor

    def _temp_dir(self) -> str:
        import tempfile

        return tempfile.mkdtemp()

    async def test_scan_finds_entity_in_third_party_storage(self) -> None:
        """Scanner should find tracked IDs in uncaptured .storage files."""
        (self.storage_dir / "scheduler.storage").write_text(
            json.dumps({"jobs": [{"entity_id": "sensor.old_light"}]}),
            encoding="utf-8",
        )
        (self.storage_dir / "core.entity_registry").write_text("{}", encoding="utf-8")

        hits = await storage.async_scan(self.hass, {"sensor.old_light"})

        self.assertIn("sensor.old_light", hits)
        self.assertEqual(len(hits["sensor.old_light"]), 1)
        self.assertEqual(hits["sensor.old_light"][0].resource_type, "storage")
        self.assertFalse(hits["sensor.old_light"][0].auto_replaceable)

    async def test_scan_skips_invalid_json(self) -> None:
        """Broken storage files should be ignored safely."""
        (self.storage_dir / "broken.storage").write_text("{not json", encoding="utf-8")

        hits = await storage.async_scan(self.hass, {"sensor.old_light"})

        self.assertEqual(hits, {})


if __name__ == "__main__":
    unittest.main()
