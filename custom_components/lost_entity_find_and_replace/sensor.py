"""Sensor platform for Lost Entity Find And Replace."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ENTITY_LOST_ENTITIES
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


class LostEntitiesSensor(SensorEntity):
    """Sensor reporting the number of lost entity references."""

    _attr_has_entity_name = True
    _attr_name = "Lost Entities"
    _attr_native_unit_of_measurement = "entities"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:database-search"

    def __init__(self, manager: EntityFinderManager, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        self._manager = manager
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{ENTITY_LOST_ENTITIES}"
        self._attr_native_value = manager.get_lost_count()

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
        count = self._manager.get_lost_count()
        if count != self._attr_native_value:
            self._attr_native_value = count
            self.async_write_ha_state()
