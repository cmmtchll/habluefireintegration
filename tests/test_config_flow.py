"""Test actual schemas and flow methods with mocked HA flow-manager helpers."""

import importlib
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import voluptuous as vol

from custom_components.bluefire.validation import normalize_address
from test_boundaries import module


class AddressTests(unittest.TestCase):
    def test_normalizes_supported_formats(self):
        for value in (
            "aa:bb:cc:dd:ee:01", "AA-BB-CC-DD-EE-01",
            "aabbccddee01", "  AA:BB:CC:DD:EE:01  ",
        ):
            with self.subTest(value=value):
                self.assertEqual(normalize_address(value), "AA:BB:CC:DD:EE:01")

    def test_rejects_invalid_and_non_individual_addresses(self):
        for value in (
            "", "AA:BB:CC:DD:EE", "AA:BB:CC:DD:EE:GG",
            "AA:BB-CC:DD:EE:01", "AA.BB.CC.DD.EE.01",
            "000000000000", "ff:ff:ff:ff:ff:ff", "aabbccddee011",
            "AA:BB:CC:DD:EE:01\nanything",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_address(value)


class FlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        class ConfigFlow:
            def __init_subclass__(cls, **kwargs):
                super().__init_subclass__()

        self.bluetooth = SimpleNamespace(
            async_discovered_service_info=Mock(return_value=[])
        )
        self.module_name = "custom_components.bluefire.config_flow"
        # Remove import cache so every test gets fresh mocked dependencies.
        self.modules = patch.dict(sys.modules, {
            "homeassistant": module("homeassistant"),
            "homeassistant.components": module(
                "homeassistant.components", bluetooth=self.bluetooth
            ),
            "homeassistant.config_entries": module(
                "homeassistant.config_entries", ConfigFlow=ConfigFlow
            ),
            "homeassistant.const": module(
                "homeassistant.const", CONF_ADDRESS="address", CONF_NAME="name"
            ),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        sys.modules.pop(self.module_name, None)
        self.addCleanup(sys.modules.pop, self.module_name, None)
        api = importlib.import_module(self.module_name)
        self.flow = api.BlueFireConfigFlow()
        self.flow.hass = object()
        self.flow.async_show_form = Mock(side_effect=lambda **kw: kw)
        self.flow.async_show_menu = Mock(side_effect=lambda **kw: kw)
        self.flow.async_abort = Mock(side_effect=lambda **kw: kw)
        self.flow.async_create_entry = Mock(side_effect=lambda **kw: kw)
        self.flow.async_set_unique_id = AsyncMock()
        self.flow._abort_if_unique_id_configured = Mock()
        self.flow._async_current_entries = Mock(return_value=[])
        self.flow._async_current_ids = Mock(return_value=set())
        self.flow.async_update_reload_and_abort = Mock(
            side_effect=lambda entry, **kw: kw
        )
        self.data = {
            "name": "My BlueFire", "address": "AA:BB:CC:DD:EE:01",
            "vehicle_id": "coach",
        }

    async def test_user_menu_includes_offline_setup(self):
        result = await self.flow.async_step_user()
        self.assertEqual(result["menu_options"], ["discovered", "manual"])
        self.bluetooth.async_discovered_service_info.assert_not_called()

    async def test_manual_schema_defaults_and_required_fields(self):
        result = await self.flow.async_step_manual()
        schema = result["data_schema"]
        with self.assertRaises(vol.Invalid):
            schema({"unexpected": "value"})
        data = schema({})
        self.assertEqual(data["vehicle_id"], "liberty_h3_45")
        self.assertEqual(data["name"], "BlueFire")
        self.assertEqual(data["address"], "")

    async def test_manual_creates_normalized_entry_offline(self):
        result = await self.flow.async_step_manual({
            "name": "  My BlueFire ", "address": " aa-bb-cc-dd-ee-01 ",
            "vehicle_id": " coach ",
        })
        self.assertEqual(result, {"title": "My BlueFire", "data": self.data})
        self.flow.async_set_unique_id.assert_awaited_once_with(
            "AA:BB:CC:DD:EE:01"
        )
        self.flow._abort_if_unique_id_configured.assert_called_once()
        self.bluetooth.async_discovered_service_info.assert_not_called()

    async def test_j1587_firmware_format_is_optional_and_explicit(self):
        result = await self.flow.async_step_manual({
            **self.data, "j1587_extended": True,
        })
        self.assertEqual(result["data"]["j1587_extended"], True)
        schema = self.flow.async_step_manual().get("data_schema")
        self.assertIs(schema({"j1587_extended": "Extended (3.19+)"})[
            "j1587_extended"
        ], True)
        with self.assertRaises(vol.Invalid):
            schema({"j1587_extended": "Guess"})

    async def test_field_errors_preserve_input(self):
        bad = {"name": " ", "address": "oops", "vehicle_id": "invalid/topic"}
        result = await self.flow.async_step_manual(bad)
        self.assertEqual(result["errors"], {
            "name": "invalid_name", "address": "invalid_address",
            "vehicle_id": "invalid_vehicle_id",
        })
        self.assertEqual(result["data_schema"]({}), bad)
        self.flow.async_create_entry.assert_not_called()
        self.flow.async_set_unique_id.assert_not_awaited()

    async def test_duplicate_vehicle_topic_is_rejected(self):
        self.flow._async_current_entries.return_value = [
            SimpleNamespace(data={"vehicle_id": "coach"})
        ]
        result = await self.flow.async_step_manual(self.data)
        self.assertEqual(result["errors"], {"vehicle_id": "vehicle_id_in_use"})

    async def test_duplicate_mac_uses_ha_abort_guard(self):
        self.flow._abort_if_unique_id_configured.side_effect = RuntimeError(
            "already_configured"
        )
        with self.assertRaisesRegex(RuntimeError, "already_configured"):
            await self.flow.async_step_manual(self.data)
        self.flow.async_create_entry.assert_not_called()

    async def test_discovery_is_connectable_and_excludes_configured(self):
        self.flow._async_current_ids.return_value = {"AA:BB:CC:DD:EE:02"}
        self.bluetooth.async_discovered_service_info.return_value = [
            SimpleNamespace(address="aa:bb:cc:dd:ee:01", name="BlueFire"),
            SimpleNamespace(address="AA:BB:CC:DD:EE:02", name="Configured"),
            SimpleNamespace(address="not-a-mac", name="Invalid"),
            SimpleNamespace(address="AA:BB:CC:DD:EE:03", name=None),
        ]
        result = await self.flow.async_step_discovered()
        self.bluetooth.async_discovered_service_info.assert_called_once_with(
            self.flow.hass, connectable=True
        )
        schema = result["data_schema"]
        self.assertEqual(
            schema({"address": "AA:BB:CC:DD:EE:01"})["address"],
            "AA:BB:CC:DD:EE:01",
        )
        with self.assertRaises(vol.Invalid):
            schema({"address": "AA:BB:CC:DD:EE:02"})
        result = await self.flow.async_step_discovered({
            "address": "AA:BB:CC:DD:EE:01"
        })
        self.assertEqual(result["step_id"], "manual")
        defaults = result["data_schema"]({})
        self.assertEqual(defaults["name"], "BlueFire")
        self.assertEqual(defaults["address"], "AA:BB:CC:DD:EE:01")
        self.flow.async_create_entry.assert_not_called()

    async def test_no_discovered_devices_has_clear_abort(self):
        result = await self.flow.async_step_discovered()
        self.assertEqual(result["reason"], "no_devices_found")

    async def test_unknown_selection_does_not_create_entry(self):
        self.bluetooth.async_discovered_service_info.return_value = [
            SimpleNamespace(address="AA:BB:CC:DD:EE:01", name="Adapter")
        ]
        result = await self.flow.async_step_discovered({"address": "unknown"})
        self.assertEqual(result["errors"], {"address": "invalid_selection"})
        self.flow.async_create_entry.assert_not_called()

    def reconfigure_entry(self):
        entry = SimpleNamespace(
            unique_id=self.data["address"], data=self.data.copy()
        )
        self.flow._get_reconfigure_entry = Mock(return_value=entry)
        return entry

    async def test_reconfigure_preserves_vehicle_id_and_uses_ha_reload(self):
        self.reconfigure_entry()
        result = await self.flow.async_step_reconfigure({
            "name": "Corrected", "address": "aabbccddee02",
        })
        self.assertEqual(result["unique_id"], "AA:BB:CC:DD:EE:02")
        self.assertEqual(result["data_updates"], {
            "name": "Corrected", "address": "AA:BB:CC:DD:EE:02",
            "vehicle_id": "coach",
        })
        self.flow._abort_if_unique_id_configured.assert_called_once()
        self.flow.async_create_entry.assert_not_called()

    async def test_reconfigure_same_mac_does_not_abort_on_own_entry(self):
        self.reconfigure_entry()
        await self.flow.async_step_reconfigure(self.data)
        self.flow._abort_if_unique_id_configured.assert_not_called()

    async def test_reconfigure_cannot_claim_another_adapters_mac(self):
        self.reconfigure_entry()
        self.flow._abort_if_unique_id_configured.side_effect = RuntimeError(
            "already_configured"
        )
        with self.assertRaisesRegex(RuntimeError, "already_configured"):
            await self.flow.async_step_reconfigure({
                "name": "Other", "address": "AA:BB:CC:DD:EE:02",
            })
        self.flow.async_update_reload_and_abort.assert_not_called()

    async def test_reconfigure_schema_excludes_mqtt_identity(self):
        self.reconfigure_entry()
        result = await self.flow.async_step_reconfigure()
        with self.assertRaises(vol.Invalid):
            result["data_schema"](self.data)
        self.assertEqual(result["data_schema"]({}), {
            "name": self.data["name"], "address": self.data["address"],
        })
