"""Scan Lovelace dashboards for tracked old entity IDs."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN
from homeassistant.components.lovelace.const import ConfigNotFound
from homeassistant.core import HomeAssistant, callback

from ..models import ReferenceHit


async def async_scan(
    hass: HomeAssistant, tracked: set[str]
) -> dict[str, list[ReferenceHit]]:
    """Scan dashboards."""
    hits: dict[str, list[ReferenceHit]] = {}
    if LOVELACE_DOMAIN not in hass.data:
        return hits

    dashboards = hass.data[LOVELACE_DOMAIN].dashboards
    for dashboard in dashboards.values():
        url_path = dashboard.url_path or "lovelace"
        title = url_path
        if dashboard.config:
            title = dashboard.config.get("title", url_path)

        try:
            config = await dashboard.async_load(force=False)
        except ConfigNotFound:
            continue

        extracted = _extract_entities(config)
        for entity_id, view_path in extracted.items():
            if entity_id not in tracked:
                continue
            hit = ReferenceHit(
                resource_type="dashboard",
                label=title,
                edit_url=f"/{url_path}/{view_path}?edit=1",
                resource_id=url_path,
                extra={"view_path": view_path},
            )
            hits.setdefault(entity_id, []).append(hit)

    return hits


@callback
def _extract_entities(config: dict[str, Any]) -> dict[str, int | str]:
    """Extract entity IDs mapped to view path."""
    entities: dict[str, int | str] = {}
    if not isinstance(config, dict):
        return entities
    views = config.get("views")
    if not isinstance(views, list):
        return entities
    for view_index, view in enumerate(views):
        if not isinstance(view, dict):
            continue
        view_path: int | str = view.get("path") or view_index
        for entity_id in _extract_from_view(view):
            if entity_id not in entities:
                entities[entity_id] = view_path
    return entities


@callback
def _extract_from_view(config: dict[Any, Any]) -> set[str]:
    """Extract entity IDs from a view."""
    entities: set[str] = set()
    for badge in config.get("badges") or []:
        entities.update(_extract_from_badge(badge))
    for card in config.get("cards") or []:
        entities.update(_extract_from_card(card))
    for section in config.get("sections") or []:
        for card in section.get("cards") or []:
            entities.update(_extract_from_card(card))
    return entities


@callback
def _extract_from_badge(config: dict[str, Any] | str) -> set[str]:
    """Extract entity IDs from a badge."""
    if isinstance(config, str):
        return {config}
    if not isinstance(config, dict):
        return set()
    if isinstance(config.get("entity"), str):
        return {config["entity"]}
    entities = config.get("entities")
    if isinstance(entities, list):
        result: set[str] = set()
        for entity in entities:
            if isinstance(entity, str):
                result.add(entity)
            elif isinstance(entity, dict) and isinstance(entity.get("entity"), str):
                result.add(entity["entity"])
        return result
    return set()


@callback
def _extract_from_card(config: dict[str, Any]) -> set[str]:
    """Extract entity IDs from a card tree."""
    if not isinstance(config, dict):
        return set()

    entities = _extract_common(config)
    entities.update(_extract_from_actions(config))

    if isinstance(config.get("condition"), dict):
        entities.update(_extract_from_condition(config["condition"]))

    if isinstance(config.get("card"), dict):
        entities.update(_extract_from_card(config["card"]))

    for card in config.get("cards") or []:
        entities.update(_extract_from_card(card))

    for key in ("header", "footer"):
        if isinstance(config.get(key), dict):
            entities.update(_extract_common(config[key]))
            entities.update(_extract_from_actions(config[key]))

    for element in config.get("elements") or []:
        entities.update(_extract_from_element(element))

    for chip in config.get("chips") or []:
        if isinstance(chip, dict):
            entities.update(_extract_common(chip))

    for badge in config.get("badges") or []:
        if isinstance(badge, dict):
            entities.update(_extract_common(badge))
            entities.update(_extract_from_actions(badge))

    for condition in config.get("visibility") or []:
        if isinstance(condition, dict):
            entities.update(_extract_from_condition(condition))

    return entities


@callback
def _extract_common(config: dict[str, Any]) -> set[str]:
    """Extract from common entity fields."""
    entities: set[str] = set()
    for key in ("camera_image", "entity", "entities", "entity_id"):
        value = config.get(key)
        if isinstance(value, str):
            entities.add(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    entities.add(item)
                elif isinstance(item, dict) and isinstance(item.get("entity"), str):
                    entities.add(item["entity"])
        elif isinstance(value, dict) and isinstance(value.get("entity"), str):
            entities.add(value["entity"])
    return entities


@callback
def _extract_from_actions(config: dict[str, Any]) -> set[str]:
    """Extract entity IDs from card actions."""
    entities: set[str] = set()
    for key in (
        "tap_action",
        "hold_action",
        "double_tap_action",
        "subtitle_tap_action",
    ):
        action = config.get(key)
        if isinstance(action, dict):
            entities.update(_extract_from_action(action))
    return entities


@callback
def _extract_from_action(config: dict[str, Any]) -> set[str]:
    """Extract entity IDs from a single action."""
    entities: set[str] = set()
    for key in ("service_data", "target"):
        target = config.get(key)
        if isinstance(target, dict):
            entity_id = target.get("entity_id")
            if isinstance(entity_id, str):
                entities.add(entity_id)
            elif isinstance(entity_id, list):
                entities.update(entity_id)
    return entities


@callback
def _extract_from_condition(config: dict[str, Any]) -> set[str]:
    """Extract entity IDs from a condition."""
    if isinstance(config.get("entity"), str):
        return {config["entity"]}
    return set()


@callback
def _extract_from_element(config: dict[str, Any]) -> set[str]:
    """Extract entity IDs from a picture-elements element."""
    if not isinstance(config, dict):
        return set()
    entities = _extract_common(config)
    entities.update(_extract_from_actions(config))
    for condition in config.get("conditions") or []:
        if isinstance(condition, dict):
            entities.update(_extract_from_condition(condition))
    for element in config.get("elements") or []:
        entities.update(_extract_from_element(element))
    return entities
