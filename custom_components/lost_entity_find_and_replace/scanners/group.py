"""Scan groups for tracked old entity IDs."""

from __future__ import annotations

from homeassistant.components import group
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import DATA_INSTANCES

from ..models import ReferenceHit


async def async_scan(
    hass: HomeAssistant, tracked: set[str]
) -> dict[str, list[ReferenceHit]]:
    """Scan groups."""
    hits: dict[str, list[ReferenceHit]] = {}
    instances = hass.data.get(DATA_INSTANCES, {})
    if group.DOMAIN not in instances:
        return hits

    component = instances[group.DOMAIN]
    for entity in component.entities:
        members = set(getattr(entity, "extra_state_attributes", {}).get("entity_id", []) or [])
        if not members:
            tracked_in_group = tracked & set(getattr(entity, "entity_ids", []) or [])
            members = tracked_in_group

        found = members & tracked
        if not found:
            continue

        label = getattr(entity, "name", None) or entity.entity_id
        hit = ReferenceHit(
            resource_type="group",
            label=label,
            edit_url=f"/config/entities?historyBack=1&entity={entity.entity_id}",
            resource_id=entity.entity_id,
            extra={"entity_id": entity.entity_id},
        )
        for entity_id in found:
            hits.setdefault(entity_id, []).append(hit)

    return hits
