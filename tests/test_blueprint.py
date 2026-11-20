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
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.script import Script, async_validate_actions_config
from homeassistant.loader import async_setup
from homeassistant.util.yaml import load_yaml


BLUEPRINT_PATH = (
    Path(__file__).resolve().parents[1]
    / "blueprints/automation/confirmable_notification.yaml"
)


class BlueprintTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config_dir = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.config_dir.name)
        async_setup(self.hass)
        await dr.async_load(self.hass)
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
        with patch.object(dr.async_get(self.hass), "async_get", return_value=Mock()):
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

        with patch.object(
            device_action,
            "async_call_action_from_config",
            new=AsyncMock(side_effect=notify_device),
        ) as notify:
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


if __name__ == "__main__":
    unittest.main()
