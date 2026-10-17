"""Provisional BlueFire BLE receiver and MQTT integration.

The receiver follows documented EZ observations without claiming hardware
validation or inventing CAN identifiers/authentication payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from .const import CONF_J1587_EXTENDED, DOMAIN, STATUS_RECEIVER_ENABLED

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
    receiver: Any = None


def CONFIG_SCHEMA(config: dict) -> dict:
    """Reject YAML configuration; BlueFire is configured through the UI."""
    from homeassistant.helpers import config_validation as cv

    return cv.config_entry_only_config_schema(DOMAIN)(config)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register an explicit, read-only GATT inspection action."""
    import voluptuous as vol

    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.core import SupportsResponse
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
                "Select a loaded BlueFire config entry"
            )
        runtime = entry.runtime_data
        if runtime.inspecting:
            raise ServiceValidationError("Inspection is already running")
        if runtime.services:
            return {
                "status": STATUS_RECEIVER_ENABLED,
                "services": runtime.services,
            }
        runtime.inspecting = True
        try:
            runtime.services = await async_inspect(hass, entry.data["address"])
            return {
                "status": STATUS_RECEIVER_ENABLED,
                "services": runtime.services,
            }
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
    """Prepare MQTT and start the receive-only BLE task."""
    from homeassistant.components import mqtt
    from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
    from homeassistant.core import callback
    from homeassistant.exceptions import ConfigEntryNotReady
    from homeassistant.helpers.event import async_track_time_interval

    from .const import CONF_VEHICLE_ID
    from .mqtt import (
        async_flush_removals,
        async_get_ledger,
        async_publish,
        mqtt_settings,
    )
    from .receiver import BlueFireReceiver
    from .telemetry import MqttBridge

    async def publish(topic: str, payload: str, retain: bool) -> None:
        await async_publish(hass, topic, payload, retain)

    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady(
            "Configure the Home Assistant MQTT integration first"
        )

    settings = mqtt_settings(hass)
    ledger = await async_get_ledger(hass)
    signals = await ledger.async_prepare(
        entry.entry_id, entry.data[CONF_VEHICLE_ID], settings.discovery_prefix
    )

    async def save_discovery(known_signals):
        await ledger.async_save_signals(entry.entry_id, known_signals)

    async def save_j1587(known_signals):
        await ledger.async_save_signals(
            entry.entry_id, known_signals, j1587=True
        )

    bridge = MqttBridge(
        entry.data[CONF_VEHICLE_ID], publish,
        discovery_prefix=settings.discovery_prefix,
        device_name=entry.title,
        known_signals=signals,
        save_discovery=save_discovery,
        known_j1587=await ledger.async_get_j1587(entry.entry_id),
        save_j1587=save_j1587,
    )
    receiver = BlueFireReceiver(
        hass,
        entry.data["address"],
        bridge,
        j1587_extended=entry.data.get(CONF_J1587_EXTENDED),
    )
    entry.runtime_data = BlueFireRuntime(bridge, receiver=receiver)
    entry.runtime_data.services = receiver.services
    entry.async_on_unload(receiver.stop)
    entry.async_create_task(
        hass, receiver.async_run(), "BlueFire BLE receiver"
    )

    async def mqtt_ready() -> None:
        await async_flush_removals(hass, ledger)
        await bridge.async_disconnected()
        await bridge.async_rediscover()

    async def birth_received(message):
        if message.payload == settings.birth_payload:
            await bridge.async_rediscover()

    async def check_freshness(now):
        if mqtt.is_connected(hass):
            await bridge.async_check_stale()

    async def shutdown(event):
        if mqtt.is_connected(hass):
            await bridge.async_disconnected()

    @callback
    def connection_changed(connected: bool) -> None:
        if connected:
            entry.async_create_task(
                hass, mqtt_ready(), "BlueFire MQTT reconnect"
            )

    entry.async_on_unload(
        mqtt.async_subscribe_connection_status(hass, connection_changed)
    )
    if settings.birth_topic:
        entry.async_on_unload(await mqtt.async_subscribe(
            hass, settings.birth_topic, birth_received, qos=1
        ))
    entry.async_on_unload(async_track_time_interval(
        hass, check_freshness, timedelta(seconds=15)
    ))
    entry.async_on_unload(hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP, shutdown
    ))
    if mqtt.is_connected(hass):
        await mqtt_ready()
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform.SENSOR]
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Withdraw availability and unload diagnostic entities."""
    from homeassistant.components import mqtt
    from homeassistant.const import Platform

    if not await hass.config_entries.async_unload_platforms(
        entry, [Platform.SENSOR]
    ):
        return False
    if mqtt.is_connected(hass):
        await entry.runtime_data.bridge.async_disconnected()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Queue retained discovery removal without relying on runtime_data."""
    from .mqtt import async_flush_removals, async_get_ledger

    ledger = await async_get_ledger(hass)
    await ledger.async_queue_removal(entry.entry_id)
    await async_flush_removals(hass, ledger)
