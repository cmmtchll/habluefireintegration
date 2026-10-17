"""HA MQTT settings and durable discovery ownership (never live readings)."""

import asyncio
from dataclasses import dataclass
import logging
from uuid import uuid4

from .const import DOMAIN
from .telemetry import (
    MqttBridge, valid_vehicle_id, validated_j1587_ids, validated_signal_ids,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MqttSettings:
    """Only non-secret discovery settings from HA's MQTT config entry."""

    discovery_prefix: str = "homeassistant"
    birth_topic: str | None = "homeassistant/status"
    birth_payload: str = "online"


def mqtt_settings(hass) -> MqttSettings:
    """Isolate the version-sensitive lookup of MQTT entry options/defaults."""
    entries = hass.config_entries.async_entries("mqtt")
    if not entries:
        return MqttSettings()
    config = entries[0].data | entries[0].options
    birth = config.get("birth_message", {
        "topic": "homeassistant/status", "payload": "online",
    })
    return MqttSettings(
        discovery_prefix=config.get("discovery_prefix", "homeassistant"),
        birth_topic=birth.get("topic"),
        birth_payload=birth.get("payload", "online"),
    )


class DiscoveryLedger:
    """Keep ownership across unload, restart, and offline entry removal."""

    def __init__(self, store):
        self.store = store
        self._records = {}
        self._loaded = False
        self._lock = asyncio.Lock()

    async def _async_load(self):
        """Load validated identities, never stored MQTT payloads."""
        if self._loaded:
            return
        records = await self.store.async_load() or {}
        if not isinstance(records, dict):
            records = {}
        for key, record in records.items():
            if not isinstance(record, dict):
                continue
            vehicle = record.get("vehicle_id", "")
            prefix = record.get("discovery_prefix", "")
            if (
                not isinstance(vehicle, str) or not valid_vehicle_id(vehicle)
                or not isinstance(prefix, str) or not prefix
                or any(character in prefix for character in ("+", "#", "\0"))
            ):
                continue
            signals = validated_signal_ids(record.get("signals", []))
            self._records[key] = {
                "vehicle_id": vehicle,
                "discovery_prefix": prefix,
                "signals": signals,
                "j1587_signals": validated_j1587_ids(
                    record.get("j1587_signals", [])
                ),
                "pending": record.get("pending", False),
            }
        self._loaded = True

    async def async_prepare(self, entry_id, vehicle_id, prefix):
        """Restore ownership; queue old-prefix definitions for withdrawal."""
        async with self._lock:
            await self._async_load()
            old = self._records.get(entry_id)
            signals = old["signals"] if old else []
            if old and (
                old["vehicle_id"] != vehicle_id
                or old["discovery_prefix"] != prefix
            ):
                self._records[uuid4().hex] = {**old, "pending": True}
            self._records[entry_id] = {
                "vehicle_id": vehicle_id,
                "discovery_prefix": prefix,
                "signals": signals,
                "j1587_signals": old["j1587_signals"] if old else [],
                "pending": False,
            }
            await self.store.async_save(self._records)
            return self._records[entry_id]["signals"]

    async def async_get_j1587(self, entry_id):
        """Restore MID/PID ownership separately from legacy SPN metadata."""
        async with self._lock:
            await self._async_load()
            return self._records[entry_id]["j1587_signals"]

    async def async_save_signals(self, entry_id, signals, *, j1587=False):
        """Write before publishing any new retained discovery definition."""
        async with self._lock:
            await self._async_load()
            key = "j1587_signals" if j1587 else "signals"
            self._records[entry_id][key] = signals
            await self.store.async_save(self._records)

    def diagnostics(self, entry_id) -> dict:
        """Loaded ownership for one entry plus queued cleanup totals."""
        return {
            "record": self._records.get(entry_id),
            "pending_removals": sum(
                1 for record in self._records.values() if record["pending"]
            ),
        }

    async def async_queue_removal(self, entry_id):
        """Deletion must work even when entry.runtime_data no longer exists."""
        async with self._lock:
            await self._async_load()
            if entry_id in self._records:
                self._records[entry_id]["pending"] = True
                await self.store.async_save(self._records)

    async def async_flush_removals(self, publish):
        """Clear broker-retained definitions; retain failed work for retry."""
        async with self._lock:
            await self._async_load()
            for entry_id, record in tuple(self._records.items()):
                if not record["pending"]:
                    continue
                bridge = MqttBridge(
                    record["vehicle_id"],
                    publish,
                    discovery_prefix=record["discovery_prefix"],
                    known_signals=record["signals"],
                    known_j1587=record["j1587_signals"],
                )
                await bridge.async_remove_discovery()
                # A prefix change may leave an active entry on the same state
                # topics. Its current lifecycle publishes availability.
                if not any(
                    not other["pending"]
                    and other["vehicle_id"] == record["vehicle_id"]
                    for other in self._records.values()
                ):
                    await publish(bridge.availability_topic, "", True)
                    await publish(bridge.j1587.availability_topic, "", True)
                del self._records[entry_id]
                await self.store.async_save(self._records)


async def async_get_ledger(hass) -> DiscoveryLedger:
    """Keep pending cleanup alive even after the last entry unloads."""
    from homeassistant.components import mqtt
    from homeassistant.core import callback
    from homeassistant.helpers.storage import Store

    if DOMAIN not in hass.data:
        ledger = DiscoveryLedger(Store(hass, 1, f"{DOMAIN}.mqtt_discovery"))
        hass.data[DOMAIN] = ledger

        @callback
        def connected(online):
            if online:
                hass.async_create_task(
                    async_flush_removals(hass, ledger),
                    "BlueFire pending MQTT discovery cleanup",
                )

        mqtt.async_subscribe_connection_status(hass, connected)
    return hass.data[DOMAIN]


async def async_publish(hass, topic, payload, retain):
    """Use HA's shared client; deliver retained lifecycle messages at QoS 1."""
    from homeassistant.components import mqtt

    await mqtt.async_publish(
        hass, topic, payload, qos=1 if retain else 0, retain=retain
    )


async def async_confirm_removal(hass, topic):
    """Confirm broker receipt, not just queuing on HA's shared MQTT client."""
    from homeassistant.components import mqtt
    from homeassistant.core import callback

    confirmed = asyncio.get_running_loop().create_future()

    @callback
    def received(message):
        if message.payload == "" and not confirmed.done():
            confirmed.set_result(None)

    unsubscribe = None
    try:
        async with asyncio.timeout(15):
            # Empty retained payloads have no cached broker value. Seeing our
            # deletion echoed to this subscription confirms broker processing.
            unsubscribe = await mqtt.async_subscribe(
                hass, topic, received, qos=1
            )
            await async_publish(hass, topic, "", True)
            await confirmed
    finally:
        if unsubscribe is not None:
            unsubscribe()


async def async_flush_removals(hass, ledger):
    """Flush only while connected; offline tombstones remain on disk."""
    from homeassistant.components import mqtt
    from homeassistant.exceptions import HomeAssistantError

    try:
        connected = mqtt.is_connected(hass)
    except KeyError:
        # Removal also runs for disabled/failed entries with no MQTT client.
        connected = False
    if connected:
        async def publish(topic, payload, retain):
            if payload == "" and retain:
                await async_confirm_removal(hass, topic)
            else:
                await async_publish(hass, topic, payload, retain)

        try:
            await ledger.async_flush_removals(publish)
        except (TimeoutError, HomeAssistantError):
            _LOGGER.warning(
                "MQTT discovery removal was not confirmed; "
                "cleanup remains queued for reconnect"
            )
