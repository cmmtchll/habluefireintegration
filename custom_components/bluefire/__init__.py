"""Offline-ready BlueFire integration.

The vendor BLE wire protocol is not implemented. Configuring an entry never
starts a speculative subscription or publishes fabricated vehicle data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from .const import DOMAIN, STATUS_PROTOCOL_REQUIRED
from .health import Health

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
    health: Health = field(default_factory=Health)


def CONFIG_SCHEMA(config: dict) -> dict:
    """Reject YAML configuration; BlueFire is configured through the UI."""
    from homeassistant.helpers import config_validation as cv

    return cv.config_entry_only_config_schema(DOMAIN)(config)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register an explicit, read-only GATT inspection action."""
    import voluptuous as vol

    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.core import SupportsResponse
    from homeassistant.exceptions import (
        HomeAssistantError,
        ServiceValidationError,
    )
    from homeassistant.helpers import config_validation as cv

    from .bluetooth import async_capture_report, async_inspect
    from .const import (
        CAPTURE_SECONDS, MAX_CAPTURE_SECONDS, MIN_CAPTURE_SECONDS,
    )

    def loaded_runtime(call):
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
        ):
            raise ServiceValidationError(
                "Select a loaded BlueFire config entry"
            )
        if entry.runtime_data.inspecting:
            raise ServiceValidationError("Inspection is already running")
        return entry, entry.runtime_data

    async def inspect_adapter(call):
        entry, runtime = loaded_runtime(call)
        runtime.inspecting = True
        try:
            runtime.services = await async_inspect(hass, entry.data["address"])
            return {
                "status": STATUS_PROTOCOL_REQUIRED,
                "services": runtime.services,
            }
        except HomeAssistantError as err:
            runtime.health.error("connection_errors", str(err))
            raise
        finally:
            runtime.inspecting = False

    async def capture_notifications(call):
        entry, runtime = loaded_runtime(call)
        runtime.inspecting = True
        try:
            return await async_capture_report(
                hass, entry.data["address"], runtime.health,
                call.data["duration"],
            )
        finally:
            runtime.inspecting = False

    hass.services.async_register(
        DOMAIN,
        "inspect_adapter",
        inspect_adapter,
        schema=vol.Schema({vol.Required("entry_id"): cv.string}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "capture_notifications",
        capture_notifications,
        schema=vol.Schema({
            vol.Required("entry_id"): cv.string,
            vol.Optional("duration", default=CAPTURE_SECONDS): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_CAPTURE_SECONDS, max=MAX_CAPTURE_SECONDS),
            ),
        }),
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Prepare MQTT without claiming an operational BLE receiver."""
    from homeassistant.components import bluetooth, mqtt
    from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
    from homeassistant.core import callback
    from homeassistant.exceptions import (
        ConfigEntryNotReady,
        HomeAssistantError,
    )
    from homeassistant.helpers.event import async_track_time_interval

    from .const import CONF_VEHICLE_ID
    from .mqtt import (
        async_flush_removals,
        async_get_ledger,
        async_publish,
        mqtt_settings,
    )
    from .telemetry import MqttBridge

    health = Health()

    async def publish(topic: str, payload: str, retain: bool) -> None:
        try:
            await async_publish(hass, topic, payload, retain)
        except HomeAssistantError as err:
            health.error("mqtt_errors", f"{topic}: {err}")
            raise
        health.count("mqtt_published")

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
    entry.runtime_data = BlueFireRuntime(bridge, health=health)

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
    address = entry.data.get("address")
    if address:
        # Passive advertisement tracking: RSSI/presence, never a connection.
        @callback
        def advertisement(service_info, change) -> None:
            health.advertisement(service_info.rssi, service_info.source)

        @callback
        def unavailable(service_info) -> None:
            health.unavailable()

        last = bluetooth.async_last_service_info(
            hass, address, connectable=False
        )
        if last is not None:
            health.advertisement(last.rssi, last.source)
        entry.async_on_unload(bluetooth.async_register_callback(
            hass, advertisement,
            bluetooth.BluetoothCallbackMatcher(
                address=address, connectable=False
            ),
            bluetooth.BluetoothScanningMode.PASSIVE,
        ))
        entry.async_on_unload(bluetooth.async_track_unavailable(
            hass, unavailable, address, connectable=False
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
