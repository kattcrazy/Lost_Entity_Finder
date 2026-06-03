"""Unit tests for configuration.yaml scanning."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap  # noqa: F401

from lost_entity_finder.scanners import yaml_config  # noqa: E402
from lost_entity_finder.util import manual_reference_reason  # noqa: E402
from lost_entity_finder.models import ReferenceHit  # noqa: E402


class YamlConfigHelperTests(unittest.TestCase):
    """Tests for YAML config scanner helpers."""

    def test_section_label(self) -> None:
        """Section labels should name the configuration area."""
        self.assertEqual(
            yaml_config.section_label("sensor"),
            "configuration.yaml (sensor)",
        )

    def test_manual_reason_for_yaml_config(self) -> None:
        """YAML configuration hits should explain manual updates."""
        hit = ReferenceHit(
            resource_type="yaml_config",
            label="configuration.yaml (template)",
            edit_url="/config/configuration",
            resource_id="configuration.yaml:template",
            auto_replaceable=False,
        )
        self.assertEqual(manual_reference_reason(hit), "YAML config")


class YamlConfigTreeTests(unittest.IsolatedAsyncioTestCase):
    """Tests for config tree extraction."""

    async def asyncSetUp(self) -> None:
        """Create a mock Home Assistant instance."""
        self.hass = MagicMock()

    async def test_extract_skips_automation_subtree(self) -> None:
        """Automation YAML should not be scanned here (dedicated scanner handles it)."""
        config = {
            "automation": [
                {
                    "alias": "Test",
                    "trigger": {"platform": "state", "entity_id": "sensor.old"},
                }
            ],
            "template": [
                {
                    "sensor": {
                        "temp": {
                            "value_template": "{{ states('sensor.old') }}",
                        }
                    }
                },
            ],
        }
        found = await yaml_config._async_extract_from_config_tree(
            self.hass, config, {"sensor.old"}
        )
        self.assertEqual(found, {"sensor.old"})

    async def test_extract_skips_nested_domain_keys(self) -> None:
        """Package-style nested automation/script blocks should be skipped."""
        config = {
            "homeassistant": {
                "packages": {
                    "garage": {
                        "automation": [
                            {
                                "alias": "Garage",
                                "trigger": {
                                    "platform": "state",
                                    "entity_id": "binary_sensor.old",
                                },
                            }
                        ],
                        "notify": [{"name": "alert", "platform": "telegram"}],
                    }
                },
                "customize": {
                    "sensor.old": {"friendly_name": "Old"},
                },
            }
        }
        found = await yaml_config._async_extract_from_config_tree(
            self.hass, config["homeassistant"]["packages"]["garage"], {"binary_sensor.old"}
        )
        self.assertEqual(found, set())

    async def test_scan_finds_template_sensor_reference(self) -> None:
        """Merged configuration should surface YAML-only references."""
        merged_config = {
            "template": [
                {
                    "sensor": {
                        "temp": {
                            "value_template": "{{ states('sensor.old_light') }}",
                        }
                    }
                }
            ],
            "automation": [
                {
                    "alias": "Skip me",
                    "trigger": {"platform": "state", "entity_id": "sensor.old_light"},
                }
            ],
        }
        self.hass = MagicMock()

        with patch.object(
            yaml_config,
            "_async_load_merged_configuration",
            AsyncMock(return_value=merged_config),
        ):
            hits = await yaml_config.async_scan(self.hass, {"sensor.old_light"})

        self.assertIn("sensor.old_light", hits)
        self.assertEqual(len(hits["sensor.old_light"]), 1)
        self.assertEqual(hits["sensor.old_light"][0].resource_type, "yaml_config")
        self.assertEqual(
            hits["sensor.old_light"][0].label,
            "configuration.yaml (template)",
        )
        self.assertFalse(hits["sensor.old_light"][0].auto_replaceable)


if __name__ == "__main__":
    unittest.main()
