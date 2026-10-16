"""Offline-ready BlueFire integration.

The vendor BLE wire protocol is not implemented. Configuring an entry never
starts a speculative subscription or publishes fabricated vehicle data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .const import DOMAIN, STATUS_PROTOCOL_REQUIRED

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .telemetry import MqttBridge


@dataclass
class BlueFireRuntime:
    """Data owned by one config entry."""

    bridge: MqttBridge
    services: list[dict[str, Any]] = field(default_factory=list)
    inspecting: bool = False


def CONFIG_SCHEMA(config: dict) -> dict:
    """Reject YAML configuration; BlueFire is configured through the UI."""
    from homeassistant.helpers import config_validation as cv

    return cv.config_entry_only_config_schema(DOMAIN)(config)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register an explicit, read-only GATT inspection action."""
    import voluptuous as vol

    from homeassistant.core import SupportsResponse
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.helpers import config_validation as cv

    from .bluetooth import async_inspect

    async def inspect_adapter(call):
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
        ):
            raise ServiceValidationError(
                "Select a loaded BlueFire config entry")
        runtime = entry.runtime_data
        if runtime.inspecting:
            raise ServiceValidationError("Inspection is already running")
        runtime.inspecting = True
        try:
            runtime.services = await async_inspect(hass, entry.data["address"])
            return {
                "status": STATUS_PROTOCOL_REQUIRED,
                "services": runtime.services}
        finally:
            runtime.inspecting = False

    hass.services.async_register(
        DOMAIN,
        "inspect_adapter",
        inspect_adapter,
        schema=vol.Schema({vol.Required("entry_id"): cv.string}),
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Prepare MQTT without claiming an operational BLE receiver."""
    from homeassistant.components import mqtt
    from homeassistant.const import Platform
    from homeassistant.core import callback
    from homeassistant.exceptions import ConfigEntryNotReady

    from .const import CONF_VEHICLE_ID
    from .telemetry import MqttBridge

    async def publish(topic: str, payload: str, retain: bool) -> None:
        await mqtt.async_publish(hass, topic, payload, qos=0, retain=retain)

    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady(
            "Configure the Home Assistant MQTT integration first")

    bridge = MqttBridge(entry.data[CONF_VEHICLE_ID], publish)
    entry.runtime_data = BlueFireRuntime(bridge)

    async def mqtt_ready() -> None:
        await bridge.async_disconnected()
        await bridge.async_rediscover()

    @callback
    def connection_changed(connected: bool) -> None:
        if connected:
            entry.async_create_task(
                hass, mqtt_ready(), "BlueFire MQTT reconnect")

    entry.async_on_unload(
        mqtt.async_subscribe_connection_status(hass, connection_changed)
    )
    if mqtt.is_connected(hass):
        await mqtt_ready()
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform.SENSOR]
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Withdraw availability and unload diagnostic entities."""
    from homeassistant.const import Platform
    from homeassistant.components import mqtt

    if not await hass.config_entries.async_unload_platforms(
        entry, [Platform.SENSOR]
    ):
        return False
    if mqtt.is_connected(hass):
        await entry.runtime_data.bridge.async_disconnected()
    return True
