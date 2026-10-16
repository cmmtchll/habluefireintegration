"""Test HA/BLE boundaries with mocks, not hardware commissioning."""

import asyncio
import importlib
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from custom_components.bluefire import async_setup_entry, async_unload_entry


def module(name, **attributes):
    result = ModuleType(name)
    result.__dict__.update(attributes)
    return result


class BoundaryError(Exception):
    pass


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.callbacks = []
        self.tasks = []
        self.mqtt = SimpleNamespace(
            async_wait_for_mqtt_client=AsyncMock(return_value=True),
            async_publish=AsyncMock(),
            is_connected=Mock(return_value=True),
            async_subscribe_connection_status=Mock(
                side_effect=lambda hass, cb: self.callbacks.append(
                    cb) or Mock()
            ),
        )
        self.client = SimpleNamespace(services=[], disconnect=AsyncMock())
        self.connect = AsyncMock(return_value=self.client)
        self.bluetooth = SimpleNamespace(
            async_ble_device_from_address=Mock(return_value=object())
        )
        self.modules = patch.dict(sys.modules, {
            "homeassistant": module("homeassistant"),
            "homeassistant.components": module(
                "homeassistant.components",
                mqtt=self.mqtt,
                bluetooth=self.bluetooth,
            ),
            "homeassistant.const": module(
                "homeassistant.const",
                Platform=SimpleNamespace(SENSOR="sensor"),
            ),
            "homeassistant.core": module(
                "homeassistant.core", callback=lambda func: func
            ),
            "homeassistant.exceptions": module(
                "homeassistant.exceptions",
                ConfigEntryNotReady=BoundaryError,
                HomeAssistantError=BoundaryError,
            ),
            "bleak": module("bleak"),
            "bleak.exc": module("bleak.exc", BleakError=BoundaryError),
            "bleak_retry_connector": module(
                "bleak_retry_connector",
                BleakClientWithServiceCache=object,
                establish_connection=self.connect,
            ),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.hass = SimpleNamespace(config_entries=SimpleNamespace(
            async_forward_entry_setups=AsyncMock(),
            async_unload_platforms=AsyncMock(return_value=True),
        ))
        self.entry = SimpleNamespace(
            data={"vehicle_id": "coach"},
            async_on_unload=Mock(),
            async_create_task=self.create_task,
        )

    def create_task(self, hass, coroutine, name):
        task = asyncio.create_task(coroutine, name=name)
        self.tasks.append(task)
        return task

    async def test_offline_preparation_does_not_connect_ble(self):
        self.assertTrue(await async_setup_entry(self.hass, self.entry))
        self.connect.assert_not_awaited()
        entries = self.hass.config_entries
        entries.async_forward_entry_setups.assert_awaited_once()
        self.mqtt.async_publish.assert_awaited_once_with(
            self.hass, "vehicle/coach/j1939/availability", "offline",
            qos=0, retain=True,
        )
        self.entry.async_on_unload.assert_called_once()

    async def test_missing_mqtt_client_is_retryable(self):
        self.mqtt.async_wait_for_mqtt_client.return_value = False
        with self.assertRaises(BoundaryError):
            await async_setup_entry(self.hass, self.entry)
        entries = self.hass.config_entries
        entries.async_forward_entry_setups.assert_not_awaited()
        self.mqtt.async_publish.assert_not_awaited()

    async def test_setup_with_broker_offline_waits_for_reconnect(self):
        self.mqtt.is_connected.return_value = False
        self.assertTrue(await async_setup_entry(self.hass, self.entry))
        self.mqtt.async_publish.assert_not_awaited()
        self.callbacks[0](False)
        self.assertEqual(self.tasks, [])
        self.callbacks[0](True)
        await asyncio.gather(*self.tasks)
        self.assertEqual(self.mqtt.async_publish.await_count, 1)

    async def test_reconnect_replays_definitions_but_no_state(self):
        await async_setup_entry(self.hass, self.entry)
        topic = "homeassistant/sensor/test/config"
        self.entry.runtime_data.bridge.discovery[topic] = "{}"
        self.mqtt.async_publish.reset_mock()
        self.callbacks[0](True)
        await asyncio.gather(*self.tasks)
        calls = self.mqtt.async_publish.await_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[2], "offline")
        self.assertEqual(calls[1].args[1], "homeassistant/sensor/test/config")

    async def test_unload_marks_offline(self):
        await async_setup_entry(self.hass, self.entry)
        self.mqtt.async_publish.reset_mock()
        self.assertTrue(await async_unload_entry(self.hass, self.entry))
        self.assertEqual(self.mqtt.async_publish.await_args.args[2], "offline")

    async def test_failed_platform_unload_preserves_runtime(self):
        await async_setup_entry(self.hass, self.entry)
        self.hass.config_entries.async_unload_platforms.return_value = False
        self.mqtt.async_publish.reset_mock()
        self.assertFalse(await async_unload_entry(self.hass, self.entry))
        self.mqtt.async_publish.assert_not_awaited()

    async def test_unload_with_disconnected_broker(self):
        await async_setup_entry(self.hass, self.entry)
        self.mqtt.is_connected.return_value = False
        self.mqtt.async_publish.reset_mock()
        self.assertTrue(await async_unload_entry(self.hass, self.entry))
        self.mqtt.async_publish.assert_not_awaited()

    async def test_inspection_metadata_only_and_disconnects(self):
        api = importlib.import_module("custom_components.bluefire.bluetooth")
        self.client.services = [
            SimpleNamespace(uuid="service", characteristics=[
                SimpleNamespace(uuid="characteristic",
                                properties=["notify", "write"])
            ])
        ]
        result = await api.async_inspect(self.hass, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(result, [{
            "uuid": "service",
            "characteristics": [{
                "uuid": "characteristic",
                "properties": ["notify", "write"],
            }],
        }])
        self.client.disconnect.assert_awaited_once()
        # The fake client intentionally offers no reads, subscriptions or
        # writes.

    async def test_inspection_offline_error_does_not_connect(self):
        api = importlib.import_module("custom_components.bluefire.bluetooth")
        self.bluetooth.async_ble_device_from_address.return_value = None
        with self.assertRaisesRegex(BoundaryError, "not visible"):
            await api.async_inspect(self.hass, "AA:BB:CC:DD:EE:FF")
        self.connect.assert_not_awaited()

    async def test_inspection_connect_failure_is_actionable(self):
        api = importlib.import_module("custom_components.bluefire.bluetooth")
        self.connect.side_effect = BoundaryError("adapter busy")
        with self.assertRaisesRegex(BoundaryError, "not used by another app"):
            await api.async_inspect(self.hass, "AA:BB:CC:DD:EE:FF")

    async def test_inspection_disconnects_on_serialization_failure(self):
        api = importlib.import_module("custom_components.bluefire.bluetooth")
        self.client.services = [object()]
        with self.assertRaises(AttributeError):
            await api.async_inspect(self.hass, "AA:BB:CC:DD:EE:FF")
        self.client.disconnect.assert_awaited_once()

    async def test_diagnostics_omit_identifying_data(self):
        api = importlib.import_module("custom_components.bluefire.diagnostics")
        await async_setup_entry(self.hass, self.entry)
        self.entry.data["address"] = "AA:BB:CC:DD:EE:FF"
        result = await api.async_get_config_entry_diagnostics(
            self.hass, self.entry
        )
        self.assertEqual(
            result, {
                "protocol_status": "protocol_required", "gatt_services": []})
