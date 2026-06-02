"""Scan helper entities for tracked old entity IDs."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import DATA_ENTITY_PLATFORM

from ..models import ReferenceHit

HELPER_DOMAINS = (
    "utility_meter",
    "trend",
    "switch_as_x",
    "integration",
    "min_max",
    "statistics",
)


async def async_scan(
    hass: HomeAssistant, tracked: set[str]
) -> dict[str, list[ReferenceHit]]:
    """Scan helpers with source entity references."""
    hits: dict[str, list[ReferenceHit]] = {}
    platforms = hass.data.get(DATA_ENTITY_PLATFORM, {})

    for domain in HELPER_DOMAINS:
        for platform in platforms.get(domain, []):
            for entity in platform.entities.values():
                source = _get_source_entity_id(entity)
                if not source or source not in tracked:
                    continue
                label = getattr(entity, "name", None) or entity.entity_id
                hit = ReferenceHit(
                    resource_type="helper",
                    label=label,
                    edit_url="/config/helpers",
                    resource_id=entity.entity_id,
                    extra={"entity_id": entity.entity_id, "source": source},
                    auto_replaceable=False,
                )
                hits.setdefault(source, []).append(hit)

    return hits


def _get_source_entity_id(entity: object) -> str | None:
    """Return source entity ID from a helper entity when available."""
    for attr in ("source_entity_id", "_source_entity_id", "source"):
        value = getattr(entity, attr, None)
        if isinstance(value, str):
            return value
    return None
