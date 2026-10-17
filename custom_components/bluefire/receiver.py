"""Provisional receive-only BlueFire EZ BLE receiver."""

from __future__ import annotations

import asyncio
import logging

from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)
from homeassistant.components import bluetooth
from homeassistant.exceptions import HomeAssistantError

from .protocol import (
    AdapterMessage,
    J1587Report,
    ObdReport,
    PgnReport,
    ProtocolError,
    ReceiveDecoder,
    parse_message,
)

_LOGGER = logging.getLogger(__name__)

EZ_SERVICE = "65333333-a115-11e2-9e9a-0800200ca100"
EZ_CLIENT_WRITE = "65333333-a115-11e2-9e9a-0800200ca101"
EZ_RECEIVE = "65333333-a115-11e2-9e9a-0800200ca102"
EZ_CHARACTERISTICS = {EZ_CLIENT_WRITE, EZ_RECEIVE}
RECONNECT_MIN = 2
RECONNECT_MAX = 60


class BlueFireReceiver:
    """Connect to the documented EZ service and route incoming reports."""

    def __init__(self, hass, address: str, bridge, *, j1587_extended=None):
        self.hass = hass
        self.address = address
        self.bridge = bridge
        self.j1587_extended = j1587_extended
        self._decoder = ReceiveDecoder()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
        self._overflow = asyncio.Event()
        self._closed = False

    async def async_run(self) -> None:
        """Keep a bounded-backoff receiver alive until config-entry unload."""
        delay = RECONNECT_MIN
        while not self._closed:
            try:
                await self._async_receive_session()
                delay = RECONNECT_MIN
            except asyncio.CancelledError:
                raise
            except (BleakError, HomeAssistantError, OSError, TimeoutError) as err:
                _LOGGER.warning("BlueFire BLE receiver unavailable: %s", err)
            except ProtocolError as err:
                _LOGGER.warning("BlueFire receive stream rejected: %s", err)
            finally:
                self._decoder.reset()
                try:
                    await self.bridge.async_disconnected()
                except Exception:  # MQTT can be down during BLE loss.
                    _LOGGER.debug(
                        "Unable to publish BlueFire offline state",
                        exc_info=True,
                    )
            if not self._closed:
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX)

    def stop(self) -> None:
        """Prevent a pending retry after unload."""
        self._closed = True

    async def _async_receive_session(self) -> None:
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise HomeAssistantError(
                "BlueFire adapter is not visible to a connectable Bluetooth scanner"
            )

        async with asyncio.timeout(30):
            client = await establish_connection(
                BleakClientWithServiceCache,
                device,
                "BlueFire receiver",
                ble_device_callback=lambda: (
                    bluetooth.async_ble_device_from_address(
                        self.hass, self.address, connectable=True
                    )
                ),
            )
            try:
                services = {
                    service.uuid.lower(): service
                    for service in client.services
                }
                service = services.get(EZ_SERVICE)
                if service is None:
                    raise HomeAssistantError(
                        "BlueFire EZ GATT service was not found"
                    )
                characteristics = {
                    item.uuid.lower(): item
                    for item in service.characteristics
                }
                notify_uuids = [
                    uuid for uuid in sorted(EZ_CHARACTERISTICS)
                    if uuid in characteristics
                    and "notify" in characteristics[uuid].properties
                ]
                if not notify_uuids:
                    raise HomeAssistantError(
                        "BlueFire EZ service has no supported notification characteristic"
                    )

                self._queue = asyncio.Queue(maxsize=128)
                self._overflow.clear()
                started = []
                for uuid in notify_uuids:
                    await client.start_notify(
                        characteristics[uuid], self._notification_received
                    )
                    started.append(characteristics[uuid])
                _LOGGER.info(
                    "BlueFire receiver subscribed to %d EZ characteristics",
                    len(notify_uuids),
                )
                while client.is_connected and not self._closed:
                    if self._overflow.is_set():
                        raise BleakError("BlueFire receive queue overflow")
                    get_chunk = asyncio.create_task(self._queue.get())
                    overflow = asyncio.create_task(self._overflow.wait())
                    try:
                        done, pending = await asyncio.wait(
                            (get_chunk, overflow),
                            timeout=1,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for task in pending:
                            task.cancel()
                        if pending:
                            await asyncio.gather(*pending, return_exceptions=True)
                        if not done:
                            continue
                        if overflow in done and overflow.result():
                            raise BleakError("BlueFire receive queue overflow")
                        chunk = get_chunk.result()
                    finally:
                        for task in (get_chunk, overflow):
                            if not task.done():
                                task.cancel()
                    for body in self._decoder.feed(chunk):
                        await self._async_process_body(body)
                raise BleakError("BlueFire Bluetooth connection lost")
            finally:
                for characteristic in reversed(locals().get("started", [])):
                    try:
                        await client.stop_notify(characteristic)
                    except (BleakError, OSError):
                        pass
                try:
                    await client.disconnect()
                except (BleakError, OSError):
                    _LOGGER.debug("BlueFire BLE disconnect failed", exc_info=True)

    def _notification_received(self, _characteristic, data: bytearray) -> None:
        """Queue callbacks from both EZ characteristics in arrival order."""
        try:
            self._queue.put_nowait(bytes(data))
        except asyncio.QueueFull:
            _LOGGER.warning("BlueFire receive queue overflow; reconnecting")
            self._overflow.set()

    async def _async_process_body(self, body: bytes) -> None:
        if body[0] == 154 and self.j1587_extended is None:
            _LOGGER.warning(
                "Ignoring J1587 PIDData until adapter firmware format is configured"
            )
            return
        message = parse_message(
            body, j1587_extended=self.j1587_extended
        )
        if isinstance(message, PgnReport):
            await self.bridge.async_process_pgn_report(message)
        elif isinstance(message, J1587Report):
            await self.bridge.async_process_j1587(message)
        elif isinstance(message, ObdReport):
            await self.bridge.async_process_obd_report(message)
        elif isinstance(message, AdapterMessage):
            if message.command != 255:
                _LOGGER.debug(
                    "Ignoring opaque BlueFire control command %d",
                    message.command,
                )
