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
from homeassistant.components.blueprint import BLUEPRINT_SCHEMA
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.components.mobile_app import device_action
from homeassistant.components.mobile_app.const import DATA_DEVICES, DATA_NOTIFY
from homeassistant.components.script.config import SCRIPT_ENTITY_SCHEMA
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import trigger as trigger_helper
from homeassistant.helpers.script import Script, async_validate_actions_config
from homeassistant.loader import async_setup
from homeassistant.util.yaml import load_yaml

from custom_components.confirmable_actions import async_setup_entry as setup_group_action


BLUEPRINT_PATH = (
    Path(__file__).resolve().parents[1]
    / "blueprints/automation/confirmable_notification.yaml"
)


class BlueprintTests(unittest.IsolatedAsyncioTestCase):
    blueprint_domain = "automation"

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

        async def set_state(call):
            self.hass.states.async_set(call.data["entity_id"], call.data["state"])

        self.hass.services.async_register("confirmable_actions", "send_notification", notify)
        self.hass.services.async_register("test", "selected", selected)
        self.hass.services.async_register("test", "set_state", set_state)

    async def asyncTearDown(self):
        for script in self.scripts:
            await script.async_stop()
        await self.hass.async_stop()
        self.config_dir.cleanup()

    async def start_request(self, context=None, **overrides):
        domain = self.blueprint_domain
        path = BLUEPRINT_PATH.parents[1] / domain / BLUEPRINT_PATH.name
        blueprint = Blueprint(
            load_yaml(str(path)),
            expected_domain=domain,
            schema=(
                AUTOMATION_BLUEPRINT_SCHEMA if domain == "automation" else BLUEPRINT_SCHEMA
            ),
        )
        inputs = {
            "notification_group_helper": "notify.family",
            "notification_device": "a" * 32,
            "notification_message": "Confirm?",
            "confirmation_actions": [
                {"action": "test.selected", "data": {"button": "yes"}}
            ],
            "reminder_delay": {"seconds": 0},
            "response_timeout": {"seconds": 5},
            **overrides,
        }
        if domain == "automation":
            inputs["notification_trigger"] = [{"trigger": "event", "event_type": "test"}]
        configured = BlueprintInputs(
            blueprint,
            {"use_blueprint": {"path": str(path), "input": inputs}},
        )
        configured.validate()
        schema = PLATFORM_SCHEMA if domain == "automation" else SCRIPT_ENTITY_SCHEMA
        config = schema(configured.async_substitute())
        with (
            patch.object(dr.async_get(self.hass), "async_get", return_value=Mock()),
            patch(
                "homeassistant.components.device_automation.helpers.async_get_device_automation_platform",
                new=AsyncMock(return_value=device_action),
            ),
        ):
            sequence = await async_validate_actions_config(
                self.hass, config["actions" if domain == "automation" else "sequence"]
            )
        script = Script(
            self.hass,
            sequence,
            "Confirm",
            domain,
            script_mode=config["mode"],
            max_runs=config["max"],
        )
        self.scripts.append(script)
        return asyncio.create_task(script.async_run(context=context or Context()))

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

    async def test_secondary_button_runs_only_its_actions_and_finishes(self):
        task = await self.start_request(
            accept_label="Confirm",
            deny_label="Do something else",
            secondary_actions=[
                {"action": "test.selected", "data": {"button": "secondary"}}
            ],
            reminder_actions=[
                {"action": "test.selected", "data": {"button": "remind"}}
            ],
        )
        message = await self.wait_for_message(1)
        buttons = message["data"]["actions"]
        self.assertEqual(
            [b["title"] for b in buttons], ["Confirm", "Do something else", "Remind me later"]
        )
        await self.respond(buttons[1]["action"], "phone_two")
        await asyncio.wait_for(task, 5)
        self.assertEqual(self.selected, ["secondary"])
        self.assertEqual(self.notifications[-1]["message"], "clear_notification")
        self.assertEqual(self.notifications[-1]["data"]["tag"], message["data"]["tag"])
        self.assertEqual(len(self.notifications), 2)

    async def test_default_notification_has_no_persistence_or_tap_override(self):
        task = await self.start_request()
        message = await self.wait_for_message(1)
        self.assertEqual(set(message["data"]), {"tag", "actions"})
        await self.respond(message["data"]["actions"][1]["action"])
        await asyncio.wait_for(task, 5)

    async def test_persistence_and_tap_destination_survive_reminders(self):
        self.hass.states.async_set("sensor.notification_page", "/lovelace/first")
        task = await self.start_request(
            notification_icon="mdi:bell-ring",
            notification_persistent=True,
            notification_tap_url=" {{ states('sensor.notification_page') }} ",
        )
        first = await self.wait_for_message(1)
        self.assertEqual(first["data"]["notification_icon"], "mdi:bell-ring")
        self.assertIs(first["data"]["persistent"], True)
        self.assertIs(first["data"]["sticky"], True)
        self.assertEqual(first["data"]["url"], "/lovelace/first")
        self.assertEqual(first["data"]["clickAction"], "/lovelace/first")
        self.assertEqual(len(first["data"]["actions"]), 3)
        self.hass.states.async_set("sensor.notification_page", "/lovelace/second")
        await self.respond(first["data"]["actions"][2]["action"])
        second = await self.wait_for_message(2)
        self.assertEqual(second["data"]["notification_icon"], "mdi:bell-ring")
        self.assertIs(second["data"]["persistent"], True)
        self.assertIs(second["data"]["sticky"], True)
        self.assertEqual(second["data"]["url"], "/lovelace/second")
        self.assertEqual(second["data"]["clickAction"], "/lovelace/second")
        self.assertEqual(first["data"]["tag"], second["data"]["tag"])
        await self.respond(second["data"]["actions"][0]["action"])
        await asyncio.wait_for(task, 5)
        self.assertEqual(self.selected, ["yes"])
        for notification in self.notifications:
            if notification["message"] == "clear_notification":
                self.assertEqual(notification["data"], {"tag": first["data"]["tag"]})

    async def test_whitespace_tap_destination_keeps_default_behavior(self):
        task = await self.start_request(notification_tap_url="   ")
        message = await self.wait_for_message(1)
        self.assertNotIn("url", message["data"])
        self.assertNotIn("clickAction", message["data"])
        await self.respond(message["data"]["actions"][1]["action"])
        await asyncio.wait_for(task, 5)

    async def test_hidden_buttons_do_not_run_their_actions_on_confirmation(self):
        task = await self.start_request(
            deny_label="",
            reminder_label="",
            secondary_actions=[
                {"action": "test.selected", "data": {"button": "secondary"}}
            ],
            reminder_actions=[
                {"action": "test.selected", "data": {"button": "remind"}}
            ],
        )
        message = await self.wait_for_message(1)
        self.assertEqual([b["title"] for b in message["data"]["actions"]], ["Yes"])
        await self.respond(message["data"]["actions"][0]["action"])
        await asyncio.wait_for(task, 5)
        self.assertEqual(self.selected, ["yes"])

    async def test_disabled_reminders_ignore_responses_and_do_not_resend(self):
        task = await self.start_request(
            enable_reminders=False,
            reminder_actions=[
                {"action": "test.selected", "data": {"button": "remind"}}
            ],
        )
        message = await self.wait_for_message(1)
        self.assertEqual(
            [b["title"] for b in message["data"]["actions"]], ["Yes", "No"]
        )
        await self.respond(f"REMIND_{message['data']['tag']}_1")
        self.assertEqual(self.selected, [])
        self.assertEqual(len(self.notifications), 1)
        self.assertFalse(task.done())
        await self.respond(message["data"]["actions"][0]["action"])
        await asyncio.wait_for(task, 5)
        self.assertEqual(self.selected, ["yes"])
        self.assertEqual(len(self.notifications), 2)

    async def test_reminder_actions_run_on_every_press_before_delay_and_resend(self):
        self.hass.states.async_set("light.test", "on")
        task = await self.start_request(
            notification_message="{{ states('light.test') }}",
            reminder_delay={"milliseconds": 100},
            reminder_actions=[
                {"action": "test.selected", "data": {"button": "remind"}},
                {"action": "test.set_state", "data": {"entity_id": "light.test", "state": "off"}},
            ],
        )
        first = await self.wait_for_message(1)
        self.assertEqual(first["message"], "on")
        await self.respond(first["data"]["actions"][2]["action"])
        self.assertEqual(self.selected, ["remind"])
        self.assertEqual(len(self.notifications), 2)
        self.assertFalse(task.done())
        second = await self.wait_for_message(2)
        self.assertEqual(second["message"], "off")
        await self.respond(first["data"]["actions"][2]["action"])
        self.assertEqual(self.selected, ["remind"])
        await self.respond(second["data"]["actions"][2]["action"])
        self.assertEqual(self.selected, ["remind", "remind"])
        third = await self.wait_for_message(3)
        await self.respond(third["data"]["actions"][0]["action"])
        await asyncio.wait_for(task, 5)
        self.assertEqual(self.selected, ["remind", "remind", "yes"])

    async def test_parallel_runs_with_shared_context_are_isolated(self):
        context = Context()
        task = await self.start_request(context=context)
        first = await self.wait_for_message(1)
        other_task = asyncio.create_task(self.scripts[-1].async_run(context=context))
        other = await self.wait_for_message(2)
        self.assertNotEqual(first["data"]["tag"], other["data"]["tag"])
        await self.respond(first["data"]["actions"][0]["action"])
        await asyncio.wait_for(task, 5)
        self.assertFalse(other_task.done())
        await self.respond(other["data"]["actions"][1]["action"])
        await asyncio.wait_for(other_task, 5)
        self.assertEqual(self.selected, ["yes"])

    async def test_secondary_and_reminder_action_failures_stop_request(self):
        async def fail(call):
            raise HomeAssistantError("Button action failed")

        self.hass.services.async_register("test", "fail", fail)
        for input_name, button_index in (("secondary_actions", 1), ("reminder_actions", 2)):
            with self.subTest(input_name=input_name):
                self.notifications.clear()
                self.selected.clear()
                task = await self.start_request(**{input_name: [{"action": "test.fail"}]})
                message = await self.wait_for_message(1)
                await self.respond(message["data"]["actions"][button_index]["action"])
                with self.assertRaisesRegex(HomeAssistantError, "Button action failed"):
                    await asyncio.wait_for(task, 5)
                self.assertEqual(self.selected, [])
                self.assertEqual(len(self.notifications), 2)
                self.assertEqual(self.notifications[-1]["message"], "clear_notification")

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
                notification_group_helper="",
                notification_device="a" * 32,
                notification_icon="mdi:cctv",
                notification_persistent=True,
                notification_tap_url="/lovelace/cameras",
            )
            message = await self.wait_for_message(1)
            self.assertEqual(message["data"]["notification_icon"], "mdi:cctv")
            self.assertIs(message["data"]["persistent"], True)
            self.assertIs(message["data"]["sticky"], True)
            self.assertEqual(message["data"]["url"], "/lovelace/cameras")
            self.assertEqual(message["data"]["clickAction"], "/lovelace/cameras")
            await self.respond(message["data"]["actions"][0]["action"])
            await asyncio.wait_for(task, 5)
            self.assertEqual(self.selected, ["yes"])
            self.assertEqual(notify.await_count, 2)
            self.assertEqual(self.notifications[-1]["message"], "clear_notification")

    async def test_timeout_clears_without_actions(self):
        task = await self.start_request(
            response_timeout={"milliseconds": 50},
            secondary_actions=[
                {"action": "test.selected", "data": {"button": "secondary"}}
            ],
            reminder_actions=[
                {"action": "test.selected", "data": {"button": "remind"}}
            ],
        )
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
            task = await self.start_request(
                notification_group_helper="notify.family",
                notification_icon="mdi:home",
                notification_persistent=True,
                notification_tap_url="https://example.com",
            )
            message = await self.wait_for_message(2)
            for notification in self.notifications:
                self.assertEqual(notification["data"]["notification_icon"], "mdi:home")
                self.assertIs(notification["data"]["persistent"], True)
                self.assertIs(notification["data"]["sticky"], True)
                self.assertEqual(notification["data"]["url"], "https://example.com")
                self.assertEqual(notification["data"]["clickAction"], "https://example.com")
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


class ScriptBlueprintTests(BlueprintTests):
    blueprint_domain = "script"


if __name__ == "__main__":
    unittest.main()
