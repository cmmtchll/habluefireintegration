"""Verify diagnostic entities and stable identity across MAC corrections."""

import asyncio
from datetime import datetime, timezone
import importlib
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_boundaries import module
from custom_components.bluefire.protocol import J1587Report
from custom_components.bluefire.telemetry import Frame, MqttBridge


class SensorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entities = []
        self.devices = []
        self.entity_registry = SimpleNamespace(async_update_entity=Mock())
        self.device_registry = SimpleNamespace(async_update_device=Mock())
        self.modules = patch.dict(sys.modules, {
            "homeassistant": module("homeassistant"),
            "homeassistant.components": module("homeassistant.components"),
            "homeassistant.components.binary_sensor": module(
                "homeassistant.components.binary_sensor",
                BinarySensorDeviceClass=SimpleNamespace(
                    CONNECTIVITY="connectivity",
                ),
                BinarySensorEntity=type("BinarySensorEntity", (), {}),
            ),
            "homeassistant.components.sensor": module(
                "homeassistant.components.sensor",
                SensorDeviceClass=SimpleNamespace(
                    ENUM="enum", TIMESTAMP="timestamp",
                    SIGNAL_STRENGTH="signal_strength", DATA_SIZE="data_size",
                ),
                SensorStateClass=SimpleNamespace(
                    MEASUREMENT="measurement",
                    TOTAL_INCREASING="total_increasing",
                ),
                SensorEntity=type("SensorEntity", (), {
                    "async_on_remove": lambda self, func: (
                        self.removers.append(func)
                    ),
                    "async_write_ha_state": lambda self: (
                        self.writes.append(self.native_value)
                    ),
                }),
            ),
            "homeassistant.components.switch": module(
                "homeassistant.components.switch",
                SwitchEntity=type("SwitchEntity", (), {}),
            ),
            "homeassistant.components.button": module(
                "homeassistant.components.button",
                ButtonEntity=type("ButtonEntity", (), {}),
            ),
            "homeassistant.exceptions": module(
                "homeassistant.exceptions",
                HomeAssistantError=RuntimeError,
                ServiceValidationError=ValueError,
            ),
            "homeassistant.helpers": module(
                "homeassistant.helpers",
                entity_registry=SimpleNamespace(
                    async_get=lambda hass: self.entity_registry,
                    async_entries_for_config_entry=lambda reg, eid: (
                        self.entities
                    ),
                ),
                device_registry=SimpleNamespace(
                    async_get=lambda hass: self.device_registry,
                    async_entries_for_config_entry=lambda reg, eid: (
                        self.devices
                    ),
                ),
            ),
            "homeassistant.helpers.entity": module(
                "homeassistant.helpers.entity",
                DeviceInfo=dict,
                EntityCategory=SimpleNamespace(
                    DIAGNOSTIC="diagnostic", CONFIG="config",
                ),
            ),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.module_name = "custom_components.bluefire.sensor"
        sys.modules.pop(self.module_name, None)
        self.addCleanup(sys.modules.pop, self.module_name, None)
        self.api = importlib.import_module(self.module_name)
        binary_module = "custom_components.bluefire.binary_sensor"
        sys.modules.pop(binary_module, None)
        self.addCleanup(sys.modules.pop, binary_module, None)
        self.binary_api = importlib.import_module(binary_module)
        for name in ("switch", "button"):
            module_name = f"custom_components.bluefire.{name}"
            sys.modules.pop(module_name, None)
            self.addCleanup(sys.modules.pop, module_name, None)
            setattr(self, f"{name}_api", importlib.import_module(module_name))
        from custom_components.bluefire.health import Health

        self.health = Health(
            clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        self.publish = AsyncMock()
        self.bridge = MqttBridge("coach", self.publish)
        self.unloaders = []
        self.entry = SimpleNamespace(
            entry_id="stable-entry-id",
            unique_id="AA:BB:CC:DD:EE:01",
            title="Coach adapter",
            options={"unrelated_option": True},
            runtime_data=SimpleNamespace(
                health=self.health, bridge=self.bridge,
                receiver=SimpleNamespace(
                    connected=False, async_pause=AsyncMock(),
                    async_resume=Mock(),
                ),
                bluetooth_enabled=True, inspecting=False,
            ),
            async_on_unload=self.unloaders.append,
        )

    async def sensors(self):
        added = Mock()
        await self.api.async_setup_entry(object(), self.entry, added)
        return {
            entity._attr_unique_id.removeprefix("stable-entry-id_"): entity
            for entity in added.call_args.args[0]
        }

    async def controls(self):
        self.hass = SimpleNamespace(
            config_entries=SimpleNamespace(
                async_update_entry=Mock(
                    side_effect=lambda entry, options: setattr(
                        entry, "options", options,
                    ),
                ),
            ),
            services=SimpleNamespace(
                async_call=AsyncMock(return_value={"count": 2}),
            ),
        )
        switches, buttons = Mock(), Mock()
        await self.switch_api.async_setup_entry(
            self.hass, self.entry, switches,
        )
        await self.button_api.async_setup_entry(
            self.hass, self.entry, buttons,
        )
        switch, = switches.call_args.args[0]
        actions = {
            entity._attr_translation_key: entity
            for entity in buttons.call_args.args[0]
        }
        for entity in (switch, *actions.values()):
            entity.hass = self.hass
            entity.removers = []
            entity.async_on_remove = entity.removers.append
            entity.async_write_ha_state = Mock()
            await entity.async_added_to_hass()
        return switch, actions

    async def test_device_controls_share_stable_identity_and_translations(
        self,
    ):
        import json
        from pathlib import Path

        switch, buttons = await self.controls()
        folder = Path(__file__).resolve().parents[1] / (
            "custom_components"
        ) / "bluefire"
        strings = json.loads((folder / "strings.json").read_text("utf-8"))
        english = json.loads(
            (folder / "translations" / "en.json").read_text("utf-8")
        )
        self.assertEqual(strings["entity"], english["entity"])
        self.assertEqual(switch._attr_entity_category, "config")
        self.assertIn(switch._attr_translation_key,
                      strings["entity"]["switch"])
        self.assertEqual(set(buttons), {
            "read_fuel_level", "read_diagnostic_codes", "read_odometer",
            "read_engine_hours", "read_total_fuel_used",
            "read_software_identification", "read_vehicle_identification",
            "read_component_identification", "inspect_adapter",
            "capture_notifications", "reconnect_bluetooth",
            "cleanup_preview", "cleanup_mqtt",
        })
        for key, button in buttons.items():
            self.assertIn(key, strings["entity"]["button"])
            self.assertEqual(button._attr_entity_category, "diagnostic")
        self.entry.unique_id = "AA:BB:CC:DD:EE:02"
        for entity in (switch, *buttons.values()):
            self.assertEqual(
                entity._attr_device_info["identifiers"],
                {("bluefire", self.entry.entry_id)},
            )
            self.assertTrue(entity._attr_unique_id.startswith(
                f"{self.entry.entry_id}_"
            ))
            entity.async_write_ha_state.reset_mock()
        self.health.notify()
        for entity in (switch, *buttons.values()):
            entity.async_write_ha_state.assert_called_once()
            entity.removers[0]()
            entity.async_write_ha_state.reset_mock()
        self.health.notify()
        for entity in (switch, *buttons.values()):
            entity.async_write_ha_state.assert_not_called()

    async def test_switch_disconnects_persists_and_resumes_without_reload(
        self,
    ):
        switch, buttons = await self.controls()
        sensors = await self.sensors()
        status = sensors["protocol_status"]
        status.removers, status.writes = [], []
        await status.async_added_to_hass()
        await self.bridge.async_process_frame(
            Frame((6 << 26) | (61444 << 8), bytes(8))
        )
        self.assertTrue(self.bridge.telemetry_connected)
        await switch.async_turn_off()
        self.assertFalse(switch.is_on)
        self.assertFalse(self.bridge.telemetry_connected)
        self.assertEqual(status.native_value, "receiver_disabled")
        self.assertEqual(status.writes[-1], "receiver_disabled")
        self.assertEqual(self.entry.options, {
            "unrelated_option": True, "bluetooth_enabled": False,
        })
        receiver = self.entry.runtime_data.receiver
        receiver.async_pause.assert_awaited_once()
        receiver.async_resume.assert_not_called()
        for key, button in buttons.items():
            self.assertEqual(button.available, key.startswith("cleanup"))
        await switch.async_turn_off()
        receiver.async_pause.assert_awaited_once()
        await switch.async_turn_on()
        self.assertTrue(switch.is_on)
        self.assertEqual(status.native_value, "receiver_enabled")
        self.assertTrue(self.entry.options["bluetooth_enabled"])
        receiver.async_resume.assert_called_once()
        self.assertTrue(all(button.available for button in buttons.values()))
        self.assertFalse(self.entry.runtime_data.inspecting)
        status.removers[0]()

    async def test_switch_rejects_busy_and_recovers_failed_pause(self):
        switch, _ = await self.controls()
        runtime = self.entry.runtime_data
        runtime.inspecting = True
        with self.assertRaisesRegex(ValueError, "already running"):
            await switch.async_turn_off()
        runtime.inspecting = False
        runtime.receiver.async_pause.side_effect = RuntimeError("close failed")
        with self.assertRaisesRegex(RuntimeError, "close failed"):
            await switch.async_turn_off()
        self.assertTrue(switch.is_on)
        self.assertNotIn("bluetooth_enabled", self.entry.options)
        runtime.receiver.async_resume.assert_called_once()
        self.assertFalse(runtime.inspecting)
        self.assertEqual(self.health.counters["connection_errors"], 1)
        runtime.receiver.async_pause.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await switch.async_turn_off()
        self.assertTrue(switch.is_on)
        self.assertFalse(runtime.inspecting)
        self.assertNotIn("bluetooth_enabled", self.entry.options)
        self.assertEqual(runtime.receiver.async_resume.call_count, 2)
        runtime.receiver.async_pause.side_effect = None
        self.publish.side_effect = RuntimeError("MQTT offline")
        with self.assertRaisesRegex(RuntimeError, "MQTT offline"):
            await switch.async_turn_off()
        self.assertFalse(switch.is_on)
        self.assertFalse(self.entry.options["bluetooth_enabled"])
        self.assertFalse(runtime.inspecting)
        self.assertEqual(self.health.counters["mqtt_errors"], 1)

    async def test_buttons_delegate_device_actions_and_surface_cleanup_result(
        self,
    ):
        _, buttons = await self.controls()
        for key, button in buttons.items():
            await button.async_press()
            data = {"entry_id": self.entry.entry_id}
            service = key
            if key.startswith("cleanup"):
                data["dry_run"] = key == "cleanup_preview"
                service = "cleanup_mqtt"
                self.assertEqual(
                    button.extra_state_attributes, {"result": {"count": 2}},
                )
            else:
                self.assertIsNone(button.extra_state_attributes)
            self.hass.services.async_call.assert_awaited_with(
                "bluefire", service, data,
                blocking=True, return_response=True,
            )
        self.hass.services.async_call.side_effect = RuntimeError("busy")
        for key in ("cleanup_preview", "read_fuel_level"):
            with self.assertRaisesRegex(RuntimeError, "busy"):
                await buttons[key].async_press()
        self.assertEqual(
            buttons["cleanup_preview"].extra_state_attributes,
            {"result": None},
        )

    async def test_health_sensors_are_diagnostic_and_stable(self):
        sensors = await self.sensors()
        self.assertIn("protocol_status", sensors)
        for key in (
            "last_data_seen", "last_advertisement", "signal_strength",
            "decode_success_rate", "notifications", "bytes_received",
            "packets", "framing_errors", "parse_errors",
            "unrecognized_messages", "connection_errors", "mqtt_published",
            "mqtt_errors", "captures", "last_error",
        ):
            sensor = sensors[key]
            self.assertEqual(sensor._attr_entity_category, "diagnostic")
            self.assertEqual(
                sensor._attr_device_info["identifiers"],
                {("bluefire", "stable-entry-id")},
            )
        self.assertFalse(
            sensors["bytes_received"]._attr_entity_registry_enabled_default
        )
        self.assertEqual(
            sensors["signal_strength"]._attr_native_unit_of_measurement,
            "dBm",
        )
        self.assertEqual(
            sensors["framing_errors"]._attr_state_class, "total_increasing"
        )

    async def test_native_connectivity_separates_ble_and_vehicle_protocols(
        self,
    ):
        added = Mock()
        await self.binary_api.async_setup_entry(
            object(), self.entry, added,
        )
        ble, j1708, j1939 = added.call_args.args[0]
        for sensor in (ble, j1708, j1939):
            self.assertEqual(sensor._attr_device_class, "connectivity")
            self.assertEqual(sensor._attr_entity_category, "diagnostic")
            self.assertTrue(sensor._attr_should_poll)
            self.assertEqual(
                sensor._attr_device_info["identifiers"],
                {("bluefire", "stable-entry-id")},
            )
            self.assertFalse(sensor.is_on)
        self.assertEqual(j1708._attr_unique_id,
                         "stable-entry-id_j1708_connectivity")
        self.entry.runtime_data.receiver.connected = True
        self.assertTrue(ble.is_on)
        self.assertFalse(j1708.is_on)
        self.assertFalse(j1939.is_on)
        await self.bridge.async_process_j1587(
            J1587Report(128, 190, bytes(2))
        )
        self.assertTrue(j1708.is_on)
        self.assertFalse(j1939.is_on)
        await self.bridge.async_process_frame(
            Frame((6 << 26) | (61444 << 8), bytes(8))
        )
        self.assertTrue(j1939.is_on)
        self.entry.runtime_data.receiver.connected = False
        self.assertFalse(ble.is_on)
        self.assertFalse(j1708.is_on)
        self.assertFalse(j1939.is_on)
        for sensor in (ble, j1708, j1939):
            removers = []
            sensor.async_on_remove = removers.append
            sensor.async_write_ha_state = Mock()
            await sensor.async_added_to_hass()
            self.health.notify()
            sensor.async_write_ha_state.assert_called_once()
            removers[0]()
            sensor.async_write_ha_state.reset_mock()
            self.health.notify()
            sensor.async_write_ha_state.assert_not_called()

    async def test_health_sensor_values_and_attributes(self):
        sensors = await self.sensors()
        self.assertIsNone(sensors["last_data_seen"].native_value)
        self.assertIsNone(sensors["last_error"].native_value)
        self.assertIsNone(sensors["notifications"].extra_state_attributes)
        self.assertEqual(
            sensors["captures"].extra_state_attributes,
            {"last_capture": None, "summary": None},
        )
        self.assertIsNone(
            sensors["last_error"].extra_state_attributes["time"]
        )
        self.health.advertisement(-70, "hci0")
        self.health.data_seen()
        self.health.count("packets", 3)
        self.health.count("heartbeats")
        self.health.count("unknown_commands", 2)
        self.health.error("framing_errors", "Invalid receive length XOR")
        self.health.error("mqtt_errors", "x" * 300)
        self.health.capture_completed({"packets": 3})
        self.assertEqual(sensors["signal_strength"].native_value, -70)
        self.assertEqual(
            sensors["signal_strength"].extra_state_attributes["statistics"],
            {"samples": 1, "min": -70, "max": -70, "mean": -70.0,
             "spread": 0},
        )
        self.assertEqual(
            sensors["last_data_seen"].native_value,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(sensors["packets"].native_value, 3)
        self.assertEqual(
            sensors["packets"].extra_state_attributes["heartbeats"], 1
        )
        self.assertEqual(sensors["unrecognized_messages"].native_value, 2)
        self.assertEqual(sensors["decode_success_rate"].native_value, 75.0)
        self.assertEqual(
            sensors["framing_errors"].extra_state_attributes,
            {"recent": {"framing_errors: Invalid receive length XOR": 1}},
        )
        self.assertEqual(len(sensors["last_error"].native_value), 255)
        self.assertEqual(
            sensors["captures"].extra_state_attributes["last_capture"],
            "2026-01-01T00:00:00+00:00",
        )
        self.assertEqual(
            sensors["last_advertisement"].extra_state_attributes,
            {"present": True, "source": "hci0"},
        )
        self.assertEqual(
            sensors["last_error"].extra_state_attributes["time"],
            "2026-01-01T00:00:00+00:00",
        )

    async def test_health_sensors_push_significant_events(self):
        sensor = (await self.sensors())["connection_errors"]
        sensor.removers, sensor.writes = [], []
        await sensor.async_added_to_hass()
        self.health.count("connection_errors")
        self.assertEqual(sensor.writes, [])
        self.health.error("connection_errors", "not visible")
        self.assertEqual(sensor.writes, [2])
        sensor.removers[0]()
        self.health.unavailable()
        self.assertEqual(sensor.writes, [2])

    async def test_status_entity_does_not_use_mutable_mac(self):
        added = Mock()
        await self.api.async_setup_entry(object(), self.entry, added)
        sensor = added.call_args.args[0][0]
        self.assertEqual(
            sensor._attr_unique_id, "stable-entry-id_protocol_status"
        )
        self.assertEqual(
            sensor._attr_device_info["identifiers"],
            {("bluefire", "stable-entry-id")},
        )
        self.entry.unique_id = "AA:BB:CC:DD:EE:02"
        other = self.api.ProtocolStatusSensor(self.entry)
        self.assertEqual(other._attr_unique_id, sensor._attr_unique_id)
        self.assertEqual(other.native_value, "receiver_enabled")

    async def test_legacy_mac_identity_is_migrated_in_place(self):
        self.entities = [
            SimpleNamespace(
                entity_id="sensor.protocol_status",
                unique_id="AA:BB:CC:DD:EE:01_protocol_status",
                domain="sensor",
            )
        ]
        self.devices = [
            SimpleNamespace(
                id="device-id",
                identifiers={
                    ("bluefire", "AA:BB:CC:DD:EE:01"),
                    ("other_domain", "other-id"),
                },
            )
        ]
        await self.api.async_setup_entry(object(), self.entry, Mock())
        self.entity_registry.async_update_entity.assert_called_once_with(
            "sensor.protocol_status",
            new_unique_id="stable-entry-id_protocol_status",
        )
        self.device_registry.async_update_device.assert_called_once_with(
            "device-id",
            new_identifiers={
                ("bluefire", "stable-entry-id"), ("other_domain", "other-id"),
            },
            name="Coach adapter",
        )

    async def test_existing_stable_entity_is_not_recreated(self):
        self.entities = [
            SimpleNamespace(
                entity_id="sensor.protocol_status",
                unique_id="stable-entry-id_protocol_status",
                domain="sensor",
            ),
            SimpleNamespace(
                entity_id="sensor.unrelated",
                unique_id="unrelated",
                domain="sensor",
            ),
        ]
        self.devices = [
            SimpleNamespace(id="unrelated", identifiers={("other", "id")})
        ]
        await self.api.async_setup_entry(object(), self.entry, Mock())
        self.entity_registry.async_update_entity.assert_not_called()
        self.device_registry.async_update_device.assert_not_called()

    async def test_identification_sensors_are_discovered_per_mid_and_pid(self):
        added = Mock()
        await self.api.async_setup_entry(object(), self.entry, added)
        self.assertEqual(added.call_count, 1)
        await self.bridge.async_process_j1587(J1587Report(128, 190, bytes(2)))
        self.assertEqual(added.call_count, 1)
        for mid, pid, value in (
            (128, 243, b"EXAMPLE ENGINE"),
            (130, 243, b"EXAMPLE TRANSMISSION"),
            (128, 234, b"EXAMPLE SOFTWARE"),
            (128, 237, b"EXAMPLE VIN"),
            (175, 243, b"\x01\xff"),
        ):
            await self.bridge.async_process_j1587(J1587Report(mid, pid, value))
            sensor, = added.call_args.args[0]
            self.assertEqual(
                sensor._attr_unique_id,
                f"stable-entry-id_j1587_{mid}_{pid}_identification",
            )
            self.assertEqual(sensor._attr_device_info,
                             self.api._device_info(self.entry))
            self.assertEqual(sensor._attr_device_info["manufacturer"],
                             "BlueFire")
            self.assertEqual(sensor._attr_entity_category, "diagnostic")
            self.assertFalse(sensor._attr_should_poll)
            self.assertEqual(sensor.extra_state_attributes["mid"], mid)
            self.assertEqual(sensor.extra_state_attributes["pid"], pid)
            self.assertEqual(
                sensor.extra_state_attributes["data"], value.hex()
            )
            self.assertTrue(sensor.available)
        self.assertIsNone(sensor.native_value)
        self.assertEqual(sensor.extra_state_attributes["decode_status"],
                         "unsupported_encoding")
        self.assertEqual(sensor._attr_name,
                         "Controller (175): Component identification")
        self.assertEqual(added.call_count, 6)

    async def test_native_identification_updates_without_mqtt_and_cleans_up(
        self,
    ):
        added = Mock()
        await self.api.async_setup_entry(object(), self.entry, added)
        self.publish.side_effect = RuntimeError("MQTT unavailable")
        with self.assertRaisesRegex(RuntimeError, "MQTT unavailable"):
            await self.bridge.async_process_j1587(
                J1587Report(128, 243, b"EXAMPLE ENGINE")
            )
        sensor, = added.call_args.args[0]
        sensor.removers, sensor.writes = [], []
        await sensor.async_added_to_hass()
        self.assertEqual(sensor.native_value, "EXAMPLE ENGINE")
        self.assertEqual(sensor.writes, ["EXAMPLE ENGINE"])
        self.entry.unique_id = "AA:BB:CC:DD:EE:02"
        with self.assertRaisesRegex(RuntimeError, "MQTT unavailable"):
            await self.bridge.async_process_j1587(
                J1587Report(128, 243, b"UPDATED ENGINE")
            )
        self.assertEqual(added.call_count, 2)
        self.assertEqual(sensor.writes[-1], "UPDATED ENGINE")
        self.assertEqual(sensor._attr_unique_id,
                         "stable-entry-id_j1587_128_243_identification")
        self.publish.side_effect = None
        await self.bridge.async_disconnected(clear_identification=False)
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, "UPDATED ENGINE")
        self.publish.side_effect = RuntimeError("MQTT unavailable")
        with self.assertRaisesRegex(RuntimeError, "MQTT unavailable"):
            await self.bridge.async_disconnected()
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, "UPDATED ENGINE")
        self.assertEqual(sensor.extra_state_attributes["value_basis"],
                         "last_observed")
        self.assertEqual(sensor.writes[-1], "UPDATED ENGINE")
        self.publish.side_effect = None
        await self.bridge.async_process_j1587(
            J1587Report(128, 243, b"RECONNECTED ENGINE")
        )
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, "RECONNECTED ENGINE")
        self.assertEqual(added.call_count, 2)
        sensor.removers[0]()
        self.unloaders[0]()
        count = len(sensor.writes)
        await self.bridge.async_process_j1587(
            J1587Report(130, 243, b"EXAMPLE TRANSMISSION")
        )
        await self.bridge.async_disconnected()
        self.assertEqual(len(sensor.writes), count)
        self.assertEqual(added.call_count, 2)

    async def test_native_identification_present_before_platform_setup(self):
        await self.bridge.async_process_j1587(
            J1587Report(128, 234, b"EARLY SOFTWARE RESPONSE")
        )
        added = Mock()
        await self.api.async_setup_entry(object(), self.entry, added)
        self.assertEqual(added.call_count, 2)
        sensor, = added.call_args.args[0]
        self.assertEqual(sensor.native_value, "EARLY SOFTWARE RESPONSE")
        await self.bridge.async_disconnected()
        sensor.removers, sensor.writes = [], []
        await sensor.async_added_to_hass()
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.writes, ["EARLY SOFTWARE RESPONSE"])
