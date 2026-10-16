"""Expose preparation status without manufacturing engine measurements."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN, STATUS_PROTOCOL_REQUIRED


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
    async_add_entities([ProtocolStatusSensor(entry)])


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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="BlueFire",
        )
