"""Sensor platform for Lost Entity Find And Replace."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ENTITY_IGNORED_LOST_ENTITIES, ENTITY_LOST_ENTITIES
from .manager import EntityFinderManager

if TYPE_CHECKING:
    from .entity_platform import EntityFinderEntityPlatform


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lost Entity Find And Replace sensor entities."""
    manager: EntityFinderManager = entry.runtime_data
    platform: EntityFinderEntityPlatform = manager.entity_platform
    platform.async_setup_sensor(async_add_entities)


class _BaseCountSensor(SensorEntity):
    """Base class for count sensors driven by manager updates."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "entities"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, manager: EntityFinderManager, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        self._manager = manager
        self._entry = entry
        self._attr_native_value = self._get_count()

    @property
    def device_info(self) -> None:
        """Return None so the entity is not grouped under a device."""
        return None

    async def async_added_to_hass(self) -> None:
        """Register for manager updates."""
        await super().async_added_to_hass()
        self.async_on_remove(self._manager.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        """Handle manager state updates."""
        count = self._get_count()
        if count != self._attr_native_value:
            self._attr_native_value = count
            self.async_write_ha_state()

    def _get_count(self) -> int:
        """Return current count for the specific sensor."""
        raise NotImplementedError


class LostEntitiesSensor(_BaseCountSensor):
    """Sensor reporting the number of active lost entity references."""

    _attr_name = "Lost Entities"
    _attr_icon = "mdi:database-search"

    def __init__(self, manager: EntityFinderManager, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{entry.entry_id}_{ENTITY_LOST_ENTITIES}"

    def _get_count(self) -> int:
        """Return current lost-entities count."""
        return self._manager.get_lost_count()


class IgnoredLostEntitiesSensor(_BaseCountSensor):
    """Sensor reporting the number of ignored lost entity references."""

    _attr_name = "Ignored Lost Entities"
    _attr_icon = "mdi:eye-off-outline"

    def __init__(self, manager: EntityFinderManager, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{entry.entry_id}_{ENTITY_IGNORED_LOST_ENTITIES}"

    def _get_count(self) -> int:
        """Return current ignored lost-entities count."""
        return self._manager.get_ignored_lost_count()
