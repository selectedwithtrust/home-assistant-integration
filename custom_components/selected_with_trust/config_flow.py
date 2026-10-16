"""Config flow: find a business by name, or paste its page link."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelectorMode,
    TextSelector,
)

try:  # Home Assistant 2026.10+ ships probatio, a drop-in for voluptuous
    import probatio as vol
except ImportError:  # pragma: no cover - older Home Assistant
    import voluptuous as vol  # type: ignore[no-redef,unused-ignore]

from .api import (
    BusinessSummary,
    SwtClient,
    SwtConnectionError,
    SwtNotFoundError,
    SwtRateLimitError,
    extract_business_id,
)
from .const import (
    CONF_BUSINESS_ID,
    CONF_BUSINESS_NAME,
    CONF_CLOSING_SOON_MINUTES,
    DEFAULT_CLOSING_SOON_MINUTES,
    DOMAIN,
)

CONF_QUERY = "query"
CONF_PICK = "business"


class SwtConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle adding or changing a followed business."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return SwtOptionsFlow()

    def __init__(self) -> None:
        """Initialise."""
        self._results: list[BusinessSummary] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a name or a pasted link."""
        return await self._search_step("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Point the entry at a different business."""
        return await self._search_step("reconfigure", user_input)

    async def _search_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            query = user_input[CONF_QUERY].strip()
            client = SwtClient(async_get_clientsession(self.hass))
            try:
                if business_id := extract_business_id(query):
                    info = await client.get_opening_info(business_id)
                    return await self._finish(business_id, info["name"])
                self._results = await client.search(query)
            except SwtNotFoundError:
                errors["base"] = "not_found"
            except SwtRateLimitError:
                errors["base"] = "rate_limited"
            except SwtConnectionError:
                errors["base"] = "cannot_connect"
            else:
                if self._results:
                    return await self.async_step_pick()
                errors["base"] = "no_results"

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required(CONF_QUERY): TextSelector()}),
            errors=errors,
        )

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose one of the search results."""
        if user_input is not None:
            chosen = next(r for r in self._results if r["id"] == user_input[CONF_PICK])
            return await self._finish(chosen["id"], chosen["name"])

        options = [
            SelectOptionDict(
                value=r["id"], label=f"{r['name']} ({r['city']})" if r["city"] else r["name"]
            )
            for r in self._results
        ]
        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PICK): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.LIST
                        )
                    )
                }
            ),
        )

    async def _finish(self, business_id: str, name: str) -> ConfigFlowResult:
        await self.async_set_unique_id(business_id)
        data = {CONF_BUSINESS_ID: business_id, CONF_BUSINESS_NAME: name}
        self._abort_if_unique_id_configured()
        if self.source == "reconfigure":
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                unique_id=business_id,
                title=name,
                data=data,
            )
        return self.async_create_entry(title=name, data=data)


class SwtOptionsFlow(OptionsFlow):
    """Configure how early "closing soon" turns on."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(
            CONF_CLOSING_SOON_MINUTES, DEFAULT_CLOSING_SOON_MINUTES
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CLOSING_SOON_MINUTES, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=5, max=240, step=5, unit_of_measurement="min",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )
