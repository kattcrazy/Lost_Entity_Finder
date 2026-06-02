"""Button platform for Entity Finder."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ENTITY_AUTO_REPLACE_ALL,
    ENTITY_IGNORE_ALL,
    ENTITY_RESTORE_IGNORED,
)
from .manager import EntityFinderManager

if TYPE_CHECKING:
    from .entity_platform import EntityFinderEntityPlatform


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Entity Finder button entities."""
    manager: EntityFinderManager = entry.runtime_data
    platform: EntityFinderEntityPlatform = manager.entity_platform
    platform.async_setup_buttons(async_add_entities)


class EntityFinderButton(ButtonEntity):
    """Base class for Entity Finder buttons."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, manager: EntityFinderManager, entry: ConfigEntry) -> None:
        """Initialize button."""
        self._manager = manager
        self._entry = entry

    @property
    def device_info(self) -> None:
        """Return None so the entity is not grouped under a device."""
        return None


class IgnoreAllButton(EntityFinderButton):
    """Button to ignore all active lost entity repairs."""

    _attr_name = "Ignore All"
    _attr_icon = "mdi:eye-off-outline"

    def __init__(self, manager: EntityFinderManager, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{entry.entry_id}_{ENTITY_IGNORE_ALL}"

    async def async_press(self) -> None:
        """Ignore all active lost entity repairs."""
        await self._manager.async_ignore_all()


class RestoreIgnoredButton(EntityFinderButton):
    """Button to restore all ignored lost entity repairs."""

    _attr_name = "Restore Ignored"
    _attr_icon = "mdi:restore"

    def __init__(self, manager: EntityFinderManager, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{entry.entry_id}_{ENTITY_RESTORE_IGNORED}"

    async def async_press(self) -> None:
        """Restore all ignored lost entity repairs."""
        await self._manager.async_restore_ignored()


class AutoReplaceAllButton(EntityFinderButton):
    """Button to auto-replace all stale references."""

    _attr_name = "Auto-Replace All"
    _attr_icon = "mdi:swap-horizontal"

    def __init__(self, manager: EntityFinderManager, entry: ConfigEntry) -> None:
        """Initialize button."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{entry.entry_id}_{ENTITY_AUTO_REPLACE_ALL}"

    async def async_press(self) -> None:
        """Replace all stale references when bulk fix is enabled."""
        await self._manager.async_auto_replace_all()
