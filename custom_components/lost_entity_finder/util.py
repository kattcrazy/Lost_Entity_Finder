"""Utility helpers for Lost Entity Find And Replace."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import template

if TYPE_CHECKING:
    from .models import ReferenceHit
else:
    from .models import ReferenceHit  # used at runtime in merge_reference_hits

ENTITY_ID_PATTERN = re.compile(
    r"^(?:(?:automation|binary_sensor|button|camera|climate|cover|device_tracker|"
    r"fan|group|humidifier|input_boolean|input_button|input_datetime|input_number|"
    r"input_select|input_text|light|lock|media_player|number|person|remote|scene|"
    r"script|select|sensor|sun|switch|text|time|timer|todo|update|vacuum|valve|"
    r"water_heater|weather|zone)\.[a-z0-9_]+)$"
)

TEMPLATE_MARKERS = ("{{", "{%", "{%")


def slugify_issue_id(old_entity_id: str) -> str:
    """Build a stable issue ID from an old entity ID."""
    return "stale_" + old_entity_id.replace(".", "_").replace("-", "_")


def is_template_string(value: str) -> bool:
    """Return True if value looks like a Jinja template."""
    return any(marker in value for marker in TEMPLATE_MARKERS)


async def extract_entities_from_value(
    hass: HomeAssistant, value: Any, tracked: set[str]
) -> set[str]:
    """Extract tracked entity IDs from a config value."""
    found: set[str] = set()

    if isinstance(value, str):
        if is_template_string(value):
            try:
                tmpl = template.Template(value, hass)
                info = await tmpl.async_render_to_info(hass, {})
                for entity_id in info.entities:
                    if entity_id in tracked:
                        found.add(entity_id)
            except Exception:  # noqa: BLE001 - template parse errors are skipped
                for entity_id in tracked:
                    if entity_id in value:
                        found.add(entity_id)
        elif value in tracked:
            found.add(value)
        else:
            for entity_id in tracked:
                if _entity_id_in_text(value, entity_id):
                    found.add(entity_id)
    elif isinstance(value, list):
        for item in value:
            found.update(await extract_entities_from_value(hass, item, tracked))
    elif isinstance(value, dict):
        if (
            "entity" in value
            and isinstance(value["entity"], str)
            and value["entity"] in tracked
        ):
            found.add(value["entity"])
        for item in value.values():
            found.update(await extract_entities_from_value(hass, item, tracked))

    return found


def _entity_id_in_text(text: str, entity_id: str) -> bool:
    """Match a full entity ID token inside text."""
    pattern = re.compile(rf"(?<![a-z0-9_]){re.escape(entity_id)}(?![a-z0-9_])")
    return bool(pattern.search(text))


async def deep_replace_entity_ids(
    hass: HomeAssistant,
    value: Any,
    old_entity_id: str,
    new_entity_id: str,
) -> tuple[Any, int]:
    """Deep-replace old entity ID with new in structured config. Returns (value, count)."""
    replacements = 0

    if isinstance(value, str):
        if value == old_entity_id:
            return new_entity_id, 1
        if is_template_string(value) or old_entity_id in value:
            new_value, count = _replace_in_text(value, old_entity_id, new_entity_id)
            return new_value, count
        return value, 0

    if isinstance(value, list):
        new_list: list[Any] = []
        for item in value:
            new_item, count = await deep_replace_entity_ids(
                hass, item, old_entity_id, new_entity_id
            )
            new_list.append(new_item)
            replacements += count
        return new_list, replacements

    if isinstance(value, dict):
        new_dict: dict[Any, Any] = {}
        for key, item in value.items():
            if key == "entity" and item == old_entity_id:
                new_dict[key] = new_entity_id
                replacements += 1
                continue
            new_item, count = await deep_replace_entity_ids(
                hass, item, old_entity_id, new_entity_id
            )
            new_dict[key] = new_item
            replacements += count
        return new_dict, replacements

    return value, 0


def _replace_in_text(text: str, old_entity_id: str, new_entity_id: str) -> tuple[str, int]:
    """Replace whole entity ID tokens in a string."""
    pattern = re.compile(rf"(?<![a-z0-9_]){re.escape(old_entity_id)}(?![a-z0-9_])")
    new_text, count = pattern.subn(new_entity_id, text)
    return new_text, count


def merge_reference_hits(
    results: list[dict[str, list["ReferenceHit"]]],
) -> dict[str, list["ReferenceHit"]]:
    """Merge scanner outputs keyed by old entity ID."""
    merged: dict[str, list[ReferenceHit]] = {}
    for result in results:
        for entity_id, hits in result.items():
            bucket = merged.setdefault(entity_id, [])
            seen = {(hit.resource_type, hit.resource_id) for hit in bucket}
            for hit in hits:
                key = (hit.resource_type, hit.resource_id)
                if key not in seen:
                    bucket.append(hit)
                    seen.add(key)
    return merged


def dedupe_reference_hits(
    hits: list[ReferenceHit],
) -> dict[tuple[str, str], ReferenceHit]:
    """Deduplicate reference hits by resource type and ID."""
    unique: dict[tuple[str, str], ReferenceHit] = {}
    for hit in hits:
        unique[(hit.resource_type, hit.resource_id)] = hit
    return unique


def has_auto_replaceable_hits(hits: list[ReferenceHit]) -> bool:
    """Return True when at least one reference can be auto-replaced."""
    return any(hit.auto_replaceable for hit in dedupe_reference_hits(hits).values())


def manual_reference_reason(hit: ReferenceHit) -> str:
    """Return a short reason why a reference must be updated manually."""
    if hit.resource_type == "storage":
        return "third-party storage"
    if hit.resource_type == "helper":
        return "helper"
    if hit.resource_type in {"automation", "script", "scene"}:
        return "YAML config"
    return "manual edit"


def format_references_for_repair(
    hits: list[ReferenceHit],
) -> tuple[str, str]:
    """Format references for repairs, marking items that need manual updates."""
    lines: list[str] = []
    manual_count = 0

    for hit in dedupe_reference_hits(hits).values():
        line = f"- [{hit.label}]({hit.edit_url})"
        if not hit.auto_replaceable:
            manual_count += 1
            line += " _(manual update required)_"
        lines.append(line)

    manual_note = ""
    if manual_count:
        manual_note = (
            f"_{manual_count} reference(s) cannot be auto-replaced and must be "
            "updated manually._"
        )

    return "\n".join(lines), manual_note
