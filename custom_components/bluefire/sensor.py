"""Expose preparation status and receive-quality diagnostics.

No engine measurements are manufactured here; vehicle telemetry uses MQTT.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN, STATUS_PROTOCOL_REQUIRED
from .health import Health

# Counters are in-memory; polling them is cheap and avoids a state write for
# every notification. Captures, errors and presence changes push immediately.
SCAN_INTERVAL = timedelta(seconds=15)
PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    """Add one honest diagnostic entity; telemetry will use MQTT discovery."""
    # Preserve existing entities/devices when correcting a manually entered
    # MAC.
    unique_id = f"{entry.entry_id}_protocol_status"
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            entity.domain == "sensor"
            and entity.unique_id.endswith("_protocol_status")
            and entity.unique_id != unique_id
        ):
            registry.async_update_entity(
                entity.entity_id, new_unique_id=unique_id
            )
    devices = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(devices, entry.entry_id):
        identifiers = {
            identifier for identifier in device.identifiers
            if identifier[0] != DOMAIN
        }
        if identifiers != device.identifiers:
            devices.async_update_device(
                device.id,
                new_identifiers=identifiers | {(DOMAIN, entry.entry_id)},
                name=entry.title,
            )
    health = entry.runtime_data.health
    async_add_entities([ProtocolStatusSensor(entry)] + [
        HealthSensor(entry, health, description)
        for description in HEALTH_SENSORS
    ])


class ProtocolStatusSensor(SensorEntity):
    """Keep the missing vendor protocol visible in the UI."""

    _attr_has_entity_name = True
    _attr_name = "Protocol status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_options = [STATUS_PROTOCOL_REQUIRED]
    _attr_native_value = STATUS_PROTOCOL_REQUIRED
    _attr_should_poll = False

    def __init__(self, entry):
        self._attr_unique_id = f"{entry.entry_id}_protocol_status"
        self._attr_device_info = _device_info(entry)


def _device_info(entry):
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="BlueFire",
    )


@dataclass(frozen=True)
class HealthDescription:
    key: str
    name: str
    value: Callable[[Health], object]
    device_class: str | None = None
    state_class: str | None = None
    unit: str | None = None
    enabled: bool = True
    attributes: Callable[[Health], dict] | None = None


def _counter(key, name, counter, *, enabled=True, attributes=None):
    return HealthDescription(
        key, name, lambda health: health.counters[counter],
        state_class=SensorStateClass.TOTAL_INCREASING, enabled=enabled,
        attributes=attributes,
    )


def _errors(prefix):
    return lambda health: {
        "recent": {
            message: count
            for message, count in health.error_messages.items()
            if message.startswith(f"{prefix}: ")
        },
    }


HEALTH_SENSORS = (
    HealthDescription(
        "last_data_seen", "Last data seen",
        lambda health: health.last_data,
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    HealthDescription(
        "last_advertisement", "Last advertisement",
        lambda health: health.last_advertisement,
        device_class=SensorDeviceClass.TIMESTAMP,
        attributes=lambda health: {
            "present": health.present, "source": health.source,
        },
    ),
    HealthDescription(
        "signal_strength", "Signal strength",
        lambda health: health.rssi,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        unit="dBm",
        attributes=lambda health: {
            "source": health.source,
            "statistics": health.rssi_statistics(),
        },
    ),
    HealthDescription(
        "decode_success_rate", "Decode success rate",
        lambda health: health.decode_success_rate,
        state_class=SensorStateClass.MEASUREMENT,
        unit="%",
    ),
    _counter("notifications", "BLE notifications", "notifications"),
    HealthDescription(
        "bytes_received", "BLE bytes received",
        lambda health: health.counters["bytes"],
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        unit="B", enabled=False,
    ),
    _counter("packets", "Decoded packets", "packets", attributes=(
        lambda health: {
            name: health.counters[name] for name in (
                "heartbeats", "pgn_reports", "j1587_reports", "obd_reports",
            )
        }
    )),
    _counter(
        "framing_errors", "Framing errors", "framing_errors",
        attributes=_errors("framing_errors"),
    ),
    _counter(
        "parse_errors", "Parse errors", "parse_errors",
        attributes=_errors("parse_errors"),
    ),
    HealthDescription(
        "unrecognized_messages", "Unrecognized messages",
        lambda health: health.unrecognized,
        state_class=SensorStateClass.TOTAL_INCREASING,
        attributes=lambda health: {
            "unknown_commands": health.counters["unknown_commands"],
            "unrecognized_pgns": health.counters["unrecognized_pgns"],
        },
    ),
    _counter(
        "connection_errors", "Connection errors", "connection_errors",
        attributes=_errors("connection_errors"),
    ),
    _counter(
        "mqtt_published", "MQTT messages published", "mqtt_published",
        enabled=False,
    ),
    _counter(
        "mqtt_errors", "MQTT publish errors", "mqtt_errors",
        attributes=_errors("mqtt_errors"),
    ),
    _counter(
        "captures", "Diagnostic captures", "captures",
        attributes=lambda health: {
            "last_capture": (
                health.last_capture.isoformat()
                if health.last_capture else None
            ),
            "summary": health.last_capture_summary,
        },
    ),
    HealthDescription(
        "last_error", "Last error",
        lambda health: (
            health.last_error[:255] if health.last_error else None
        ),
        attributes=lambda health: {
            "time": (
                health.last_error_at.isoformat()
                if health.last_error_at else None
            ),
        },
    ),
)


class HealthSensor(SensorEntity):
    """Receive-quality tallies; reset when Home Assistant restarts."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = True

    def __init__(self, entry, health: Health, description: HealthDescription):
        self._health = health
        self._description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_name = description.name
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_native_unit_of_measurement = description.unit
        self._attr_entity_registry_enabled_default = description.enabled
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        return self._description.value(self._health)

    @property
    def extra_state_attributes(self):
        if self._description.attributes is None:
            return None
        return self._description.attributes(self._health)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._health.add_listener(self.async_write_ha_state)
        )
