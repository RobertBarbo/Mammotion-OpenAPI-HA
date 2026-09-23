"""Credential configuration and reauthentication for Mammotion OpenAPI."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api.client import MammotionApiClient
from .api.exceptions import (
    MammotionApiError,
    MammotionAuthenticationError,
    MammotionMalformedResponseError,
    MammotionTransportError,
)
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, DOMAIN

_CREDENTIAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
        vol.Required(CONF_CLIENT_SECRET): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


class MammotionOpenAPIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up one entry per Mammotion developer credential set."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for credentials and verify that they can discover mowers."""
        return await self._async_credentials_step("user", user_input)

    async def async_step_reauth(self, _entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication without pre-filling stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate replacement credentials and reload the existing entry."""
        return await self._async_credentials_step("reauth_confirm", user_input)

    async def _async_credentials_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client_id = user_input[CONF_CLIENT_ID]
            reauth_entry = self._get_reauth_entry() if step_id == "reauth_confirm" else None
            if any(
                entry.data.get(CONF_CLIENT_ID) == client_id
                and (reauth_entry is None or entry.entry_id != reauth_entry.entry_id)
                for entry in self._async_current_entries()
            ):
                return self.async_abort(reason="already_configured")

            client = MammotionApiClient(
                async_get_clientsession(self.hass),
                client_id,
                user_input[CONF_CLIENT_SECRET],
            )
            try:
                mowers = await client.get_mowers()
            except MammotionAuthenticationError:
                errors["base"] = "invalid_auth"
            except MammotionTransportError:
                errors["base"] = "cannot_connect"
            except MammotionMalformedResponseError:
                errors["base"] = "invalid_response"
            except MammotionApiError:
                errors["base"] = "api_error"
            except Exception:
                # Do not include exception text: remote responses may echo input.
                errors["base"] = "unknown"
            else:
                if not mowers:
                    errors["base"] = "no_mowers"
                elif reauth_entry is not None:
                    return self.async_update_reload_and_abort(
                        reauth_entry,
                        data_updates={
                            CONF_CLIENT_ID: client_id,
                            CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
                        },
                    )
                else:
                    return self.async_create_entry(
                        title="Mammotion OpenAPI",
                        data={
                            CONF_CLIENT_ID: client_id,
                            CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
                        },
                    )

        return self.async_show_form(step_id=step_id, data_schema=_CREDENTIAL_SCHEMA, errors=errors)
