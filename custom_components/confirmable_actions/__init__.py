"""Send actionable notifications to notification group helper members."""

import asyncio

import voluptuous as vol

from homeassistant.components.mobile_app.const import DATA_NOTIFY
from homeassistant.components.mobile_app.util import (
    get_notify_service,
    webhook_id_from_device_id,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er

DOMAIN = "confirmable_actions"

SEND_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("message"): cv.string,
        vol.Optional("title"): cv.string,
        vol.Optional("data"): dict,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the group notification action."""

    async def send_notification(call: ServiceCall) -> None:
        registry = er.async_get(hass)
        devices = set()
        visiting = set()
        recipients = []

        def resolve(entity_id: str) -> None:
            entry = registry.async_get(entity_id)
            if entry is None or entry.domain != "notify":
                raise HomeAssistantError(f"Unknown notification entity: {entity_id}")
            if entry.platform == "group":
                if entity_id in visiting:
                    raise HomeAssistantError(f"Notification group cycle: {entity_id}")
                state = hass.states.get(entity_id)
                members = state.attributes.get("entity_id") if state else None
                if not isinstance(members, (list, tuple)) or not members:
                    raise HomeAssistantError(f"Notification group has no members: {entity_id}")
                visiting.add(entity_id)
                for member in members:
                    resolve(member)
                visiting.remove(entity_id)
                return
            if entry.platform != "mobile_app" or not entry.device_id:
                raise HomeAssistantError(
                    f"Notification group member is not a Companion app device: {entity_id}"
                )
            if entry.device_id in devices:
                return
            webhook_id = webhook_id_from_device_id(hass, entry.device_id)
            service = (
                get_notify_service(hass, webhook_id)
                if webhook_id and hass.data.get("mobile_app", {}).get(DATA_NOTIFY)
                else None
            )
            if not service:
                raise HomeAssistantError(
                    f"No mobile app notification action for {entity_id}"
                )
            devices.add(entry.device_id)
            recipients.append((service, webhook_id))

        group_id = call.data["entity_id"]
        group_entry = registry.async_get(group_id)
        if group_entry is None or group_entry.platform != "group":
            raise HomeAssistantError(f"Not a notification group helper: {group_id}")
        resolve(group_id)
        calls = []
        for service, webhook_id in recipients:
            payload = {key: value for key, value in call.data.items() if key != "entity_id"}
            payload["target"] = webhook_id
            calls.append(
                hass.services.async_call(
                    "notify", service, payload, blocking=True, context=call.context
                )
            )
        results = await asyncio.gather(*calls, return_exceptions=True)
        failures = [result for result in results if isinstance(result, Exception)]
        if failures:
            raise HomeAssistantError(
                f"Failed to notify {len(failures)} member(s) of {group_id}: "
                + "; ".join(str(error) for error in failures)
            )

    hass.services.async_register(
        DOMAIN, "send_notification", send_notification, schema=SEND_SCHEMA
    )
    return True
