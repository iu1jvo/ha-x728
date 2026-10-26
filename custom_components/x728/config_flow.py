"""Config flow for Geekworm X728 UPS integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class X728ConfigFlow(  # pylint: disable=abstract-method
    config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle the initial config flow for X728."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            # Test connection to daemon
            ok, err = await _test_connection(self.hass, host, port)
            if ok:
                await self.async_set_unique_id(f"x728_{host}_{port}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"X728 UPS ({host}:{port})",
                    data=user_input,
                )
            errors["base"] = err

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(int, vol.Range(min=5, max=300)),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,  # pylint: disable=unused-argument
    ) -> X728OptionsFlow:
        """Return the options flow handler."""
        return X728OptionsFlow()


class X728OptionsFlow(config_entries.OptionsFlow):
    """Handle options for X728 (editable after setup)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.data

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST, default=current.get(CONF_HOST, DEFAULT_HOST)
                ): str,
                vol.Required(
                    CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)
                ): int,
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=5, max=300)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)


async def _test_connection(
    hass: HomeAssistant, host: str, port: int
) -> tuple[bool, str]:
    """Try to reach the daemon and return (success, error_key)."""
    url = f"http://{host}:{port}/api/x728"
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(5):
            async with session.get(url) as resp:
                if resp.status == 200:
                    return True, ""
                return False, "cannot_connect"
    except (aiohttp.ClientError, TimeoutError):
        return False, "cannot_connect"
