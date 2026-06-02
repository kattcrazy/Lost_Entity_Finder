"""Entity Finder integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from . import repairs  # noqa: F401
from .const import DOMAIN
from .entity_platform import EntityFinderEntityPlatform
from .manager import EntityFinderManager

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Entity Finder."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Entity Finder from a config entry."""
    manager = EntityFinderManager(hass, entry)
    await manager.async_setup()
    manager.entity_platform = EntityFinderEntityPlatform(hass, entry, manager)
    entry.runtime_data = manager
    hass.data[DOMAIN][entry.entry_id] = manager
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button"])
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates."""
    manager: EntityFinderManager = entry.runtime_data
    await manager.entity_platform.async_refresh_auto_replace()
    await manager.async_trigger_rescan()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Entity Finder."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ["sensor", "button"]
    )
    if not unload_ok:
        return False
    manager: EntityFinderManager = entry.runtime_data
    await manager.async_unload()
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
