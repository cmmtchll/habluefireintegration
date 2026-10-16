"""Read-only BLE service inventory, not a BlueFire protocol implementation."""

import asyncio

from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)
from homeassistant.components import bluetooth
from homeassistant.exceptions import HomeAssistantError


async def async_inspect(hass, address: str) -> list[dict]:
    """Connect on request and list GATT metadata without reading values."""
    device = bluetooth.async_ble_device_from_address(
        hass, address, connectable=True)
    if device is None:
        raise HomeAssistantError(
            "Adapter is not visible to a connectable Home Assistant "
            "Bluetooth scanner"
        )
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
                return [
                    {
                        "uuid": service.uuid,
                        "characteristics": [
                            {"uuid": characteristic.uuid, "properties": list(
                                characteristic.properties)}
                            for characteristic in service.characteristics
                        ],
                    }
                    for service in client.services
                ]
            finally:
                await client.disconnect()
    except (BleakError, TimeoutError) as err:
        raise HomeAssistantError(
            "BLE inspection failed; ensure the adapter is powered "
            "and not used by another app"
        ) from err
