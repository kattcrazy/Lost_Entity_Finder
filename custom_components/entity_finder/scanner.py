"""Orchestrate reference scanners for Entity Finder."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .models import ReferenceHit
from .scanners import automation, group, helper, lovelace, scene, script, storage
from .util import merge_reference_hits

SCANNERS = (
    automation.async_scan,
    script.async_scan,
    scene.async_scan,
    lovelace.async_scan,
    group.async_scan,
    helper.async_scan,
    storage.async_scan,
)


async def async_scan_tracked_references(
    hass: HomeAssistant, tracked: set[str]
) -> dict[str, list[ReferenceHit]]:
    """Run all scanners for tracked old entity IDs."""
    if not tracked:
        return {}

    results: list[dict[str, list[ReferenceHit]]] = []
    for scanner in SCANNERS:
        results.append(await scanner(hass, tracked))
    return merge_reference_hits(results)
