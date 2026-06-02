"""Scan scripts for tracked old entity IDs."""

from __future__ import annotations

from typing import Any

from homeassistant.components import script
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import DATA_INSTANCES

from ..models import ReferenceHit
from ..util import extract_entities_from_value


async def async_scan(
    hass: HomeAssistant, tracked: set[str]
) -> dict[str, list[ReferenceHit]]:
    """Scan scripts."""
    hits: dict[str, list[ReferenceHit]] = {}
    instances = hass.data.get(DATA_INSTANCES, {})
    if script.DOMAIN not in instances:
        return hits

    component = instances[script.DOMAIN]
    for entity in component.entities:
        found: set[str] = set(getattr(entity, "referenced_entities", []) or [])
        found.update(
            await _extract_from_config(hass, getattr(entity, "raw_config", None), tracked)
        )
        found &= tracked
        if not found:
            continue

        unique_id = getattr(entity, "unique_id", None) or entity.entity_id.split(".", 1)[-1]
        label = getattr(entity, "name", None) or entity.entity_id
        hit = ReferenceHit(
            resource_type="script",
            label=label,
            edit_url=f"/config/script/edit/{unique_id}",
            resource_id=str(unique_id),
            extra={"entity_id": entity.entity_id},
            auto_replaceable=bool(getattr(entity, "raw_config", None)),
        )
        for entity_id in found:
            hits.setdefault(entity_id, []).append(hit)

    return hits


async def _extract_from_config(
    hass: HomeAssistant, config: dict[str, Any] | None, tracked: set[str]
) -> set[str]:
    """Extract tracked entity IDs from script config."""
    if not config:
        return set()
    return await extract_entities_from_value(hass, config, tracked)
