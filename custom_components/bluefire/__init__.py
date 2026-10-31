"""Provisional BlueFire BLE receiver and MQTT integration.

The receiver follows documented EZ observations without claiming hardware
validation or inventing CAN identifiers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import TYPE_CHECKING, Any

from .const import (
    CONF_ENGINE_PROFILE,
    CONF_J1587_EXTENDED,
    CONF_J1708_STARTUP,
    DOMAIN,
    J1708_READ_ACTIONS,
    MQTT_PUBLISH_TIMEOUT,
    STATUS_RECEIVER_ENABLED,
)
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
    receiver: Any = None
    health: Health = field(default_factory=Health)


def CONFIG_SCHEMA(config: dict) -> dict:
    """Reject YAML configuration; BlueFire is configured through the UI."""
    from homeassistant.helpers import config_validation as cv

    return cv.config_entry_only_config_schema(DOMAIN)(config)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register inspection, capture and explicit J1708 read actions."""
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
            raise ServiceValidationError(
                "Another BlueFire action is already running"
            )
        return entry, entry.runtime_data

    async def inspect_adapter(call):
        entry, runtime = loaded_runtime(call)
        runtime.inspecting = True
        paused = False
        try:
            if runtime.receiver is not None:
                await runtime.receiver.async_pause()
                paused = True
            runtime.services = await async_inspect(hass, entry.data["address"])
            return {
                "status": STATUS_RECEIVER_ENABLED,
                "services": runtime.services,
            }
        except HomeAssistantError as err:
            runtime.health.error("connection_errors", str(err))
            raise
        finally:
            if runtime.receiver is not None and paused:
                runtime.receiver.async_resume()
            runtime.inspecting = False

    async def capture_notifications(call):
        entry, runtime = loaded_runtime(call)
        runtime.inspecting = True
        paused = False
        try:
            if runtime.receiver is not None:
                await runtime.receiver.async_pause()
                paused = True
            return await async_capture_report(
                hass, entry.data["address"], runtime.health,
                call.data["duration"],
            )
        finally:
            if runtime.receiver is not None and paused:
                runtime.receiver.async_resume()
            runtime.inspecting = False

    async def read_vehicle(call):
        _, runtime = loaded_runtime(call)
        if runtime.receiver is None:
            raise ServiceValidationError("BlueFire receiver is not running")
        runtime.inspecting = True
        try:
            pid = (
                call.data["pid"] if call.service == "read_parameter"
                else J1708_READ_ACTIONS[call.service]
            )
            if call.data.get("mid", 0):
                return await runtime.receiver.async_read(
                    pid, mid=call.data["mid"],
                )
            return await runtime.receiver.async_read(pid)
        except HomeAssistantError as err:
            runtime.health.error("connection_errors", str(err))
            raise
        finally:
            runtime.inspecting = False

    async def cleanup_mqtt(call):
        from homeassistant.components import mqtt

        from .mqtt import async_confirm_removal

        _, runtime = loaded_runtime(call)
        dry_run = call.data.get("dry_run", True)
        if not dry_run and not mqtt.is_connected(hass):
            raise ServiceValidationError("MQTT must be connected for cleanup")
        runtime.inspecting = True
        try:
            return await runtime.bridge.async_cleanup_unobserved(
                lambda topic: async_confirm_removal(hass, topic),
                dry_run=dry_run,
            )
        except (HomeAssistantError, TimeoutError) as err:
            runtime.health.error("mqtt_errors", f"MQTT cleanup failed: {err}")
            raise HomeAssistantError(
                "MQTT cleanup was not confirmed; ownership is retained "
                f"for retry: {err}"
            ) from err
        finally:
            runtime.inspecting = False

    hass.services.async_register(
        DOMAIN, "cleanup_mqtt", cleanup_mqtt,
        schema=vol.Schema({
            vol.Required("entry_id"): cv.string,
            vol.Optional("dry_run", default=True): bool,
        }),
        supports_response=SupportsResponse.ONLY,
    )

    from .catalog import lookup
    from .j1587 import READABLE_PIDS

    for service in (*J1708_READ_ACTIONS, "read_parameter"):
        schema = {
            vol.Required("entry_id"): cv.string,
            vol.Optional("mid"): vol.All(
                vol.Coerce(int), vol.Any(0, vol.Range(min=128, max=255)),
            ),
        }
        if service == "read_parameter":
            schema[vol.Required("pid")] = vol.All(
                vol.Coerce(int),
                vol.In({pid: lookup("pid", pid)["name"]
                        for pid in READABLE_PIDS}),
            )
        hass.services.async_register(
            DOMAIN, service, read_vehicle,
            schema=vol.Schema(schema),
            supports_response=SupportsResponse.ONLY,
        )

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
    """Prepare MQTT and start the BLE telemetry task."""
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
    from .receiver import BlueFireReceiver
    from .telemetry import MqttBridge

    health = Health()

    async def publish(topic: str, payload: str, retain: bool) -> None:
        try:
            async with asyncio.timeout(MQTT_PUBLISH_TIMEOUT):
                await async_publish(hass, topic, payload, retain)
        except TimeoutError as err:
            health.error("mqtt_errors", f"{topic}: publish timed out")
            raise HomeAssistantError(
                f"MQTT publish timed out for {topic}"
            ) from err
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
        entry.entry_id, entry.data[CONF_VEHICLE_ID], settings.discovery_prefix,
    )

    async def save_discovery(known_signals):
        await ledger.async_save_signals(entry.entry_id, known_signals)

    async def save_j1587(known_signals):
        await ledger.async_save_signals(
            entry.entry_id, known_signals, j1587=True
        )

    async def save_identification(reports):
        await ledger.async_save_identification(entry.entry_id, reports)

    bridge = MqttBridge(
        entry.data[CONF_VEHICLE_ID], publish,
        discovery_prefix=settings.discovery_prefix,
        device_name=entry.title,
        known_signals=signals,
        save_discovery=save_discovery,
        known_j1587=await ledger.async_get_j1587(entry.entry_id),
        save_j1587=save_j1587,
        j1708_polling=entry.data.get(CONF_J1708_STARTUP, False),
        engine_profile=entry.data.get(CONF_ENGINE_PROFILE, "generic"),
        known_identification=await ledger.async_get_identification(
            entry.entry_id
        ),
        save_identification=save_identification,
    )
    receiver = BlueFireReceiver(
        hass,
        entry.data["address"],
        bridge,
        health=health,
        j1587_extended=entry.data.get(CONF_J1587_EXTENDED),
        j1708_startup=entry.data.get(CONF_J1708_STARTUP, False),
    )
    entry.runtime_data = BlueFireRuntime(
        bridge, receiver=receiver, health=health
    )
    entry.runtime_data.services = receiver.services
    entry.async_on_unload(receiver.stop)
    entry.async_create_background_task(
        hass, receiver.async_run(), "BlueFire BLE receiver"
    )

    async def mqtt_ready() -> None:
        await async_flush_removals(hass, ledger)
        await bridge.async_disconnected(reset_receive=False)
        await bridge.async_rediscover()

    async def birth_received(message):
        if message.payload == settings.birth_payload:
            await bridge.async_rediscover()

    async def check_freshness(now):
        if mqtt.is_connected(hass):
            await bridge.async_check_stale()

    async def shutdown(event):
        receiver.stop()
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
            observed_at = datetime.now(timezone.utc) - timedelta(
                seconds=monotonic() - last.time
            )
            health.advertisement(last.rssi, last.source, observed_at)
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
        entry, [Platform.SENSOR, Platform.BINARY_SENSOR]
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Withdraw availability and unload diagnostic entities."""
    from homeassistant.components import mqtt
    from homeassistant.const import Platform

    if not await hass.config_entries.async_unload_platforms(
        entry, [Platform.SENSOR, Platform.BINARY_SENSOR]
    ):
        return False
    from homeassistant.exceptions import HomeAssistantError

    from .mqtt import async_get_ledger

    ledger = await async_get_ledger(hass)
    await ledger.async_queue_offline(entry.entry_id)
    try:
        if mqtt.is_connected(hass):
            await entry.runtime_data.bridge.async_disconnected()
            await ledger.async_clear_offline(entry.entry_id)
    except KeyError:
        # MQTT may have been unloaded before the BlueFire entry.
        pass
    except HomeAssistantError:
        # The durable offline marker will be published on the next reconnect.
        pass
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Queue retained discovery removal without relying on runtime_data."""
    from .mqtt import async_flush_removals, async_get_ledger

    ledger = await async_get_ledger(hass)
    await ledger.async_queue_removal(entry.entry_id)
    await async_flush_removals(hass, ledger)
