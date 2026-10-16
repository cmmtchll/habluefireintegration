"""Expose preparation status without manufacturing engine measurements."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN, STATUS_PROTOCOL_REQUIRED


async def async_setup_entry(hass, entry, async_add_entities):
    """Add one honest diagnostic entity; telemetry will use MQTT discovery."""
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
        self._attr_unique_id = f"{entry.unique_id}_protocol_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="BlueFire",
        )
