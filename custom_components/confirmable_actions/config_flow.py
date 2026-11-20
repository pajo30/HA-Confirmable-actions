"""Config flow for Confirmable Actions."""

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from . import DOMAIN


class ConfirmableActionsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a single Confirmable Actions entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setup."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Confirmable Actions", data={})
        return self.async_show_form(step_id="user")
