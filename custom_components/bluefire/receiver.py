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

from .catalog import lookup
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


class _ReceiverPaused(Exception):
    """Signal a diagnostic capture to take exclusive BLE ownership."""


EZ_SERVICE = "65333333-a115-11e2-9e9a-0800200ca100"
EZ_CLIENT_WRITE = "65333333-a115-11e2-9e9a-0800200ca101"
EZ_RECEIVE = "65333333-a115-11e2-9e9a-0800200ca102"
EZ_CHARACTERISTICS = {EZ_CLIENT_WRITE, EZ_RECEIVE}
RECONNECT_MIN = 2
RECONNECT_MAX = 60


class BlueFireReceiver:
    """Connect to the documented EZ service and route incoming reports."""

    def __init__(
        self, hass, address: str, bridge, *, health=None,
        j1587_extended=None,
    ):
        self.hass = hass
        self.address = address
        self.bridge = bridge
        self.health = health
        self.j1587_extended = j1587_extended
        self._decoder = ReceiveDecoder()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
        self._overflow = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._session_closed = asyncio.Event()
        self._session_closed.set()
        self._paused = False
        self._closed = False
        self.services: list[dict] = []

    async def async_run(self) -> None:
        """Keep a bounded-backoff receiver alive until config-entry unload."""
        delay = RECONNECT_MIN
        while not self._closed:
            if self._paused:
                await self._resume_event.wait()
                if self._closed:
                    break
            self._session_closed.clear()
            paused_session = False
            try:
                await self._async_receive_session()
                delay = RECONNECT_MIN
            except asyncio.CancelledError:
                raise
            except _ReceiverPaused:
                paused_session = True
            except (
                BleakError, HomeAssistantError, OSError, TimeoutError
            ) as err:
                self._health_error("connection_errors", str(err))
                _LOGGER.warning("BlueFire BLE receiver unavailable: %s", err)
            except ProtocolError as err:
                self._health_error("framing_errors", str(err))
                _LOGGER.warning("BlueFire receive stream rejected: %s", err)
            except Exception:
                _LOGGER.exception("BlueFire receiver session failed")
            finally:
                self._session_closed.set()
                self._decoder.reset()
                if not paused_session:
                    try:
                        await self.bridge.async_disconnected()
                    except Exception:  # MQTT can be down during BLE loss.
                        _LOGGER.debug(
                            "Unable to publish BlueFire offline state",
                            exc_info=True,
                        )
            if not self._closed and not self._paused:
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX)

    def stop(self) -> None:
        """Prevent a pending retry after unload."""
        self._closed = True
        self._resume_event.set()

    async def async_pause(self) -> None:
        """Yield the BLE connection to a user-requested diagnostic capture."""
        self._paused = True
        self._resume_event.clear()
        self._pause_event.set()
        await self._session_closed.wait()

    def async_resume(self) -> None:
        """Restart live reception after a diagnostic capture completes."""
        self._paused = False
        self._pause_event.clear()
        self._resume_event.set()

    async def _async_receive_session(self) -> None:
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise HomeAssistantError(
                "BlueFire adapter is not visible to a connectable "
                "Bluetooth scanner"
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
                if self._paused:
                    raise _ReceiverPaused
                services = {
                    service.uuid.lower(): service
                    for service in client.services
                }
                self.services[:] = [
                    {
                        "uuid": service.uuid,
                        "characteristics": [
                            {
                                "uuid": characteristic.uuid,
                                "properties": list(characteristic.properties),
                            }
                            for characteristic in service.characteristics
                        ],
                    }
                    for service in client.services
                ]
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
                        "BlueFire EZ service has no supported "
                        "notification characteristic"
                    )

                self._queue = asyncio.Queue(maxsize=128)
                self._overflow.clear()
                self._pause_event.clear()
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
                    paused = asyncio.create_task(self._pause_event.wait())
                    try:
                        done, pending = await asyncio.wait(
                            (get_chunk, overflow, paused),
                            timeout=1,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for task in pending:
                            task.cancel()
                        if pending:
                            await asyncio.gather(
                                *pending, return_exceptions=True
                            )
                        if not done:
                            continue
                        if overflow in done and overflow.result():
                            raise BleakError("BlueFire receive queue overflow")
                    finally:
                        for task in (get_chunk, overflow, paused):
                            if not task.done():
                                task.cancel()
                        await asyncio.gather(
                            get_chunk, overflow, paused,
                            return_exceptions=True,
                        )
                    if paused in done and paused.result():
                        if get_chunk not in done:
                            raise _ReceiverPaused
                    if get_chunk not in done:
                        continue
                    chunk = get_chunk.result()
                    try:
                        bodies = self._decoder.feed(chunk)
                    except ProtocolError as err:
                        self._health_error("framing_errors", str(err))
                        raise
                    for body in bodies:
                        try:
                            await self._async_process_body(body)
                        except ProtocolError:
                            continue
                    if paused in done and paused.result():
                        raise _ReceiverPaused
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
                    _LOGGER.debug(
                        "BlueFire BLE disconnect failed",
                        exc_info=True,
                    )

    def _notification_received(self, _characteristic, data: bytearray) -> None:
        """Queue callbacks from both EZ characteristics in arrival order."""
        if self.health is not None:
            self.health.count("notifications")
            self.health.count("bytes", len(data))
        try:
            self._queue.put_nowait(bytes(data))
        except asyncio.QueueFull:
            _LOGGER.warning("BlueFire receive queue overflow; reconnecting")
            self._overflow.set()

    async def _async_process_body(self, body: bytes) -> None:
        try:
            message = parse_message(
                body, j1587_extended=self.j1587_extended
            )
        except ProtocolError as err:
            self._health_error("parse_errors", str(err))
            raise
        if self.health is not None:
            self.health.count("packets")
        if isinstance(message, PgnReport):
            if self.health is not None:
                self.health.count("pgn_reports")
                if not lookup("pgn", message.pgn)["known"]:
                    self.health.count("unrecognized_pgns")
                self.health.data_seen()
            await self.bridge.async_process_pgn_report(message)
        elif isinstance(message, J1587Report):
            if self.health is not None:
                self.health.count("j1587_reports")
                self.health.data_seen()
            await self.bridge.async_process_j1587(message)
        elif isinstance(message, ObdReport):
            if self.health is not None:
                self.health.count("obd_reports")
                self.health.data_seen()
            await self.bridge.async_process_obd_report(message)
        elif isinstance(message, AdapterMessage):
            if message.command == 255:
                if self.health is not None:
                    self.health.count("heartbeats")
            elif self.health is not None and not lookup(
                "command", message.command
            )["known"]:
                self.health.count("unknown_commands")
                _LOGGER.debug(
                    "Ignoring unknown BlueFire control command %d",
                    message.command,
                )

    def _health_error(self, counter: str, message: str) -> None:
        if self.health is not None:
            self.health.error(counter, message)
