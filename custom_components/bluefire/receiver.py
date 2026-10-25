"""BlueFire EZ receiver with opt-in unsecured J1708 startup."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
import logging
from time import monotonic

from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)
from homeassistant.components import bluetooth
from homeassistant.exceptions import HomeAssistantError

from .catalog import lookup
from .capture import analyze_notifications, serialize_notifications
from .const import MAX_CAPTURE_NOTIFICATIONS
from .protocol import (
    AdapterMessage,
    J1587Report,
    ObdReport,
    PgnReport,
    ProtocolError,
    ReceiveDecoder,
    parse_message,
)
from .startup import J1708Startup, StartupError

_LOGGER = logging.getLogger(__name__)


class _ReceiverPaused(Exception):
    """Signal a diagnostic capture to take exclusive BLE ownership."""


EZ_SERVICE = "65333333-a115-11e2-9e9a-0800200ca100"
EZ_CLIENT_WRITE = "65333333-a115-11e2-9e9a-0800200ca101"
EZ_RECEIVE = "65333333-a115-11e2-9e9a-0800200ca102"
EZ_CHARACTERISTICS = {EZ_CLIENT_WRITE, EZ_RECEIVE}
RECONNECT_MIN = 2
RECONNECT_MAX = 60
CONNECTION_TIMEOUT = 30
BLE_OPERATION_TIMEOUT = 10
BLE_CLEANUP_TIMEOUT = 5
SESSION_CLOSE_TIMEOUT = 20


class BlueFireReceiver:
    """Connect to the documented EZ service and route incoming reports."""

    def __init__(
        self, hass, address: str, bridge, *, health=None,
        j1587_extended=None, j1708_startup: bool = False,
    ):
        self.hass = hass
        self.address = address
        self.bridge = bridge
        self.health = health
        self.j1587_extended = j1587_extended
        self.j1708_startup = j1708_startup
        self._startup: J1708Startup | None = None
        self._decoder = ReceiveDecoder()
        self._control_decoder = ReceiveDecoder()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
        self._overflow = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._session_closed = asyncio.Event()
        self._session_closed.set()
        self._paused = False
        self._closed = False
        self._session_task: asyncio.Task | None = None
        self._connected = False
        self._session_healthy = False
        self._session_ended = asyncio.Event()
        self._session_ended.set()
        self._capture_callback: (
            Callable[[object, bytes | bytearray], None] | None
        ) = None
        self._reconnect_delay = 0
        self._connection_events: deque[dict] = deque(maxlen=20)
        self._last_notification: str | None = None
        self.services: list[dict] = []

    def connection_diagnostics(self) -> dict:
        """Expose bounded connection history alongside startup errors."""
        return {
            "connected": self._connected,
            "retry_delay_s": self._reconnect_delay,
            "last_notification": self._last_notification,
            "events": list(self._connection_events),
        }

    def _connection_event(self, event: str, reason: str | None = None) -> None:
        self._connection_events.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "reason": reason,
        })

    async def async_capture(self, duration: float) -> dict:
        """Observe one live session without disconnecting or extra writes."""
        if not self._connected:
            return {
                "status": "skipped", "mode": "live",
                "reason": "No subscribed live BLE session; retries continue",
            }
        if self._capture_callback is not None:
            raise HomeAssistantError("A live capture is already running")
        notifications: list[dict] = []
        received = 0
        received_bytes = 0
        started = monotonic()
        ended = self._session_ended

        def capture(characteristic, data):
            nonlocal received, received_bytes
            received += 1
            received_bytes += len(data)
            if len(notifications) < MAX_CAPTURE_NOTIFICATIONS:
                notifications.append({
                    "t": round(monotonic() - started, 4),
                    "characteristic": getattr(characteristic, "uuid", ""),
                    "handle": getattr(characteristic, "handle", None),
                    "data": bytes(data),
                })

        self._capture_callback = capture
        try:
            try:
                async with asyncio.timeout(duration):
                    await ended.wait()
            except TimeoutError:
                pass
        finally:
            self._capture_callback = None
        analysis = analyze_notifications(notifications)
        selected = analysis["selected_framing"]
        if self.health is not None:
            # Live processing owns counters; do not add capture totals twice.
            self.health.capture_completed({
                "selected_framing": selected, **analysis["timing"],
                **analysis["totals"][selected],
            })
        return {
            "status": "completed", "mode": "live",
            "requested_duration_s": duration,
            "elapsed_s": round(monotonic() - started, 3),
            "connection_lost": ended.is_set(),
            "notification_limit": MAX_CAPTURE_NOTIFICATIONS,
            "received_notifications": received,
            "received_bytes": received_bytes,
            "dropped_notifications": received - len(notifications),
            "analysis": analysis,
            "notifications": serialize_notifications(notifications),
        }

    def startup_diagnostics(self) -> dict:
        """Expose startup progress without security data or raw payloads."""
        if self._startup is not None:
            return self._startup.diagnostics()
        return {
            "stage": "not_started" if self.j1708_startup else "disabled",
        }

    async def async_run(self) -> None:
        """Keep a bounded-backoff receiver alive until config-entry unload."""
        delay = RECONNECT_MIN
        while not self._closed:
            if self._paused:
                await self._resume_event.wait()
                if self._closed:
                    break
            self._session_closed.clear()
            self._session_healthy = False
            self._reconnect_delay = 0
            self._connection_event("connecting")
            session_task = asyncio.create_task(
                self._async_receive_session(), name="BlueFire BLE session"
            )
            self._session_task = session_task
            paused_session = False
            end_reason = "Receiver stopped"
            try:
                await session_task
                delay = RECONNECT_MIN
            except asyncio.CancelledError:
                current_task = asyncio.current_task()
                if current_task is not None and current_task.cancelling():
                    raise
                if not (self._paused or self._closed):
                    raise
                paused_session = self._paused and not self._closed
            except _ReceiverPaused:
                paused_session = True
            except (
                BleakError, HomeAssistantError, OSError, TimeoutError
            ) as err:
                end_reason = str(err)
                self._health_error("connection_errors", str(err))
                _LOGGER.warning("BlueFire BLE receiver unavailable: %s", err)
            except ProtocolError as err:
                end_reason = str(err)
                self._health_error("framing_errors", str(err))
                _LOGGER.warning("BlueFire receive stream rejected: %s", err)
            except Exception:
                end_reason = "Unexpected receiver session failure"
                _LOGGER.exception("BlueFire receiver session failed")
            finally:
                self._connection_event(
                    "paused" if paused_session else "disconnected", end_reason
                )
                self._session_task = None
                self._session_closed.set()
                self._decoder.reset()
                self._control_decoder.reset()
                if not paused_session:
                    try:
                        await self.bridge.async_disconnected()
                    except Exception:  # MQTT can be down during BLE loss.
                        _LOGGER.debug(
                            "Unable to publish BlueFire offline state",
                            exc_info=True,
                        )
            if not self._closed and not self._paused:
                if self._session_healthy:
                    delay = RECONNECT_MIN
                self._reconnect_delay = delay
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX)

    def stop(self) -> None:
        """Stop retries and interrupt an active BLE session."""
        self._closed = True
        self._resume_event.set()
        if self._session_task is not None:
            self._session_task.cancel()

    async def async_pause(self) -> None:
        """Yield the BLE connection to a user-requested diagnostic capture."""
        self._paused = True
        self._resume_event.clear()
        self._pause_event.set()
        if self._session_task is not None:
            self._session_task.cancel()
        try:
            async with asyncio.timeout(SESSION_CLOSE_TIMEOUT):
                await self._session_closed.wait()
        except TimeoutError as err:
            raise HomeAssistantError(
                "BlueFire receiver did not release its BLE connection"
            ) from err

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

        async with asyncio.timeout(CONNECTION_TIMEOUT):
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
        started = []
        startup_task: asyncio.Task | None = None
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
                and {"notify", "indicate"} & set(
                    characteristics[uuid].properties
                )
            ]
            if not notify_uuids:
                raise HomeAssistantError(
                    "BlueFire EZ service has no supported "
                    "notification characteristic"
                )
            if self.j1708_startup:
                write_characteristic = characteristics.get(EZ_CLIENT_WRITE)
                if (
                    write_characteristic is None
                    or "write" not in write_characteristic.properties
                    or set(notify_uuids) != EZ_CHARACTERISTICS
                ):
                    raise HomeAssistantError(
                        "J1708 startup requires both EZ subscriptions "
                        "and the client write-with-response characteristic"
                    )
                if type(self.j1587_extended) is not bool:
                    raise HomeAssistantError(
                        "Select a J1587 firmware format before J1708 startup"
                    )

                async def write(packet: bytes) -> None:
                    async with asyncio.timeout(BLE_OPERATION_TIMEOUT):
                        await client.write_gatt_char(
                            write_characteristic, packet, response=True
                        )

                self._startup = J1708Startup(
                    write, getattr(device, "name", None),
                    self.j1587_extended,
                )

            self._queue = asyncio.Queue(maxsize=128)
            self._overflow.clear()
            self._pause_event.clear()
            for uuid in notify_uuids:
                async with asyncio.timeout(BLE_OPERATION_TIMEOUT):
                    await client.start_notify(
                        characteristics[uuid], self._notification_received
                    )
                    started.append(characteristics[uuid])
            _LOGGER.info(
                "BlueFire receiver subscribed to %d EZ characteristics",
                len(notify_uuids),
            )
            self._connected = True
            self._session_ended = asyncio.Event()
            self._connection_event("connected")

            async def maintain_session(startup: J1708Startup) -> None:
                await startup.run()
                self._session_healthy = True
                self._connection_event("startup_ready")
                _LOGGER.info(
                    "BlueFire J1708 startup complete; "
                    "starting read-only probes"
                )
                await startup.keepalive()

            if self._startup is not None and self.j1708_startup:
                startup_task = asyncio.create_task(
                    maintain_session(self._startup),
                    name="BlueFire J1708 session control",
                )
            while client.is_connected and not self._closed:
                if startup_task is not None and startup_task.done():
                    startup_task.result()
                    startup_task = None
                if self._overflow.is_set():
                    raise BleakError("BlueFire receive queue overflow")
                get_chunk = asyncio.create_task(self._queue.get())
                overflow = asyncio.create_task(self._overflow.wait())
                paused = asyncio.create_task(self._pause_event.wait())
                try:
                    waiting = {get_chunk, overflow, paused}
                    if startup_task is not None and not startup_task.done():
                        waiting.add(startup_task)
                    done, pending = await asyncio.wait(
                        waiting,
                        timeout=1,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    pending.discard(startup_task)
                    for task in pending:
                        task.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    if not done:
                        continue
                    if overflow in done and overflow.result():
                        raise BleakError("BlueFire receive queue overflow")
                finally:
                    for task in (get_chunk, overflow, paused):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(
                        get_chunk, overflow, paused, return_exceptions=True
                    )
                if paused in done and paused.result():
                    if get_chunk not in done:
                        raise _ReceiverPaused
                if get_chunk not in done:
                    continue
                chunk = get_chunk.result()
                bodies = self._decoder.feed(chunk)
                for body in bodies:
                    try:
                        await self._async_process_body(body)
                    except ProtocolError:
                        continue
                if paused in done and paused.result():
                    raise _ReceiverPaused
            raise BleakError("BlueFire Bluetooth connection lost")
        except (StartupError, BleakError, OSError, TimeoutError) as err:
            if self._startup is not None and (
                isinstance(err, StartupError) or not self._startup.ready
                or startup_task is not None and startup_task.done()
            ):
                self._startup.error = str(err)
                self._startup.stage = "failed"
            if isinstance(err, StartupError):
                raise HomeAssistantError(
                    f"J1708 session failed: {err}"
                ) from err
            raise
        finally:
            self._connected = False
            self._session_ended.set()
            if startup_task is not None:
                startup_task.cancel()
                await asyncio.gather(startup_task, return_exceptions=True)
            if self._startup is not None:
                self._startup.disconnected()
            self._decoder.reset()
            self._control_decoder.reset()
            for characteristic in reversed(started):
                try:
                    async with asyncio.timeout(BLE_CLEANUP_TIMEOUT):
                        await client.stop_notify(characteristic)
                except (BleakError, OSError, TimeoutError):
                    _LOGGER.debug(
                        "Unable to stop BlueFire BLE notification",
                        exc_info=True,
                    )
            try:
                async with asyncio.timeout(BLE_CLEANUP_TIMEOUT):
                    await client.disconnect()
            except (BleakError, OSError, TimeoutError):
                _LOGGER.debug(
                    "BlueFire BLE disconnect failed", exc_info=True
                )

    def _notification_received(self, _characteristic, data: bytearray) -> None:
        """Queue callbacks from both EZ characteristics in arrival order."""
        self._last_notification = datetime.now(timezone.utc).isoformat()
        if self._capture_callback is not None:
            self._capture_callback(_characteristic, data)
        if self.health is not None:
            self.health.count("notifications")
            self.health.count("bytes", len(data))
        try:
            self._queue.put_nowait(bytes(data))
        except asyncio.QueueFull:
            _LOGGER.warning("BlueFire receive queue overflow; reconnecting")
            self._overflow.set()
        try:
            bodies = self._control_decoder.feed(bytes(data))
        except ProtocolError:
            # The queued live consumer records/rejects this same framing error.
            return
        if self._startup is not None and self._startup.ready:
            for body in bodies:
                if body[0] == 7:
                    # Resolve probes even while MQTT publication awaits IO.
                    self._startup.receive(AdapterMessage(7, body[1:]))

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
        if self._startup is not None:
            if isinstance(message, AdapterMessage):
                if self._startup.ready and message.command == 7:
                    # Already dispatched; never replay an old ACK.
                    handled = True
                else:
                    handled = self._startup.receive(message)
                if handled and message.command != 255:
                    await asyncio.sleep(0)
                    return
            elif not self._startup.ready:
                self._startup.discarded_reports += 1
                return
        if isinstance(message, PgnReport):
            self._session_healthy = True
            if self.health is not None:
                self.health.count("pgn_reports")
                if not lookup("pgn", message.pgn)["known"]:
                    self.health.count("unrecognized_pgns")
                self.health.data_seen()
            await self.bridge.async_process_pgn_report(message)
        elif isinstance(message, J1587Report):
            self._session_healthy = True
            if self.health is not None:
                self.health.count("j1587_reports")
                self.health.data_seen()
            await self.bridge.async_process_j1587(message)
        elif isinstance(message, ObdReport):
            self._session_healthy = True
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
