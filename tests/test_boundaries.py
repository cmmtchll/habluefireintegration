"""Test HA/BLE boundaries with mocks, not hardware commissioning."""

import asyncio
import importlib
import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from time import monotonic
import unittest
from unittest.mock import AsyncMock, Mock, patch

from custom_components.bluefire.health import Health
from custom_components.bluefire import (
    CONFIG_SCHEMA,
    async_setup,
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
)


def packet(body):
    """Frame a receive body exactly as the offline decoder expects."""
    from custom_components.bluefire.protocol import receive_checksum

    high, low = len(body) >> 8, len(body) & 255
    return bytes([high, low, high ^ low]) + body + bytes(
        [receive_checksum(body)]
    )


def module(name, **attributes):
    result = ModuleType(name)
    result.__dict__.update(attributes)
    return result


class BoundaryError(Exception):
    pass


class ConnectionFailure(Exception):
    pass


class ServiceSetupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.services = {}

        def register_service(domain, name, handler, **kwargs):
            self.services[name] = handler

        self.service_registration = Mock(side_effect=register_service)
        self.runtime = SimpleNamespace(
            inspecting=False, services=[], health=Health()
        )
        self.receiver = SimpleNamespace(
            async_pause=AsyncMock(), async_resume=Mock()
        )
        self.runtime.receiver = self.receiver
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
                HomeAssistantError=ConnectionFailure,
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
        self.captured = AsyncMock(return_value={"status": "completed"})
        inspect_patch = patch.dict(sys.modules, {
            "custom_components.bluefire.bluetooth": module(
                "custom_components.bluefire.bluetooth",
                async_inspect=self.inspected,
                async_capture_report=self.captured,
            )
        })
        inspect_patch.start()
        self.addCleanup(inspect_patch.stop)
        await async_setup(self.hass, {})
        self.inspect = self.services["inspect_adapter"]
        self.capture = self.services["capture_notifications"]

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
        self.receiver.async_pause.assert_awaited_once()
        self.receiver.async_resume.assert_called_once()
        self.assertFalse(self.runtime.inspecting)

    async def test_inspection_refreshes_receiver_gatt_inventory(self):
        self.runtime.services = [{"uuid": "cached-service"}]
        result = await self.inspect(
            SimpleNamespace(data={"entry_id": "entry"})
        )
        self.assertEqual(
            result,
            {
                "status": "receiver_enabled",
                "services": [{"uuid": "service"}],
            },
        )
        self.inspected.assert_awaited_once_with(
            self.hass, "AA:BB:CC:DD:EE:01"
        )

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

    async def test_inspection_connection_failure_is_counted(self):
        self.inspected.side_effect = ConnectionFailure("not visible")
        with self.assertRaises(ConnectionFailure):
            await self.inspect(SimpleNamespace(data={"entry_id": "entry"}))
        self.assertEqual(
            self.runtime.health.counters["connection_errors"], 1
        )
        self.assertEqual(
            self.runtime.health.last_error, "connection_errors: not visible"
        )

    async def test_capture_service_uses_duration_and_clears_busy_flag(self):
        result = await self.capture(SimpleNamespace(
            data={"entry_id": "entry", "duration": 7}
        ))
        self.assertEqual(result, {"status": "completed"})
        self.captured.assert_awaited_once_with(
            self.hass, "AA:BB:CC:DD:EE:01", self.runtime.health, 7
        )
        self.receiver.async_pause.assert_awaited_once()
        self.receiver.async_resume.assert_called_once()
        self.assertFalse(self.runtime.inspecting)
        self.captured.side_effect = ConnectionFailure("busy")
        with self.assertRaises(ConnectionFailure):
            await self.capture(SimpleNamespace(
                data={"entry_id": "entry", "duration": 7}
            ))
        self.assertFalse(self.runtime.inspecting)

    async def test_capture_service_rejects_concurrent_request(self):
        self.runtime.inspecting = True
        with self.assertRaisesRegex(BoundaryError, "already running"):
            await self.capture(SimpleNamespace(
                data={"entry_id": "entry", "duration": 7}
            ))
        self.captured.assert_not_awaited()

    def test_capture_schema_bounds_duration(self):
        import voluptuous as vol

        schemas = {
            call.args[1]: call.kwargs["schema"]
            for call in self.service_registration.call_args_list
        }
        schema = schemas["capture_notifications"]
        self.assertEqual(schema({"entry_id": "e"})["duration"], 20)
        self.assertEqual(
            schema({"entry_id": "e", "duration": "30"})["duration"], 30
        )
        for value in (4, 61):
            with self.assertRaises(vol.Invalid):
                schema({"entry_id": "e", "duration": value})


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.callbacks = []
        self.tasks = []
        self.receiver_tasks = []
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
        self.client = SimpleNamespace(
            services=[], disconnect=AsyncMock(), start_notify=AsyncMock(),
            stop_notify=AsyncMock(), mtu_size=185,
        )
        self.connect = AsyncMock(return_value=self.client)
        self.receiver_instances = []
        self.advertisement_callbacks = []
        self.unavailable_callbacks = []
        self.service_info = None

        class Receiver:
            def __init__(receiver, *args, **kwargs):
                receiver.args = args
                receiver.kwargs = kwargs
                receiver.stop = Mock()
                receiver.services = []
                receiver.async_pause = AsyncMock()
                receiver.async_resume = Mock()
                self.receiver_instances.append(receiver)

            async def async_run(receiver):
                return None

        self.bluetooth = SimpleNamespace(
            async_ble_device_from_address=Mock(return_value=object()),
            async_last_service_info=Mock(
                side_effect=lambda hass, address, connectable: (
                    self.service_info
                )
            ),
            async_register_callback=Mock(
                side_effect=lambda hass, cb, matcher, mode: (
                    self.advertisement_callbacks.append(
                        (cb, matcher, mode)) or Mock()
                )
            ),
            async_track_unavailable=Mock(
                side_effect=lambda hass, cb, address, connectable: (
                    self.unavailable_callbacks.append(cb) or Mock()
                )
            ),
            BluetoothCallbackMatcher=dict,
            BluetoothScanningMode=SimpleNamespace(PASSIVE="passive"),
            async_scanner_count=Mock(
                side_effect=lambda hass, connectable: 2 if connectable else 3
            ),
            async_address_present=Mock(return_value=True),
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
            "homeassistant.loader": module(
                "homeassistant.loader",
                async_get_integration=AsyncMock(
                    return_value=SimpleNamespace(version="0.4.0")
                ),
            ),
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
            self.receiver_tasks.append(name)
            coroutine.close()
            return Mock()
        task = asyncio.create_task(coroutine, name=name)
        self.tasks.append(task)
        return task

    async def test_setup_starts_live_receiver_without_waiting_for_ble(self):
        self.assertTrue(await async_setup_entry(self.hass, self.entry))
        self.connect.assert_not_awaited()
        self.assertEqual(self.receiver_tasks, ["BlueFire BLE receiver"])
        entries = self.hass.config_entries
        entries.async_forward_entry_setups.assert_awaited_once()
        self.assertEqual(self.mqtt.async_publish.await_count, 2)
        self.mqtt.async_publish.assert_any_await(
            self.hass, "vehicle/coach/j1939/availability", "offline",
            qos=1, retain=True,
        )
        self.assertEqual(self.entry.async_on_unload.call_count, 7)
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
        record = self.store.async_save.await_args.args[0]["test-entry"]
        self.assertTrue(record["pending_offline"])
        self.mqtt.is_connected.return_value = True
        self.callbacks[0](True)
        await asyncio.gather(*self.tasks)
        calls = self.mqtt.async_publish.await_args_list
        self.assertTrue(any(
            call.args[1:3] == (
                "vehicle/coach/j1939/availability", "offline"
            )
            for call in calls
        ))
        self.assertFalse(
            self.store.async_save.await_args.args[0]["test-entry"][
                "pending_offline"
            ]
        )

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
        self.assertEqual(self.entry.async_on_unload.call_count, 6)

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

    def ble_entry(self):
        self.entry.data["address"] = "AA:BB:CC:DD:EE:FF"
        self.entry.unique_id = "AA:BB:CC:DD:EE:FF"
        self.entry.options = {}
        self.service_info = SimpleNamespace(
            name="BlueFire LE", rssi=-71, tx_power=None, source="hci0",
            connectable=True, time=0.0, service_uuids=["b65d50ef"],
            manufacturer_data={65535: b"\x01\x02"},
            service_data={"b65d50ef": b"\x03"},
        )

    def notify_client(self, notifications, *, failing=()):
        """Deliver notifications as soon as each characteristic subscribes."""
        def characteristic(uuid, handle, properties):
            return SimpleNamespace(
                uuid=uuid, handle=handle, properties=properties
            )

        self.client.services = [SimpleNamespace(
            uuid="service", characteristics=[
                characteristic("j1939", 12, ["notify"]),
                characteristic("j1708", 15, ["indicate"]),
                characteristic("write", 18, ["write"]),
            ],
        )]

        async def start_notify(char, callback):
            if char.uuid in failing:
                raise BoundaryError("subscribe refused")
            for uuid, data in notifications:
                if uuid == char.uuid:
                    callback(char, bytearray(data))

        self.client.start_notify.side_effect = start_notify

    async def test_passive_advertisements_track_rssi_without_connecting(self):
        self.ble_entry()
        self.service_info.time = monotonic() - 60
        await async_setup_entry(self.hass, self.entry)
        health = self.entry.runtime_data.health
        self.assertEqual(health.rssi, -71)
        self.assertGreaterEqual(
            (datetime.now(timezone.utc) - health.last_advertisement)
            .total_seconds(),
            59,
        )
        callback, matcher, mode = self.advertisement_callbacks[0]
        self.assertEqual(matcher, {
            "address": "AA:BB:CC:DD:EE:FF", "connectable": False,
        })
        self.assertEqual(mode, "passive")
        callback(SimpleNamespace(rssi=-60, source="proxy"), "change")
        self.assertEqual((health.rssi, health.source), (-60, "proxy"))
        self.unavailable_callbacks[0](SimpleNamespace())
        self.assertFalse(health.present)
        self.assertIsNone(health.rssi)
        self.connect.assert_not_awaited()

    async def test_mqtt_publish_success_and_failure_are_counted(self):
        await async_setup_entry(self.hass, self.entry)
        runtime = self.entry.runtime_data
        published = runtime.health.counters["mqtt_published"]
        self.assertGreater(published, 0)
        self.mqtt.async_publish.side_effect = BoundaryError("broker down")
        with self.assertRaises(BoundaryError):
            await runtime.bridge.publish("topic", "payload", False)
        self.assertEqual(runtime.health.counters["mqtt_errors"], 1)
        self.assertEqual(
            runtime.health.counters["mqtt_published"], published
        )

    async def test_capture_records_raw_notifications_and_failures(self):
        api = importlib.import_module("custom_components.bluefire.bluetooth")
        heartbeat = packet(b"\xff")
        self.notify_client(
            [("j1939", heartbeat[:2]), ("j1939", heartbeat[2:])],
            failing=("j1708",),
        )
        result = await api.async_capture(self.hass, "AA:BB:CC:DD:EE:FF", 0)
        self.assertEqual(
            [item["data"] for item in result["notifications"]],
            [heartbeat[:2], heartbeat[2:]],
        )
        self.assertEqual(result["subscribed"], [{
            "service": "service", "characteristic": "j1939", "handle": 12,
        }])
        self.assertEqual(
            result["subscribe_failures"][0]["error"], "subscribe refused"
        )
        self.assertEqual(result["mtu"], 185)
        self.assertEqual(
            result["services"][0]["characteristics"][0]["handle"], 12
        )
        self.client.stop_notify.assert_awaited_once()
        self.client.disconnect.assert_awaited_once()

    async def test_capture_bounds_notifications_and_ignores_stop_errors(self):
        api = importlib.import_module("custom_components.bluefire.bluetooth")
        self.notify_client([
            ("j1939", b"\x00"), ("j1939", b"\x00\x01"),
            ("j1939", b"\x00\x01\x02"),
        ])
        self.client.stop_notify.side_effect = BoundaryError("gone")
        with patch.object(api, "MAX_CAPTURE_NOTIFICATIONS", 2):
            result = await api.async_capture(self.hass, "AA:BB", 0)
        self.assertEqual(len(result["notifications"]), 2)
        self.assertEqual(result["dropped_notifications"], 1)
        self.assertEqual(result["received_notifications"], 3)
        self.assertEqual(result["received_bytes"], 6)
        self.assertIsNotNone(result["last_received"])
        self.client.disconnect.assert_awaited_once()

    async def test_capture_disconnects_when_unsubscribe_times_out(self):
        api = importlib.import_module("custom_components.bluefire.bluetooth")
        self.notify_client([("j1939", b"\x00")])
        self.client.stop_notify.side_effect = TimeoutError("cleanup timeout")

        with self.assertRaisesRegex(BoundaryError, "cleanup timeout"):
            await api.async_capture(self.hass, "AA:BB", 0)

        self.client.disconnect.assert_awaited_once()

    async def test_capture_failures_are_actionable(self):
        api = importlib.import_module("custom_components.bluefire.bluetooth")
        self.connect.side_effect = BoundaryError("adapter busy")
        with self.assertRaisesRegex(BoundaryError, "adapter busy"):
            await api.async_capture(self.hass, "AA:BB", 0)
        self.bluetooth.async_ble_device_from_address.return_value = None
        with self.assertRaisesRegex(BoundaryError, "not visible"):
            await api.async_capture(self.hass, "AA:BB", 0)

    async def test_diagnostics_dump_state_and_capture_raw_data(self):
        api = importlib.import_module("custom_components.bluefire.diagnostics")
        self.ble_entry()
        await async_setup_entry(self.hass, self.entry)
        pgn = packet(bytes([151, 0, 0xF0, 0x04, 3, 0, 8]) + bytes(8))
        self.notify_client([
            ("j1939", packet(b"\xff")), ("j1939", pgn),
            ("j1939", packet(b"\x07\x01")), ("j1708", b"\x00\x01\x00"),
        ])
        with patch.object(api, "CAPTURE_SECONDS", 0):
            result = await api.async_get_config_entry_diagnostics(
                self.hass, self.entry
            )
        self.assertEqual(result["entry"]["data"]["address"],
                         "AA:BB:CC:DD:EE:FF")
        self.assertEqual(result["integration_version"], "0.4.0")
        self.assertTrue(result["mqtt"]["connected"])
        self.assertEqual(
            result["mqtt"]["ledger"]["record"]["vehicle_id"], "coach"
        )
        self.assertEqual(result["bridge"]["vehicle_id"], "coach")
        self.assertEqual(result["bluetooth"]["scanner_count"], 3)
        advertisement = result["bluetooth"]["last_advertisement"]
        self.assertEqual(advertisement["rssi"], -71)
        self.assertEqual(advertisement["manufacturer_data"], {"65535": "0102"})
        capture = result["capture"]
        self.assertEqual(capture["status"], "completed")
        self.assertEqual(
            [item["hex"] for item in capture["notifications"]][:2],
            [packet(b"\xff").hex(), pgn.hex()],
        )
        stream = capture["analysis"]["totals"]["stream"]
        self.assertEqual(stream["packets"], 3)
        self.assertEqual(stream["heartbeats"], 1)
        self.assertEqual(stream["pgn_reports"], 1)
        self.assertEqual(stream["unknown_commands"], 1)
        self.assertEqual(stream["framing_errors"], 1)
        counters = result["health"]["counters"]
        self.assertEqual(counters["notifications"], 4)
        self.assertEqual(counters["captures"], 1)
        self.assertEqual(
            result["health_before_capture"]["counters"]["captures"], 0
        )
        self.assertFalse(self.entry.runtime_data.inspecting)
        self.assertNotIn("data", capture["notifications"][0])

    async def test_diagnostics_report_busy_failed_and_missing_address(self):
        api = importlib.import_module("custom_components.bluefire.diagnostics")
        await async_setup_entry(self.hass, self.entry)
        self.entry.options = {}
        self.entry.unique_id = None
        self.entry.data.pop("address")
        result = await api.async_get_config_entry_diagnostics(
            self.hass, self.entry
        )
        self.assertIsNone(result["bluetooth"])
        self.assertEqual(result["capture"]["status"], "skipped")
        self.ble_entry()
        self.service_info = None
        self.entry.runtime_data.inspecting = True
        result = await api.async_get_config_entry_diagnostics(
            self.hass, self.entry
        )
        self.assertIn("running", result["capture"]["reason"])
        self.assertIsNone(result["bluetooth"]["last_advertisement"])
        self.entry.runtime_data.inspecting = False
        self.connect.side_effect = BoundaryError("adapter busy")
        result = await api.async_get_config_entry_diagnostics(
            self.hass, self.entry
        )
        self.assertEqual(result["capture"]["status"], "failed")
        self.assertEqual(
            result["health"]["counters"]["connection_errors"], 1
        )
        self.assertFalse(self.entry.runtime_data.inspecting)
        self.hass.data.clear()
        result = await api.async_get_config_entry_diagnostics(
            self.hass, self.entry
        )
        self.assertIsNone(result["mqtt"]["ledger"])
