"""Lost Entity Find And Replace integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from . import repairs  # noqa: F401
from .const import DOMAIN
from .entity_platform import EntityFinderEntityPlatform
from .manager import EntityFinderManager
from .scanner import async_scan_tracked_references
from .util import format_references_for_repair

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SERVICE_FIND_REFERENCES = "find_entity_references"
SERVICE_SCHEMA_FIND_REFERENCES = vol.Schema({vol.Required("entity_id"): cv.entity_id})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Lost Entity Find And Replace."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Lost Entity Find And Replace from a config entry."""
    manager = EntityFinderManager(hass, entry)
    await manager.async_setup()
    manager.entity_platform = EntityFinderEntityPlatform(hass, entry, manager)
    entry.runtime_data = manager
    hass.data[DOMAIN][entry.entry_id] = manager
    if not hass.services.has_service(DOMAIN, SERVICE_FIND_REFERENCES):
        async def _handle_service(call: ServiceCall) -> None:
            await _async_handle_find_references_service(hass, call)

        hass.services.async_register(
            DOMAIN,
            SERVICE_FIND_REFERENCES,
            _handle_service,
            schema=SERVICE_SCHEMA_FIND_REFERENCES,
        )
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button"])
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates."""
    manager: EntityFinderManager = entry.runtime_data
    await manager.entity_platform.async_refresh_auto_replace()
    await manager.async_trigger_rescan()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Lost Entity Find And Replace."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ["sensor", "button"]
    )
    if not unload_ok:
        return False
    manager: EntityFinderManager = entry.runtime_data
    await manager.async_unload()
    hass.data[DOMAIN].pop(entry.entry_id, None)
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_FIND_REFERENCES)
    return True


async def _async_handle_find_references_service(
    hass: HomeAssistant, call: ServiceCall
) -> None:
    """Scan and show all locations that reference an entity ID."""
    entity_id = str(call.data["entity_id"]).lower()
    hits_by_entity = await async_scan_tracked_references(hass, {entity_id})
    hits = hits_by_entity.get(entity_id, [])
    if not hits:
        raise HomeAssistantError(
            f"No references found for '{entity_id}' in supported scan targets."
        )

    references_md, manual_note = format_references_for_repair(hits)
    message = f"Found {len(hits)} reference(s) for `{entity_id}`:\n\n{references_md}"
    if manual_note:
        message += f"\n\n{manual_note}"

    from homeassistant.components.persistent_notification import async_create

    async_create(
        hass,
        message,
        title=f"{DOMAIN}: {entity_id}",
        notification_id=f"{DOMAIN}_find_refs_{entity_id}",
    )
