"""Config flow for the SmartThinQ Hybrid integration.

Both the ThinQ Web (wideq) login and the official PAT credentials are
required; the config entry is only created once both have been
successfully verified. If either step fails, the user is shown the
relevant error and asked to try again - no partially configured entry is
ever created.
"""

from __future__ import annotations

import logging
from typing import Any
import uuid

import voluptuous as vol
from thinqconnect import ThinQAPIException
from thinqconnect.thinq_api import ThinQApi

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    CountrySelector,
    CountrySelectorConfig,
)

from .const import (
    CONF_PAT_ACCESS_TOKEN,
    CONF_PAT_CLIENT_ID,
    CONF_PAT_COUNTRY,
    CONF_WIDEQ_CLIENT_ID,
    CONF_WIDEQ_LANGUAGE,
    CONF_WIDEQ_OAUTH_URL,
    CONF_WIDEQ_REFRESH_TOKEN,
    CONF_WIDEQ_REGION,
    DEFAULT_COUNTRY,
    DEFAULT_LANGUAGE,
    DOMAIN,
)
from .wideq.core_async import ClientAsync
from .wideq.core_exceptions import AuthenticationError

_LOGGER = logging.getLogger(__name__)

CLIENT_ID_PREFIX = "smartthinq-hybrid"


class SmartThinqHybridFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle the SmartThinQ Hybrid config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._wideq_refresh_token: str | None = None
        self._wideq_oauth_url: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: ThinQ Web login (wideq), used for AC fan/swing control
        and the washer's current-course sensor."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input["username"]
            password = user_input["password"]

            session = async_get_clientsession(self.hass)
            try:
                auth_info = await ClientAsync.auth_info_from_user_login(
                    username,
                    password,
                    country=DEFAULT_COUNTRY,
                    language=DEFAULT_LANGUAGE,
                    aiohttp_session=session,
                )
            except AuthenticationError as exc:
                _LOGGER.warning("ThinQ Web login failed: %s", exc)
                errors["base"] = "invalid_auth"
            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error during ThinQ Web login")
                errors["base"] = "unknown"
            else:
                self._wideq_refresh_token = auth_info.get("refresh_token")
                self._wideq_oauth_url = auth_info.get("oauth_url")
                if not self._wideq_refresh_token:
                    errors["base"] = "invalid_auth"
                else:
                    return await self.async_step_pat()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("username"): str,
                    vol.Required("password"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_pat(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: official PAT credentials, used as the primary data
        source for the air conditioner, dehumidifier and washer."""
        errors: dict[str, str] = {}

        if user_input is not None:
            access_token = user_input[CONF_PAT_ACCESS_TOKEN]
            country = user_input[CONF_PAT_COUNTRY]
            pat_client_id = f"{CLIENT_ID_PREFIX}-{uuid.uuid4()}"

            session = async_get_clientsession(self.hass)
            thinq_api = ThinQApi(
                session=session,
                access_token=access_token,
                country_code=country,
                client_id=pat_client_id,
            )
            try:
                await thinq_api.async_get_device_list()
            except ThinQAPIException as exc:
                _LOGGER.warning("PAT validation failed: %s", exc)
                errors["base"] = "pat_invalid"
            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error validating PAT")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="SmartThinQ Hybrid",
                    data={
                        CONF_WIDEQ_REFRESH_TOKEN: self._wideq_refresh_token,
                        CONF_WIDEQ_OAUTH_URL: self._wideq_oauth_url,
                        CONF_WIDEQ_REGION: DEFAULT_COUNTRY,
                        CONF_WIDEQ_LANGUAGE: DEFAULT_LANGUAGE,
                        CONF_WIDEQ_CLIENT_ID: None,
                        CONF_PAT_ACCESS_TOKEN: access_token,
                        CONF_PAT_CLIENT_ID: pat_client_id,
                        CONF_PAT_COUNTRY: country,
                    },
                )

        return self.async_show_form(
            step_id="pat",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PAT_ACCESS_TOKEN): str,
                    vol.Required(
                        CONF_PAT_COUNTRY, default=DEFAULT_COUNTRY
                    ): CountrySelector(CountrySelectorConfig()),
                }
            ),
            errors=errors,
        )
