"""Tests for integration setup and bundled blueprint installation."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import AbortFlow, FlowResultType
from homeassistant.loader import async_setup as setup_loader

from custom_components.confirmable_actions import (
    DOMAIN,
    _install_blueprint,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.confirmable_actions.config_flow import ConfirmableActionsConfigFlow


ROOT = Path(__file__).resolve().parents[1]
BUNDLED_BLUEPRINT = (
    ROOT / "custom_components/confirmable_actions/blueprints/confirmable_notification.yaml"
)


class BlueprintInstallTests(unittest.TestCase):
    def test_bundled_blueprint_matches_importable_blueprint(self):
        for domain in ("automation", "script"):
            with self.subTest(domain=domain):
                bundled = BUNDLED_BLUEPRINT if domain == "automation" else (
                    BUNDLED_BLUEPRINT.parent / domain / BUNDLED_BLUEPRINT.name
                )
                self.assertEqual(
                    bundled.read_bytes(),
                    (ROOT / "blueprints" / domain / BUNDLED_BLUEPRINT.name).read_bytes(),
                )

    def test_install_preserves_existing_blueprint(self):
        for domain in ("automation", "script"):
            with self.subTest(domain=domain), tempfile.TemporaryDirectory() as config_dir:
                bundled = BUNDLED_BLUEPRINT if domain == "automation" else (
                    BUNDLED_BLUEPRINT.parent / domain / BUNDLED_BLUEPRINT.name
                )
                path = (
                    Path(config_dir)
                    / "blueprints" / domain / "confirmable_actions/confirmable_notification.yaml"
                )
                self.assertTrue(_install_blueprint(config_dir, domain))
                self.assertEqual(path.read_bytes(), bundled.read_bytes())
                path.write_text("custom blueprint", encoding="utf-8")
                self.assertFalse(_install_blueprint(config_dir, domain))
                self.assertEqual(path.read_text(encoding="utf-8"), "custom blueprint")
                path.unlink()
                self.assertTrue(_install_blueprint(config_dir, domain))
                self.assertEqual(path.read_bytes(), bundled.read_bytes())


class IntegrationSetupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config_dir = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.config_dir.name)
        setup_loader(self.hass)

    async def asyncTearDown(self):
        await self.hass.async_stop()
        self.config_dir.cleanup()

    async def test_ui_setup_installs_blueprint_and_unload_removes_action(self):
        cache = Mock(async_reset_cache=AsyncMock())
        script_cache = Mock(async_reset_cache=AsyncMock())
        self.hass.data["blueprint"] = {"automation": cache, "script": script_cache}
        self.assertTrue(await async_setup_entry(self.hass, Mock()))
        cache.async_reset_cache.assert_awaited_once()
        script_cache.async_reset_cache.assert_awaited_once()
        self.assertTrue(self.hass.services.has_service(DOMAIN, "send_notification"))
        self.assertTrue(await async_unload_entry(self.hass, Mock()))
        self.assertFalse(self.hass.services.has_service(DOMAIN, "send_notification"))
        self.assertTrue(await async_setup_entry(self.hass, Mock()))
        cache.async_reset_cache.assert_awaited_once()
        script_cache.async_reset_cache.assert_awaited_once()
        self.assertTrue(self.hass.services.has_service(DOMAIN, "send_notification"))


class ConfigFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmation_and_duplicate_entry(self):
        flow = ConfirmableActionsConfigFlow()
        flow.hass = Mock()
        flow.handler = DOMAIN
        flow.flow_id = "test-flow"
        flow.context = {"source": "user"}
        entries = flow.hass.config_entries
        entries.flow.async_progress_by_handler.return_value = []
        entries.async_entry_for_domain_unique_id.return_value = None

        result = await flow.async_step_user()
        self.assertEqual(result["type"], FlowResultType.FORM)
        result = await flow.async_step_user({})
        self.assertEqual(result["type"], FlowResultType.CREATE_ENTRY)
        self.assertEqual(result["data"], {})

        entries.async_entry_for_domain_unique_id.return_value = Mock()
        with self.assertRaises(AbortFlow) as abort:
            await flow.async_step_user()
        self.assertEqual(abort.exception.reason, "already_configured")
