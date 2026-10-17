"""Test HA/BLE boundaries with mocks, not hardware commissioning."""

import asyncio
import importlib
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from custom_components.bluefire import (
    CONFIG_SCHEMA,
    async_setup,
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
)


def module(name, **attributes):
    result = ModuleType(name)
    result.__dict__.update(attributes)
    return result


class BoundaryError(Exception):
    pass


class ServiceSetupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.services = {}

        def register_service(domain, name, handler, **kwargs):
            self.services[name] = handler

        self.service_registration = Mock(side_effect=register_service)
        self.runtime = SimpleNamespace(inspecting=False, services=[])
        self.entry = SimpleNamespace(
            domain="bluefire",
            state="loaded",
            runtime_data=self.runtime,
            data={"address": "AA:BB:CC:DD:EE:01"},
        )
        self.hass = SimpleNamespace(
            config_entries=SimpleNamespace(
                async_get_entry=Mock(return_value=self.entry)
            ),
            services=SimpleNamespace(async_register=self.service_registration),
        )
        self.config_schema = Mock(side_effect=lambda config: config)
        cv = module(
            "homeassistant.helpers.config_validation",
            string=str,
            config_entry_only_config_schema=Mock(
                return_value=self.config_schema
            ),
        )
        self.modules = patch.dict(sys.modules, {
            "homeassistant": module("homeassistant"),
            "homeassistant.config_entries": module(
                "homeassistant.config_entries",
                ConfigEntryState=SimpleNamespace(LOADED="loaded"),
            ),
            "homeassistant.core": module(
                "homeassistant.core",
                SupportsResponse=SimpleNamespace(ONLY="only"),
            ),
            "homeassistant.exceptions": module(
                "homeassistant.exceptions",
                ServiceValidationError=BoundaryError,
            ),
            "homeassistant.helpers": module(
                "homeassistant.helpers", config_validation=cv
            ),
            "homeassistant.helpers.config_validation": cv,
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_yaml_schema_is_limited_to_config_entries(self):
        config = {"bluefire": {}}
        self.assertEqual(CONFIG_SCHEMA(config), config)
        self.config_schema.assert_called_once_with(config)

    async def asyncSetUp(self):
        self.inspected = AsyncMock(return_value=[{"uuid": "service"}])
        inspect_patch = patch.dict(sys.modules, {
            "custom_components.bluefire.bluetooth": module(
                "custom_components.bluefire.bluetooth",
                async_inspect=self.inspected,
            )
        })
        inspect_patch.start()
        self.addCleanup(inspect_patch.stop)
        await async_setup(self.hass, {})
        self.inspect = self.services["inspect_adapter"]

    async def test_inspection_returns_metadata_and_clears_busy_flag(self):
        result = await self.inspect(
            SimpleNamespace(data={"entry_id": "entry"})
        )
        self.assertEqual(
            result,
            {"status": "receiver_enabled", "services": [{"uuid": "service"}]},
        )
        self.inspected.assert_awaited_once_with(
            self.hass, "AA:BB:CC:DD:EE:01"
        )
        self.assertFalse(self.runtime.inspecting)

    async def test_inspection_reuses_receiver_gatt_inventory(self):
        self.runtime.services = [{"uuid": "cached-service"}]
        result = await self.inspect(
            SimpleNamespace(data={"entry_id": "entry"})
        )
        self.assertEqual(
            result,
            {
                "status": "receiver_enabled",
                "services": [{"uuid": "cached-service"}],
            },
        )
        self.inspected.assert_not_awaited()

    async def test_inspection_rejects_non_loaded_entry(self):
        self.entry.state = "not_loaded"
        with self.assertRaisesRegex(BoundaryError, "loaded BlueFire"):
            await self.inspect(SimpleNamespace(data={"entry_id": "entry"}))

    async def test_inspection_rejects_concurrent_request(self):
        self.runtime.inspecting = True
        with self.assertRaisesRegex(BoundaryError, "already running"):
            await self.inspect(SimpleNamespace(data={"entry_id": "entry"}))

    async def test_inspection_clears_busy_flag_after_failure(self):
        self.inspected.side_effect = BoundaryError("inspection failed")
        with self.assertRaisesRegex(BoundaryError, "inspection failed"):
            await self.inspect(SimpleNamespace(data={"entry_id": "entry"}))
        self.assertFalse(self.runtime.inspecting)


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.callbacks = []
        self.tasks = []
        self.intervals = []
        self.birth = []
        self.shutdown = []
        self.store = SimpleNamespace(
            async_load=AsyncMock(return_value=None),
            async_save=AsyncMock(),
        )
        self.mqtt = SimpleNamespace(
            async_wait_for_mqtt_client=AsyncMock(return_value=True),
            async_publish=AsyncMock(side_effect=self.publish),
            async_subscribe=AsyncMock(
                side_effect=lambda hass, topic, cb, qos: (
                    self.birth.append((topic, cb)) or Mock()
                )
            ),
            is_connected=Mock(return_value=True),
            async_subscribe_connection_status=Mock(
                side_effect=lambda hass, cb: self.callbacks.append(
                    cb) or Mock()
            ),
        )
        self.client = SimpleNamespace(services=[], disconnect=AsyncMock())
        self.connect = AsyncMock(return_value=self.client)
        self.receiver_instances = []

        class Receiver:
            def __init__(receiver, *args, **kwargs):
                receiver.args = args
                receiver.kwargs = kwargs
                receiver.stop = Mock()
                receiver.services = []
                self.receiver_instances.append(receiver)

            async def async_run(receiver):
                return None

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
                EVENT_HOMEASSISTANT_STOP="homeassistant_stop",
            ),
            "homeassistant.core": module(
                "homeassistant.core", callback=lambda func: func
            ),
            "homeassistant.exceptions": module(
                "homeassistant.exceptions",
                ConfigEntryNotReady=BoundaryError,
                HomeAssistantError=BoundaryError,
            ),
            "homeassistant.helpers": module("homeassistant.helpers"),
            "homeassistant.helpers.storage": module(
                "homeassistant.helpers.storage",
                Store=Mock(return_value=self.store),
            ),
            "homeassistant.helpers.event": module(
                "homeassistant.helpers.event",
                async_track_time_interval=Mock(
                    side_effect=lambda hass, cb, interval: (
                        self.intervals.append(cb) or Mock()
                    )
                ),
            ),
            "bleak": module("bleak"),
            "bleak.exc": module("bleak.exc", BleakError=BoundaryError),
            "bleak_retry_connector": module(
                "bleak_retry_connector",
                BleakClientWithServiceCache=object,
                establish_connection=self.connect,
            ),
            "custom_components.bluefire.receiver": module(
                "custom_components.bluefire.receiver",
                BlueFireReceiver=Receiver,
            ),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.hass = SimpleNamespace(
            data={},
            config_entries=SimpleNamespace(
                async_forward_entry_setups=AsyncMock(),
                async_unload_platforms=AsyncMock(return_value=True),
                async_entries=Mock(return_value=[]),
            ),
            bus=SimpleNamespace(async_listen_once=Mock(
                side_effect=lambda event, cb: (
                    self.shutdown.append(cb) or Mock()
                )
            )),
            async_create_task=lambda coro, name: self.create_task(
                None, coro, name
            ),
        )
        self.entry = SimpleNamespace(
            entry_id="test-entry",
            title="Coach adapter",
            data={
                "vehicle_id": "coach",
                "address": "AA:BB:CC:DD:EE:01",
            },
            async_on_unload=Mock(),
            async_create_task=self.create_task,
        )

    async def publish(self, hass, topic, payload, **kwargs):
        """Simulate broker delivery to active test subscriptions."""
        for subscribed_topic, callback in tuple(self.birth):
            if subscribed_topic == topic:
                callback(SimpleNamespace(payload=payload))

    def create_task(self, hass, coroutine, name):
        if name == "BlueFire BLE receiver":
            coroutine.close()
            return Mock()
        task = asyncio.create_task(coroutine, name=name)
        self.tasks.append(task)
        return task

    async def test_offline_preparation_does_not_connect_ble(self):
        self.assertTrue(await async_setup_entry(self.hass, self.entry))
        self.connect.assert_not_awaited()
        entries = self.hass.config_entries
        entries.async_forward_entry_setups.assert_awaited_once()
        self.assertEqual(self.mqtt.async_publish.await_count, 2)
        self.mqtt.async_publish.assert_any_await(
            self.hass, "vehicle/coach/j1939/availability", "offline",
            qos=1, retain=True,
        )
        self.assertEqual(self.entry.async_on_unload.call_count, 5)
        self.assertEqual(len(self.receiver_instances), 1)
        self.assertEqual(
            self.receiver_instances[0].kwargs["j1587_extended"], None
        )

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
        self.callbacks[-1](False)
        self.assertEqual(self.tasks, [])
        self.callbacks[-1](True)
        await asyncio.gather(*self.tasks)
        self.assertEqual(self.mqtt.async_publish.await_count, 2)

    async def test_reconnect_replays_definitions_but_no_state(self):
        await async_setup_entry(self.hass, self.entry)
        topic = "homeassistant/sensor/test/config"
        self.entry.runtime_data.bridge.discovery[topic] = "{}"
        self.mqtt.async_publish.reset_mock()
        self.callbacks[-1](True)
        await asyncio.gather(*self.tasks)
        calls = self.mqtt.async_publish.await_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].args[2], "offline")
        self.assertEqual(calls[2].args[1], "homeassistant/sensor/test/config")

    async def test_j1587_runtime_persists_and_rediscoveries_use_ha_mqtt(self):
        from custom_components.bluefire.protocol import J1587Report

        await async_setup_entry(self.hass, self.entry)
        bridge = self.entry.runtime_data.bridge
        await bridge.async_process_j1587(
            J1587Report(128, 190, bytes.fromhex("a0 0f"))
        )
        self.mqtt.async_publish.assert_any_await(
            self.hass, "vehicle/coach/j1587/availability", "online",
            qos=1, retain=True,
        )
        self.mqtt.async_publish.reset_mock()
        self.callbacks[-1](True)
        await asyncio.gather(*self.tasks)
        calls = self.mqtt.async_publish.await_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1].args[1],
                         "homeassistant/sensor/"
                         "bluefire_coach_j1587_128_190/config")
        self.assertTrue(all(
            not call.args[1].endswith("/pid/190") for call in calls
        ))
        self.connect.assert_not_awaited()

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
                "protocol_status": "receiver_enabled", "gatt_services": []})

    async def test_custom_birth_settings_and_prefix(self):
        self.hass.config_entries.async_entries.return_value = [
            SimpleNamespace(
                data={},
                options={
                    "discovery_prefix": "custom/ha",
                    "birth_message": {
                        "topic": "custom/status", "payload": "up",
                    },
                },
            )
        ]
        await async_setup_entry(self.hass, self.entry)
        self.assertEqual(self.birth[0][0], "custom/status")
        bridge = self.entry.runtime_data.bridge
        self.assertEqual(bridge.discovery_prefix, "custom/ha")
        bridge.discovery["custom/ha/sensor/test/config"] = "{}"
        self.mqtt.async_publish.reset_mock()
        await self.birth[0][1](SimpleNamespace(payload="online"))
        self.mqtt.async_publish.assert_not_awaited()
        await self.birth[0][1](SimpleNamespace(payload="up"))
        self.mqtt.async_publish.assert_awaited_once_with(
            self.hass, "custom/ha/sensor/test/config", "{}",
            qos=1, retain=True,
        )

    async def test_disabled_birth_does_not_subscribe(self):
        self.hass.config_entries.async_entries.return_value = [
            SimpleNamespace(data={}, options={"birth_message": {}})
        ]
        await async_setup_entry(self.hass, self.entry)
        self.mqtt.async_subscribe.assert_not_awaited()
        self.assertEqual(self.entry.async_on_unload.call_count, 4)

    async def test_shutdown_withdraws_availability(self):
        await async_setup_entry(self.hass, self.entry)
        self.mqtt.async_publish.reset_mock()
        await self.shutdown[0](object())
        self.assertEqual(self.mqtt.async_publish.await_count, 2)
        self.mqtt.async_publish.assert_any_await(
            self.hass, "vehicle/coach/j1939/availability", "offline",
            qos=1, retain=True,
        )
        self.mqtt.async_publish.assert_any_await(
            self.hass, "vehicle/coach/j1587/availability", "offline",
            qos=1, retain=True,
        )

    async def test_watchdog_calls_bridge_only_while_broker_connected(self):
        await async_setup_entry(self.hass, self.entry)
        bridge = self.entry.runtime_data.bridge
        bridge.async_check_stale = AsyncMock()
        await self.intervals[0](object())
        bridge.async_check_stale.assert_awaited_once()
        self.mqtt.is_connected.return_value = False
        await self.intervals[0](object())
        bridge.async_check_stale.assert_awaited_once()

    async def test_removal_uses_ledger_after_runtime_data_is_gone(self):
        from custom_components.bluefire.telemetry import Frame

        await async_setup_entry(self.hass, self.entry)
        await self.entry.runtime_data.bridge.async_process_frame(
            Frame(0x18F00400, bytes(8))
        )
        await async_unload_entry(self.hass, self.entry)
        del self.entry.runtime_data
        self.mqtt.async_publish.reset_mock()
        await async_remove_entry(self.hass, self.entry)
        cleared = [
            call.args[1] for call in self.mqtt.async_publish.await_args_list
            if call.args[2] == ""
        ]
        self.assertIn(
            "homeassistant/sensor/bluefire_coach_0_190/config", cleared
        )
        self.assertIn("vehicle/coach/j1939/availability", cleared)

    async def test_offline_removal_is_flushed_on_later_broker_connection(self):
        from custom_components.bluefire.telemetry import Frame

        await async_setup_entry(self.hass, self.entry)
        await self.entry.runtime_data.bridge.async_process_frame(
            Frame(0x18F00400, bytes(8))
        )
        await async_unload_entry(self.hass, self.entry)
        del self.entry.runtime_data
        self.mqtt.is_connected.return_value = False
        self.mqtt.async_publish.reset_mock()
        await async_remove_entry(self.hass, self.entry)
        self.mqtt.async_publish.assert_not_awaited()
        self.assertTrue(
            self.store.async_save.await_args.args[0]["test-entry"]["pending"]
        )
        self.mqtt.is_connected.return_value = True
        # The ledger's independent connection listener survives entry unload.
        self.callbacks[0](True)
        await asyncio.gather(*self.tasks)
        self.assertEqual(self.store.async_save.await_args.args[0], {})

    async def test_removal_without_mqtt_client_keeps_pending_cleanup(self):
        await async_setup_entry(self.hass, self.entry)
        del self.entry.runtime_data
        self.mqtt.is_connected.side_effect = KeyError("mqtt")
        self.mqtt.async_publish.reset_mock()
        await async_remove_entry(self.hass, self.entry)
        self.mqtt.async_publish.assert_not_awaited()
        self.assertTrue(
            self.store.async_save.await_args.args[0]["test-entry"]["pending"]
        )
