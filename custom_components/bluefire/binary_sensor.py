"""Native BLE and protocol receive connectivity for the BlueFire device."""

from datetime import timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.entity import EntityCategory

from .sensor import _device_info

SCAN_INTERVAL = timedelta(seconds=15)
PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    """Keep transport and vehicle-bus status visible without MQTT."""
    runtime = entry.runtime_data
    async_add_entities([
        ConnectivitySensor(
            entry, "bluetooth_connectivity", "Bluetooth connectivity",
            lambda: runtime.receiver.connected,
        ),
        ConnectivitySensor(
            entry, "j1708_connectivity", "J1708 telemetry connectivity",
            lambda: runtime.receiver.connected
            and runtime.bridge.j1587.telemetry_connected,
        ),
        ConnectivitySensor(
            entry, "j1939_connectivity", "J1939 telemetry connectivity",
            lambda: runtime.receiver.connected
            and runtime.bridge.telemetry_connected,
        ),
    ])


class ConnectivitySensor(BinarySensorEntity):
    """Read live runtime state, never retained MQTT availability."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = True

    def __init__(self, entry, key, name, value):
        self._value = value
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return self._value()
