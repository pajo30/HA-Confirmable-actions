"""Exercise the blueprint with Home Assistant's script runner."""

import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.components.automation.config import (
    AUTOMATION_BLUEPRINT_SCHEMA,
    PLATFORM_SCHEMA,
)
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.components.mobile_app import device_action
from homeassistant.components.mobile_app.const import DATA_DEVICES, DATA_NOTIFY
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import trigger as trigger_helper
from homeassistant.helpers.script import Script, async_validate_actions_config
from homeassistant.loader import async_setup
from homeassistant.util.yaml import load_yaml

from custom_components.confirmable_actions import async_setup as setup_group_action


BLUEPRINT_PATH = (
    Path(__file__).resolve().parents[1]
    / "blueprints/automation/confirmable_notification.yaml"
)


class BlueprintTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config_dir = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.config_dir.name)
        async_setup(self.hass)
        if hasattr(dr, "async_setup"):
            dr.async_setup(self.hass)
        await dr.async_load(self.hass)
        if hasattr(trigger_helper, "async_setup"):
            await trigger_helper.async_setup(self.hass)
        self.notifications = []
        self.selected = []
        self.scripts = []

        async def notify(call):
            self.notifications.append(call.data)

        async def selected(call):
            self.selected.append(call.data["button"])

        self.hass.services.async_register("notify", "family", notify)
        self.hass.services.async_register("test", "selected", selected)

    async def asyncTearDown(self):
        for script in self.scripts:
            await script.async_stop()
        await self.hass.async_stop()
        self.config_dir.cleanup()

    async def start_request(self, **overrides):
        blueprint = Blueprint(
            load_yaml(str(BLUEPRINT_PATH)), schema=AUTOMATION_BLUEPRINT_SCHEMA
        )
        inputs = {
            "notification_trigger": [{"trigger": "event", "event_type": "test"}],
            "notification_group": "notify.family",
            "notification_device": "a" * 32,
            "notification_message": "Confirm?",
            "confirmation_actions": [
                {"action": "test.selected", "data": {"button": "yes"}}
            ],
            "reminder_delay": {"seconds": 0},
            "response_timeout": {"seconds": 5},
            **overrides,
        }
        configured = BlueprintInputs(
            blueprint,
            {"use_blueprint": {"path": str(BLUEPRINT_PATH), "input": inputs}},
        )
        configured.validate()
        config = PLATFORM_SCHEMA(configured.async_substitute())
        with (
            patch.object(dr.async_get(self.hass), "async_get", return_value=Mock()),
            patch(
                "homeassistant.components.device_automation.helpers.async_get_device_automation_platform",
                new=AsyncMock(return_value=device_action),
            ),
        ):
            sequence = await async_validate_actions_config(self.hass, config["actions"])
        script = Script(self.hass, sequence, "Confirm", "automation")
        self.scripts.append(script)
        return asyncio.create_task(script.async_run(context=Context()))

    async def wait_for_message(self, count):
        async with asyncio.timeout(5):
            while len(
                [n for n in self.notifications if n["message"] != "clear_notification"]
            ) < count:
                await asyncio.sleep(0.01)
        return [
            n for n in self.notifications if n["message"] != "clear_notification"
        ][count - 1]

    async def respond(self, action, device="phone_one"):
        self.hass.bus.async_fire(
            "mobile_app_notification_action",
            {"action": action, "device_id": device},
        )
        await asyncio.sleep(0.01)

    async def test_group_custom_buttons_and_hidden_defaults(self):
        for button in (1, 2):
            with self.subTest(button=button):
                self.notifications.clear()
                self.selected.clear()
                task = await self.start_request(
                    deny_label="",
                    reminder_label="",
                    extra_action_1_label="First",
                    extra_action_2_label="Second",
                    extra_action_1=[
                        {"action": "test.selected", "data": {"button": "first"}}
                    ],
                    extra_action_2=[
                        {"action": "test.selected", "data": {"button": "second"}}
                    ],
                )
                message = await self.wait_for_message(1)
                buttons = message["data"]["actions"]
                self.assertEqual([b["title"] for b in buttons], ["Yes", "First", "Second"])
                await self.respond(buttons[button]["action"], "phone_two")
                await asyncio.wait_for(task, 5)
                self.assertEqual(self.selected, ["first" if button == 1 else "second"])
                self.assertEqual(self.notifications[-1]["message"], "clear_notification")
                self.assertEqual(
                    self.notifications[-1]["data"]["tag"], message["data"]["tag"]
                )

    async def test_reminder_templates_and_response_isolation(self):
        self.hass.states.async_set("light.test", "on")
        task = await self.start_request(
            notification_title="{{ states('light.test') }}",
            notification_message=(
                "{% if is_state('light.test', 'on') %}Turn off?{% else %}Done{% endif %}"
            ),
        )
        first = await self.wait_for_message(1)
        other_task = await self.start_request()
        other = await self.wait_for_message(2)
        self.hass.states.async_set("light.test", "off")
        await self.respond(first["data"]["actions"][2]["action"])
        second = await self.wait_for_message(3)
        self.assertEqual((first["title"], first["message"]), ("on", "Turn off?"))
        self.assertEqual((second["title"], second["message"]), ("off", "Done"))
        self.assertEqual(first["data"]["tag"], second["data"]["tag"])
        self.assertNotEqual(
            first["data"]["actions"][0]["action"], second["data"]["actions"][0]["action"]
        )
        await self.respond(first["data"]["actions"][0]["action"])
        self.assertFalse(task.done())
        self.assertFalse(other_task.done())
        await self.respond(second["data"]["actions"][0]["action"], "phone_two")
        await asyncio.wait_for(task, 5)
        self.assertFalse(other_task.done())
        await self.respond(other["data"]["actions"][1]["action"])
        await asyncio.wait_for(other_task, 5)
        self.assertEqual(self.selected, ["yes"])

    async def test_existing_device_target(self):
        from homeassistant.components.mobile_app import device_action

        async def notify_device(hass, config, variables, context):
            from homeassistant.helpers.template import render_complex

            self.notifications.append(
                {
                    key: render_complex(config[key], variables)
                    for key in ("title", "message", "data")
                    if key in config
                }
            )

        with (
            patch.object(
                device_action,
                "async_call_action_from_config",
                new=AsyncMock(side_effect=notify_device),
            ) as notify,
            patch(
                "homeassistant.components.device_automation.action.async_get_device_automation_platform",
                new=AsyncMock(return_value=device_action),
            ),
        ):
            task = await self.start_request(
                notification_group="", notification_device="a" * 32
            )
            message = await self.wait_for_message(1)
            await self.respond(message["data"]["actions"][0]["action"])
            await asyncio.wait_for(task, 5)
            self.assertEqual(self.selected, ["yes"])
            self.assertEqual(notify.await_count, 2)
            self.assertEqual(self.notifications[-1]["message"], "clear_notification")

    async def test_timeout_clears_without_actions(self):
        task = await self.start_request(response_timeout={"milliseconds": 50})
        await asyncio.wait_for(task, 5)
        self.assertEqual(self.selected, [])
        self.assertEqual(self.notifications[-1]["message"], "clear_notification")

    async def test_group_helper_sends_actions_and_clears_all_members(self):
        await setup_group_action(self.hass, {})
        entries = {
            "notify.family": Mock(domain="notify", platform="group"),
            "notify.nested": Mock(domain="notify", platform="group"),
            "notify.phone_one": Mock(domain="notify", platform="mobile_app", device_id="one"),
            "notify.phone_two": Mock(domain="notify", platform="mobile_app", device_id="two"),
        }
        self.hass.states.async_set(
            "notify.family", "unknown", {"entity_id": ["notify.phone_one", "notify.nested"]}
        )
        self.hass.states.async_set(
            "notify.nested", "unknown", {"entity_id": ["notify.phone_one", "notify.phone_two"]}
        )

        async def notify(call):
            self.notifications.append(call.data)

        self.hass.services.async_register("notify", "mobile_app_one", notify)
        self.hass.services.async_register("notify", "mobile_app_two", notify)
        self.hass.data["mobile_app"] = {
            DATA_DEVICES: {"webhook_one": Mock(id="one"), "webhook_two": Mock(id="two")},
            DATA_NOTIFY: Mock(
                registered_targets={
                    "mobile_app_one": "webhook_one",
                    "mobile_app_two": "webhook_two",
                }
            ),
        }
        with patch("custom_components.confirmable_actions.er.async_get") as registry:
            registry.return_value.async_get.side_effect = entries.get
            task = await self.start_request(notification_group_helper="notify.family")
            message = await self.wait_for_message(2)
            self.assertEqual(
                {n["target"] for n in self.notifications}, {"webhook_one", "webhook_two"}
            )
            async with asyncio.timeout(5):
                while not self.hass.bus.async_listeners().get(
                    "mobile_app_notification_action"
                ):
                    await asyncio.sleep(0.01)
            await self.respond(message["data"]["actions"][0]["action"], "phone_two")
            await asyncio.wait_for(task, 5)
            self.assertEqual(self.selected, ["yes"])
            self.assertEqual(len(self.notifications), 4)
            for clear in self.notifications[2:]:
                self.assertEqual(clear["message"], "clear_notification")
                self.assertEqual(clear["data"]["tag"], message["data"]["tag"])

    async def test_group_helper_rejects_non_mobile_members_before_sending(self):
        await setup_group_action(self.hass, {})
        entries = {
            "notify.family": Mock(domain="notify", platform="group"),
            "notify.phone": Mock(domain="notify", platform="mobile_app", device_id="one"),
            "notify.other": Mock(domain="notify", platform="other"),
        }
        self.hass.states.async_set(
            "notify.family", "unknown", {"entity_id": ["notify.phone", "notify.other"]}
        )
        self.hass.data["mobile_app"] = {DATA_NOTIFY: Mock()}
        with (
            patch("custom_components.confirmable_actions.er.async_get") as registry,
            patch(
                "custom_components.confirmable_actions.webhook_id_from_device_id",
                return_value="webhook",
            ),
            patch(
                "custom_components.confirmable_actions.get_notify_service",
                return_value="mobile_app_one",
            ),
        ):
            registry.return_value.async_get.side_effect = entries.get
            with self.assertRaisesRegex(HomeAssistantError, "not a Companion app device"):
                await self.hass.services.async_call(
                    "confirmable_actions",
                    "send_notification",
                    {"entity_id": "notify.family", "message": "Confirm?"},
                    blocking=True,
                )
            self.assertEqual(self.notifications, [])

    async def test_group_helper_rejects_cycles(self):
        await setup_group_action(self.hass, {})
        self.hass.states.async_set(
            "notify.family", "unknown", {"entity_id": ["notify.family"]}
        )
        with patch("custom_components.confirmable_actions.er.async_get") as registry:
            registry.return_value.async_get.return_value = Mock(
                domain="notify", platform="group"
            )
            with self.assertRaisesRegex(HomeAssistantError, "group cycle"):
                await self.hass.services.async_call(
                    "confirmable_actions",
                    "send_notification",
                    {"entity_id": "notify.family", "message": "Confirm?"},
                    blocking=True,
                )

    async def test_group_helper_attempts_all_members_when_one_fails(self):
        await setup_group_action(self.hass, {})
        entries = {
            "notify.family": Mock(domain="notify", platform="group"),
            "notify.phone_one": Mock(domain="notify", platform="mobile_app", device_id="one"),
            "notify.phone_two": Mock(domain="notify", platform="mobile_app", device_id="two"),
        }
        self.hass.states.async_set(
            "notify.family", "unknown", {"entity_id": ["notify.phone_one", "notify.phone_two"]}
        )
        self.hass.data["mobile_app"] = {
            DATA_DEVICES: {"one": Mock(id="one"), "two": Mock(id="two")},
            DATA_NOTIFY: Mock(registered_targets={"mobile_app_one": "one", "mobile_app_two": "two"}),
        }

        async def fail(call):
            raise HomeAssistantError("Delivery failed")

        async def succeed(call):
            self.notifications.append(call.data)

        self.hass.services.async_register("notify", "mobile_app_one", fail)
        self.hass.services.async_register("notify", "mobile_app_two", succeed)
        with patch("custom_components.confirmable_actions.er.async_get") as registry:
            registry.return_value.async_get.side_effect = entries.get
            with self.assertRaisesRegex(HomeAssistantError, "Delivery failed"):
                await self.hass.services.async_call(
                    "confirmable_actions",
                    "send_notification",
                    {"entity_id": "notify.family", "message": "Confirm?"},
                    blocking=True,
                )
        self.assertEqual(len(self.notifications), 1)
        self.assertEqual(self.notifications[0]["target"], "two")


if __name__ == "__main__":
    unittest.main()
