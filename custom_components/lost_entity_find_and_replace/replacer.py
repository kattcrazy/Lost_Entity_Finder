"""Apply structured entity ID replacements across HA configs."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import automation, script
from homeassistant.components.homeassistant import scene
from homeassistant.components.lovelace import DOMAIN as LOVELACE_DOMAIN
from homeassistant.components.lovelace.const import ConfigNotFound
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.util.file import write_utf8_file_atomic
from homeassistant.util.yaml import dump

from .models import ReferenceHit
from .util import dedupe_reference_hits, deep_replace_entity_ids, manual_reference_reason

_LOGGER = logging.getLogger(__name__)


class ReplaceResult:
    """Summary of an Auto-Replace run."""

    def __init__(self) -> None:
        """Initialize result."""
        self.updated: list[str] = []
        self.skipped: list[str] = []
        self.failed: list[str] = []

    def summary(self) -> str:
        """Return a human-readable summary."""
        lines: list[str] = []
        if self.updated:
            lines.append("Updated:\n" + "\n".join(f"- {item}" for item in self.updated))
        if self.skipped:
            lines.append("Skipped:\n" + "\n".join(f"- {item}" for item in self.skipped))
        if self.failed:
            lines.append("Failed:\n" + "\n".join(f"- {item}" for item in self.failed))
        return "\n\n".join(lines) if lines else "No changes were applied."


async def async_preview_replace(
    hass: HomeAssistant,
    hits: list[ReferenceHit],
    old_entity_id: str,
    new_entity_id: str,
) -> tuple[str, dict[tuple[str, str], ReferenceHit]]:
    """Build a preview string and deduplicated hit map."""
    unique = dedupe_reference_hits(hits)
    auto_hits = [hit for hit in unique.values() if hit.auto_replaceable]
    manual_hits = [hit for hit in unique.values() if not hit.auto_replaceable]

    sections: list[str] = []
    if auto_hits:
        sections.append(
            "Will be updated:\n"
            + "\n".join(
                f"- [{hit.label}]({hit.edit_url}) ({hit.resource_type})"
                for hit in auto_hits
            )
        )
    if manual_hits:
        sections.append(
            "Manual update required:\n"
            + "\n".join(
                f"- [{hit.label}]({hit.edit_url}) "
                f"({manual_reference_reason(hit)})"
                for hit in manual_hits
            )
        )

    preview = "\n\n".join(sections) if sections else "No changes will be applied."
    return preview, unique


async def async_apply_replace(
    hass: HomeAssistant,
    hits: list[ReferenceHit],
    old_entity_id: str,
    new_entity_id: str,
) -> ReplaceResult:
    """Apply replacements for all reference hits."""
    result = ReplaceResult()
    _, unique = await async_preview_replace(hass, hits, old_entity_id, new_entity_id)

    for hit in unique.values():
        try:
            changed = await _replace_hit(hass, hit, old_entity_id, new_entity_id)
        except Exception as err:  # noqa: BLE001 - collect per-resource failures
            _LOGGER.exception("Auto-Replace failed for %s", hit.label)
            result.failed.append(f"{hit.label}: {err}")
            continue
        if changed:
            result.updated.append(hit.label)
        else:
            reason = manual_reference_reason(hit) if not hit.auto_replaceable else hit.resource_type
            result.skipped.append(f"{hit.label} ({reason})")

    return result


async def _replace_hit(
    hass: HomeAssistant,
    hit: ReferenceHit,
    old_entity_id: str,
    new_entity_id: str,
) -> bool:
    """Replace references for a single hit."""
    if hit.resource_type == "automation":
        return await _replace_entity_component_config(
            hass, automation.DOMAIN, hit.resource_id, old_entity_id, new_entity_id
        )
    if hit.resource_type == "script":
        return await _replace_entity_component_config(
            hass, script.DOMAIN, hit.resource_id, old_entity_id, new_entity_id
        )
    if hit.resource_type == "scene":
        return await _replace_entity_component_config(
            hass, scene.DOMAIN, hit.resource_id, old_entity_id, new_entity_id
        )
    if hit.resource_type == "dashboard":
        return await _replace_dashboard(
            hass, hit.resource_id, old_entity_id, new_entity_id
        )
    if hit.resource_type == "group":
        return await _replace_group(hass, hit, old_entity_id, new_entity_id)
    if hit.resource_type == "helper":
        return False
    return False


async def _replace_entity_component_config(
    hass: HomeAssistant,
    domain: str,
    resource_id: str,
    old_entity_id: str,
    new_entity_id: str,
) -> bool:
    """Replace entity IDs inside an automation/script/scene config."""
    instances = hass.data.get(DATA_INSTANCES, {})
    if domain not in instances:
        return False

    component = instances[domain]
    for entity in component.entities:
        if str(getattr(entity, "unique_id", "")) != str(resource_id):
            continue
        raw_config = getattr(entity, "raw_config", None)
        if not raw_config:
            return False
        new_config, count = await deep_replace_entity_ids(
            hass, dict(raw_config), old_entity_id, new_entity_id
        )
        if count == 0:
            return False
        if domain == automation.DOMAIN:
            from homeassistant.components.automation import config as automation_config

            async_update = getattr(automation_config, "async_update", None)
            if callable(async_update):
                await async_update(hass, resource_id, new_config)
            else:
                await _async_update_automation_via_config_view(hass, resource_id, new_config)
            return True
        if domain == script.DOMAIN:
            from homeassistant.components.script import config as script_config

            async_update = getattr(script_config, "async_update", None)
            if callable(async_update):
                await async_update(hass, resource_id, new_config)
            else:
                await _async_update_script_via_config_view(hass, resource_id, new_config)
            return True
        if domain == scene.DOMAIN:
            try:
                from homeassistant.components.scene import config as scene_config
            except ImportError:
                from homeassistant.components.homeassistant.scene import (
                    config as scene_config,
                )

            async_update = getattr(scene_config, "async_update", None)
            if callable(async_update):
                await async_update(hass, resource_id, new_config)
            else:
                await _async_update_scene_via_config_view(hass, resource_id, new_config)
            return True
    return False


async def _async_write_yaml_config(hass: HomeAssistant, rel_path: str, data: dict | list) -> None:
    """Write a YAML config file atomically."""
    contents = dump(data)
    await hass.async_add_executor_job(write_utf8_file_atomic, hass.config.path(rel_path), contents)


async def _async_update_automation_via_config_view(
    hass: HomeAssistant, automation_id: str, new_config: dict[str, Any]
) -> None:
    """Update an automation using the config editor backend."""
    from homeassistant.components.automation import DOMAIN as AUTOMATION_DOMAIN
    from homeassistant.components.automation.config import async_validate_config_item
    from homeassistant.components.config.automation import EditAutomationConfigView
    from homeassistant.config import AUTOMATION_CONFIG_PATH
    from homeassistant.const import CONF_ID, SERVICE_RELOAD
    from homeassistant.helpers import config_validation as cv

    view = EditAutomationConfigView(
        AUTOMATION_DOMAIN,
        "config",
        AUTOMATION_CONFIG_PATH,
        cv.string,
        data_validator=async_validate_config_item,
    )
    current = await view.read_config(hass)
    view._write_value(hass, current, automation_id, new_config)
    await _async_write_yaml_config(hass, AUTOMATION_CONFIG_PATH, current)
    await hass.services.async_call(
        AUTOMATION_DOMAIN, SERVICE_RELOAD, {CONF_ID: automation_id}, blocking=True
    )


async def _async_update_script_via_config_view(
    hass: HomeAssistant, script_id: str, new_config: dict[str, Any]
) -> None:
    """Update a script using the config editor backend."""
    from homeassistant.components.config.script import EditScriptConfigView
    from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN
    from homeassistant.components.script.config import async_validate_config_item
    from homeassistant.config import SCRIPT_CONFIG_PATH
    from homeassistant.const import SERVICE_RELOAD
    from homeassistant.helpers import config_validation as cv

    view = EditScriptConfigView(
        SCRIPT_DOMAIN,
        "config",
        SCRIPT_CONFIG_PATH,
        cv.slug,
        data_validator=async_validate_config_item,
    )
    current = await view.read_config(hass)
    view._write_value(hass, current, script_id, new_config)
    await _async_write_yaml_config(hass, SCRIPT_CONFIG_PATH, current)
    await hass.services.async_call(SCRIPT_DOMAIN, SERVICE_RELOAD, blocking=True)


async def _async_update_scene_via_config_view(
    hass: HomeAssistant, scene_id: str, new_config: dict[str, Any]
) -> None:
    """Update a scene using the config editor backend."""
    from homeassistant.components.config.scene import EditSceneConfigView, PLATFORM_SCHEMA
    from homeassistant.components.scene import DOMAIN as SCENE_DOMAIN
    from homeassistant.config import SCENE_CONFIG_PATH
    from homeassistant.const import SERVICE_RELOAD
    from homeassistant.helpers import config_validation as cv

    view = EditSceneConfigView(
        SCENE_DOMAIN,
        "config",
        SCENE_CONFIG_PATH,
        cv.string,
        data_schema=PLATFORM_SCHEMA,
    )
    current = await view.read_config(hass)
    view._write_value(hass, current, scene_id, new_config)
    await _async_write_yaml_config(hass, SCENE_CONFIG_PATH, current)
    await hass.services.async_call(SCENE_DOMAIN, SERVICE_RELOAD, blocking=True)


async def _replace_dashboard(
    hass: HomeAssistant,
    url_path: str,
    old_entity_id: str,
    new_entity_id: str,
) -> bool:
    """Replace entity IDs in a Lovelace dashboard."""
    if LOVELACE_DOMAIN not in hass.data:
        return False
    dashboard = hass.data[LOVELACE_DOMAIN].dashboards.get(url_path)
    if dashboard is None:
        return False
    try:
        config = await dashboard.async_load(force=False)
    except ConfigNotFound:
        return False
    new_config, count = await deep_replace_entity_ids(
        hass, config, old_entity_id, new_entity_id
    )
    if count == 0:
        return False
    await dashboard.async_save(new_config)
    return True


async def _replace_group(
    hass: HomeAssistant,
    hit: ReferenceHit,
    old_entity_id: str,
    new_entity_id: str,
) -> bool:
    """Replace a member entity ID in a group via service call."""
    entity_id = hit.extra.get("entity_id", hit.resource_id)
    state = hass.states.get(entity_id)
    if state is None:
        return False
    members = list(state.attributes.get("entity_id", []))
    if old_entity_id not in members:
        return False
    new_members = [
        new_entity_id if member == old_entity_id else member for member in members
    ]
    await hass.services.async_call(
        "group",
        "set",
        {"object_id": entity_id.split(".", 1)[-1], "entities": new_members},
        blocking=True,
    )
    return True
