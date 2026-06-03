"""Scan configuration.yaml (and merged !include / packages) for tracked entity IDs."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ..models import ReferenceHit
from ..util import extract_entities_from_value

_LOGGER = logging.getLogger(__name__)

# Domains already scanned by dedicated component scanners (avoid duplicate repair links).
SKIP_DOMAIN_CONFIG_KEYS = frozenset({"automation", "script", "scene", "group", "lovelace"})

CONFIGURATION_EDIT_URL = "/config/configuration"
CONFIGURATION_RESOURCE_PREFIX = "configuration.yaml"


async def async_scan(
    hass: HomeAssistant, tracked: set[str]
) -> dict[str, list[ReferenceHit]]:
    """Scan merged Home Assistant YAML configuration for tracked old entity IDs."""
    if not tracked:
        return {}

    try:
        config = await _async_load_merged_configuration(hass)
    except (FileNotFoundError, HomeAssistantError) as err:
        _LOGGER.debug("Skipping YAML configuration scan: %s", err)
        return {}
    except Exception:  # noqa: BLE001 - config load can fail for many reasons
        _LOGGER.debug("Unable to load configuration.yaml for scanning", exc_info=True)
        return {}

    hits: dict[str, list[ReferenceHit]] = {}
    for key, value in config.items():
        if key in SKIP_DOMAIN_CONFIG_KEYS:
            continue
        if key == "homeassistant" and isinstance(value, dict):
            await _async_scan_homeassistant_section(hass, value, tracked, hits)
            continue
        await _async_scan_config_section(
            hass, f"{CONFIGURATION_RESOURCE_PREFIX}:{key}", key, value, tracked, hits
        )

    return hits


async def _async_load_merged_configuration(hass: HomeAssistant) -> dict[str, Any]:
    """Load configuration.yaml with !include and package merge (same as HA core)."""
    from homeassistant.config import async_hass_config_yaml

    config = await async_hass_config_yaml(hass)
    if not isinstance(config, dict):
        return {}
    return config


async def _async_scan_homeassistant_section(
    hass: HomeAssistant,
    homeassistant_config: dict[str, Any],
    tracked: set[str],
    hits: dict[str, list[ReferenceHit]],
) -> None:
    """Scan the homeassistant: block, skipping merged packages and covered domains."""
    for key, value in homeassistant_config.items():
        if key in SKIP_DOMAIN_CONFIG_KEYS or key == "packages":
            continue
        section_key = f"homeassistant.{key}"
        await _async_scan_config_section(
            hass,
            f"{CONFIGURATION_RESOURCE_PREFIX}:{section_key}",
            section_key,
            value,
            tracked,
            hits,
        )


async def _async_scan_config_section(
    hass: HomeAssistant,
    resource_id: str,
    section_key: str,
    data: Any,
    tracked: set[str],
    hits: dict[str, list[ReferenceHit]],
) -> None:
    """Scan one configuration section and record hits for tracked entity IDs."""
    found = await _async_extract_from_config_tree(hass, data, tracked)
    if not found:
        return

    hit = ReferenceHit(
        resource_type="yaml_config",
        label=section_label(section_key),
        edit_url=CONFIGURATION_EDIT_URL,
        resource_id=resource_id,
        extra={"section": section_key},
        auto_replaceable=False,
    )
    for entity_id in found:
        hits.setdefault(entity_id, []).append(hit)


async def _async_extract_from_config_tree(
    hass: HomeAssistant, node: Any, tracked: set[str]
) -> set[str]:
    """Extract tracked entity IDs from a config tree, skipping covered domain sections."""
    if isinstance(node, dict):
        found: set[str] = set()
        for key, value in node.items():
            if key in SKIP_DOMAIN_CONFIG_KEYS:
                continue
            found |= await _async_extract_from_config_tree(hass, value, tracked)
        return found

    if isinstance(node, list):
        found = set()
        for item in node:
            found |= await _async_extract_from_config_tree(hass, item, tracked)
        return found

    return await extract_entities_from_value(hass, node, tracked)


def section_label(section_key: str) -> str:
    """Build a human-readable label for a configuration section."""
    return f"configuration.yaml ({section_key})"
