"""User-requested BLE inventory and notification capture.

Neither operation is a BlueFire protocol implementation. Captures only enable
notifications/indications; they never read values, authenticate, or write
BlueFire commands.
"""

import asyncio
from datetime import datetime, timezone
from time import monotonic

from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.exceptions import HomeAssistantError

from .capture import (
    analyze_notifications, record_capture, serialize_notifications,
)
from .const import MAX_CAPTURE_NOTIFICATIONS


async def async_inspect(hass, address: str) -> list[dict]:
    """Connect on request and list GATT metadata without reading values."""
    device = _device(hass, address)
    try:
        async with asyncio.timeout(30):
            client = await establish_connection(
                BleakClientWithServiceCache,
                device,
                "BlueFire inspection",
                ble_device_callback=lambda: (
                    bluetooth.async_ble_device_from_address(
                        hass, address, connectable=True
                    )
                ),
            )
            try:
                return _inventory(client)
            finally:
                await client.disconnect()
    except (BleakError, TimeoutError) as err:
        raise HomeAssistantError(
            "BLE inspection failed; ensure the adapter is powered "
            "and not used by another app"
        ) from err


def _inventory(client, *, handles: bool = False) -> list[dict]:
    result = []
    for service in client.services:
        characteristics = []
        for characteristic in service.characteristics:
            item = {
                "uuid": characteristic.uuid,
                "properties": list(characteristic.properties),
            }
            if handles:
                item["handle"] = getattr(characteristic, "handle", None)
            characteristics.append(item)
        result.append({
            "uuid": service.uuid, "characteristics": characteristics,
        })
    return result


def _device(hass, address):
    device = bluetooth.async_ble_device_from_address(
        hass, address, connectable=True
    )
    if device is None:
        raise HomeAssistantError(
            "Adapter is not visible to a connectable Home Assistant "
            "Bluetooth scanner"
        )
    return device


async def async_capture(hass, address: str, duration: float) -> dict:
    """Subscribe to every notify/indicate characteristic for duration.

    Returns bounded raw notifications with offsets in seconds from the
    connection. Subscription failures are reported, not fatal.
    """
    device = _device(hass, address)
    notifications: list[dict] = []
    dropped = 0
    received_notifications = 0
    received_bytes = 0
    last_received = None
    started = monotonic()
    subscribed = []
    failures = []

    def receiver(characteristic):
        def received(_sender, data) -> None:
            nonlocal dropped, received_notifications, received_bytes
            nonlocal last_received
            payload = bytes(data)
            received_notifications += 1
            received_bytes += len(payload)
            last_received = datetime.now(timezone.utc)
            if len(notifications) >= MAX_CAPTURE_NOTIFICATIONS:
                dropped += 1
                return
            notifications.append({
                "t": round(monotonic() - started, 4),
                "characteristic": characteristic.uuid,
                "handle": getattr(characteristic, "handle", None),
                "data": payload,
            })
        return received

    try:
        async with asyncio.timeout(duration + 45):
            connect_started = monotonic()
            client = await establish_connection(
                BleakClientWithServiceCache,
                device,
                "BlueFire diagnostics capture",
                ble_device_callback=lambda: (
                    bluetooth.async_ble_device_from_address(
                        hass, address, connectable=True
                    )
                ),
            )
            started = monotonic()
            connect_time = round(started - connect_started, 3)
            try:
                services = _inventory(client, handles=True)
                for service in client.services:
                    for characteristic in service.characteristics:
                        if not {"notify", "indicate"} & set(
                            characteristic.properties
                        ):
                            continue
                        identity = {
                            "service": service.uuid,
                            "characteristic": characteristic.uuid,
                            "handle": getattr(characteristic, "handle", None),
                        }
                        try:
                            await client.start_notify(
                                characteristic, receiver(characteristic)
                            )
                        except BleakError as err:
                            failures.append({**identity, "error": str(err)})
                        else:
                            subscribed.append((characteristic, identity))
                listening = round(monotonic() - started, 3)
                await asyncio.sleep(duration)
                elapsed = round(monotonic() - started, 3)
            finally:
                try:
                    for characteristic, _ in subscribed:
                        try:
                            await client.stop_notify(characteristic)
                        except BleakError:
                            pass
                    mtu = getattr(client, "mtu_size", None)
                finally:
                    await client.disconnect()
    except (BleakError, TimeoutError) as err:
        raise HomeAssistantError(
            f"BLE capture failed ({type(err).__name__}: {err}); ensure the "
            "adapter is powered and not used by another app"
        ) from err
    return {
        "requested_duration_s": duration,
        "elapsed_s": elapsed,
        "connect_time_s": connect_time,
        "subscriptions_ready_t": listening,
        "mtu": mtu,
        "services": services,
        "subscribed": [identity for _, identity in subscribed],
        "subscribe_failures": failures,
        "dropped_notifications": dropped,
        "notification_limit": MAX_CAPTURE_NOTIFICATIONS,
        "received_notifications": received_notifications,
        "received_bytes": received_bytes,
        "last_received": last_received,
        "notifications": notifications,
    }


def bluetooth_state(hass, address: str) -> dict:
    """HA's view of advertisements and scanners for the configured MAC."""
    result = {
        "address": address,
        "scanner_count": bluetooth.async_scanner_count(
            hass, connectable=False
        ),
        "connectable_scanner_count": bluetooth.async_scanner_count(
            hass, connectable=True
        ),
        "present": bluetooth.async_address_present(
            hass, address, connectable=False
        ),
        "connectable_present": bluetooth.async_address_present(
            hass, address, connectable=True
        ),
        "last_advertisement": None,
    }
    info = bluetooth.async_last_service_info(hass, address, connectable=False)
    if info is not None:
        result["last_advertisement"] = {
            "name": info.name,
            "rssi": info.rssi,
            "tx_power": getattr(info, "tx_power", None),
            "source": info.source,
            "connectable": info.connectable,
            "age_s": round(monotonic() - info.time, 1),
            "service_uuids": list(info.service_uuids),
            "manufacturer_data": {
                str(key): value.hex()
                for key, value in info.manufacturer_data.items()
            },
            "service_data": {
                key: value.hex() for key, value in info.service_data.items()
            },
        }
    return result


async def async_capture_report(
    hass, address: str, health, duration: float
) -> dict:
    """Capture, analyze and tally; failures are counted then re-raised."""
    before = bluetooth_state(hass, address)
    try:
        raw = await async_capture(hass, address, duration)
    except HomeAssistantError as err:
        health.error("connection_errors", str(err))
        raise
    notifications = raw.pop("notifications")
    last_received = raw.pop("last_received")
    analysis = analyze_notifications(notifications)
    record_capture(
        health, analysis,
        received_notifications=raw["received_notifications"],
        received_bytes=raw["received_bytes"],
        last_received=last_received,
    )
    return {
        "status": "completed",
        "bluetooth_before": before,
        "bluetooth_after": bluetooth_state(hass, address),
        **raw,
        "analysis": analysis,
        "notifications": serialize_notifications(notifications),
    }
