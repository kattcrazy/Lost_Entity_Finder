"""Unit tests for Entity Finder helpers."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap  # noqa: F401

from entity_finder.models import ReferenceHit
from entity_finder.util import (
    deep_replace_entity_ids,
    format_references_for_repair,
    merge_reference_hits,
    slugify_issue_id,
)


class EntityFinderUtilTests(unittest.TestCase):
    """Tests for util helpers."""

    def test_slugify_issue_id(self) -> None:
        """Issue IDs should be stable and safe."""
        self.assertEqual(slugify_issue_id("sensor.door"), "stale_sensor_door")

    def test_merge_reference_hits_deduplicates(self) -> None:
        """Merged hits should deduplicate by resource."""
        hit = ReferenceHit(
            resource_type="automation",
            label="Test",
            edit_url="/config/automation/edit/test",
            resource_id="test",
        )
        merged = merge_reference_hits(
            [{"sensor.old": [hit]}, {"sensor.old": [hit]}]
        )
        self.assertEqual(len(merged["sensor.old"]), 1)

    def test_deep_replace_entity_id_in_dict(self) -> None:
        """Structured replace should update entity_id fields."""
        hass = MagicMock()
        config = {"entity_id": "sensor.door", "nested": {"entity": "sensor.door"}}
        new_config, count = asyncio.run(
            deep_replace_entity_ids(hass, config, "sensor.door", "sensor.window")
        )
        self.assertEqual(count, 2)
        self.assertEqual(new_config["entity_id"], "sensor.window")
        self.assertEqual(new_config["nested"]["entity"], "sensor.window")

    def test_deep_replace_avoids_partial_match(self) -> None:
        """Replace should not touch sensor.doorbell when replacing sensor.door."""
        hass = MagicMock()
        config = {"entity_id": "sensor.doorbell"}
        new_config, count = asyncio.run(
            deep_replace_entity_ids(hass, config, "sensor.door", "sensor.window")
        )
        self.assertEqual(count, 0)
        self.assertEqual(new_config["entity_id"], "sensor.doorbell")

    def test_deep_replace_does_not_mutate_original(self) -> None:
        """Auto-Replace works on copies and leaves the source config unchanged."""
        hass = MagicMock()
        config = {"entity_id": "sensor.door"}
        new_config, count = asyncio.run(
            deep_replace_entity_ids(hass, config, "sensor.door", "sensor.window")
        )
        self.assertEqual(count, 1)
        self.assertEqual(config["entity_id"], "sensor.door")
        self.assertEqual(new_config["entity_id"], "sensor.window")

    def test_format_references_marks_manual_items(self) -> None:
        """Repairs should flag helpers and YAML configs before auto-replace runs."""
        hits = [
            ReferenceHit(
                resource_type="automation",
                label="UI Automation",
                edit_url="/config/automation/edit/ui",
                resource_id="ui",
                auto_replaceable=True,
            ),
            ReferenceHit(
                resource_type="automation",
                label="YAML Automation",
                edit_url="/config/automation/edit/yaml",
                resource_id="yaml",
                auto_replaceable=False,
            ),
            ReferenceHit(
                resource_type="helper",
                label="Trend Helper",
                edit_url="/config/helpers",
                resource_id="sensor.trend",
                auto_replaceable=False,
            ),
        ]
        references, manual_note = format_references_for_repair(hits)
        self.assertIn("UI Automation", references)
        self.assertIn("manual update required - YAML config", references)
        self.assertIn("manual update required - helper", references)
        self.assertIn("2 reference(s) cannot be auto-replaced", manual_note)


if __name__ == "__main__":
    unittest.main()
