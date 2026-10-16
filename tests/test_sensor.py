"""Verify stable diagnostic identity across a MAC-address correction."""

import importlib
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_boundaries import module


class SensorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entities = []
        self.devices = []
        self.entity_registry = SimpleNamespace(async_update_entity=Mock())
        self.device_registry = SimpleNamespace(async_update_device=Mock())
        self.modules = patch.dict(sys.modules, {
            "homeassistant": module("homeassistant"),
            "homeassistant.components": module("homeassistant.components"),
            "homeassistant.components.sensor": module(
                "homeassistant.components.sensor",
                SensorDeviceClass=SimpleNamespace(ENUM="enum"),
                SensorEntity=type("SensorEntity", (), {}),
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
                EntityCategory=SimpleNamespace(DIAGNOSTIC="diagnostic"),
            ),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.module_name = "custom_components.bluefire.sensor"
        sys.modules.pop(self.module_name, None)
        self.addCleanup(sys.modules.pop, self.module_name, None)
        self.api = importlib.import_module(self.module_name)
        self.entry = SimpleNamespace(
            entry_id="stable-entry-id",
            unique_id="AA:BB:CC:DD:EE:01",
            title="Coach adapter",
        )

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
        self.assertEqual(other._attr_native_value, "protocol_required")

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
