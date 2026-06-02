"""Config flow for Lost Entity Find And Replace."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_ENABLE_BULK_FIX, DEFAULT_ENABLE_BULK_FIX, DOMAIN


class EntityFinderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lost Entity Find And Replace."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="Lost Entity Find & Replace",
                data={
                    CONF_ENABLE_BULK_FIX: user_input.get(
                        CONF_ENABLE_BULK_FIX, DEFAULT_ENABLE_BULK_FIX
                    )
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ENABLE_BULK_FIX, default=DEFAULT_ENABLE_BULK_FIX
                    ): bool
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> EntityFinderOptionsFlow:
        """Get the options flow."""
        return EntityFinderOptionsFlow()


class EntityFinderOptionsFlow(config_entries.OptionsFlow):
    """Handle Lost Entity Find And Replace options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage Lost Entity Find And Replace options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.data.get(
            CONF_ENABLE_BULK_FIX, DEFAULT_ENABLE_BULK_FIX
        )
        if self.config_entry.options:
            current = self.config_entry.options.get(CONF_ENABLE_BULK_FIX, current)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Optional(CONF_ENABLE_BULK_FIX, default=current): bool}
            ),
        )


def get_enable_bulk_fix(hass: HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
    """Return whether bulk fix is enabled for the config entry."""
    if entry.options and CONF_ENABLE_BULK_FIX in entry.options:
        return bool(entry.options[CONF_ENABLE_BULK_FIX])
    return bool(entry.data.get(CONF_ENABLE_BULK_FIX, DEFAULT_ENABLE_BULK_FIX))
