"""BlueFire EZ receiver with opt-in J1708 startup and minute polling."""

from __future__ import annotations

import asyncio
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
from .const import (
    J1708_POLL_INTERVAL, J1708_POLL_MAX_BACKOFF, J1708_READ_ACTIONS,
)
from .j1587 import decode_report
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
READ_WINDOW_SECONDS = 5


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
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
        self._overflow = asyncio.Event()
        self._reconnect_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._session_closed = asyncio.Event()
        self._session_closed.set()
        self._paused = False
        self._closed = False
        self._session_task: asyncio.Task | None = None
        self._read_waiter: asyncio.Future[None] | None = None
        self._read_pid: int | None = None
        self._read_reports: dict[int, dict] = {}
        self.services: list[dict] = []

    async def async_read(self, pid: int) -> dict:
        """Collect fresh reports during a bounded, explicit J1708 request."""
        startup = self._startup
        if (
            not self.j1708_startup or startup is None or not startup.ready
            or self._closed or self._paused or self._overflow.is_set()
            or self._reconnect_event.is_set()
        ):
            raise HomeAssistantError(
                "Enable J1708 startup and wait for a ready BLE connection"
            )
        if type(pid) is not int or pid not in J1708_READ_ACTIONS.values():
            raise HomeAssistantError(
                "Only supported J1708 sensor reads are allowed"
            )
        if self._read_waiter is not None:
            raise HomeAssistantError("A J1708 read is already running")
        waiter: asyncio.Future[None] = (
            asyncio.get_running_loop().create_future()
        )
        self._read_waiter = waiter
        self._read_pid = pid
        self._read_reports = {}
        try:
            await startup.async_read(pid)
            try:
                async with asyncio.timeout(READ_WINDOW_SECONDS):
                    await asyncio.shield(waiter)
            except TimeoutError:
                if not self._read_reports:
                    raise HomeAssistantError(
                        f"No J1708 PID {pid} report received "
                        "during read window"
                    ) from None
            return {
                "pid": pid,
                "reports": [
                    {"mid": mid, **report}
                    for mid, report in sorted(self._read_reports.items())
                ],
            }
        except (StartupError, BleakError, OSError, TimeoutError) as err:
            raise HomeAssistantError(f"J1708 read failed: {err}") from err
        finally:
            waiter.cancel()
            if waiter.done() and not waiter.cancelled():
                waiter.exception()
            try:
                if startup.ready and not self._closed and not self._paused:
                    await startup.async_read(pid, restore=True)
            except (StartupError, BleakError, OSError, TimeoutError) as err:
                self._health_error("connection_errors", str(err))
                self._reconnect_event.set()
                raise HomeAssistantError(
                    f"Unable to restore passive J1708 monitoring: {err}"
                ) from err
            finally:
                self._read_waiter = None
                self._read_pid = None
                self._read_reports = {}

    def startup_diagnostics(self) -> dict:
        """Expose startup progress without security data or raw payloads."""
        if self._startup is not None:
            return self._startup.diagnostics()
        return {
            "stage": "not_started" if self.j1708_startup else "disabled",
        }

    async def _async_poll(self) -> None:
        """Poll each minute, backing off each silent PID independently."""
        next_poll = monotonic() + J1708_POLL_INTERVAL
        retry_at = {pid: next_poll for pid in J1708_READ_ACTIONS.values()}
        backoff = {pid: J1708_POLL_INTERVAL for pid in retry_at}
        while True:
            await asyncio.sleep(max(0, next_poll - monotonic()))
            now = monotonic()
            next_poll = now + J1708_POLL_INTERVAL
            for pid in retry_at:
                if self._closed or self._paused or (
                    self._startup is None or not self._startup.ready
                    or self._reconnect_event.is_set()
                ):
                    return
                if self._read_waiter is not None or now < retry_at[pid]:
                    continue
                try:
                    await self.async_read(pid)
                except HomeAssistantError as err:
                    backoff[pid] = min(
                        backoff[pid] * 2, J1708_POLL_MAX_BACKOFF
                    )
                    self._health_error("connection_errors", str(err))
                    _LOGGER.warning(
                        "BlueFire periodic PID %d read failed; "
                        "retrying in %d seconds: %s",
                        pid, backoff[pid], err,
                    )
                else:
                    backoff[pid] = J1708_POLL_INTERVAL
                retry_at[pid] = now + backoff[pid]
            finished = monotonic()
            if finished >= next_poll:
                next_poll = finished + J1708_POLL_INTERVAL

    async def async_run(self) -> None:
        """Keep a bounded-backoff receiver alive until config-entry unload."""
        delay = RECONNECT_MIN
        while not self._closed:
            if self._paused:
                await self._resume_event.wait()
                if self._closed:
                    break
            self._session_closed.clear()
            session_task = asyncio.create_task(
                self._async_receive_session(), name="BlueFire BLE session"
            )
            self._session_task = session_task
            paused_session = False
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
                self._health_error("connection_errors", str(err))
                _LOGGER.warning("BlueFire BLE receiver unavailable: %s", err)
            except ProtocolError as err:
                self._health_error("framing_errors", str(err))
                _LOGGER.warning("BlueFire receive stream rejected: %s", err)
            except Exception:
                _LOGGER.exception("BlueFire receiver session failed")
            finally:
                self._session_task = None
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
        poll_task: asyncio.Task | None = None
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
            self._reconnect_event.clear()
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
            if self._startup is not None and self.j1708_startup:
                startup_task = asyncio.create_task(
                    self._startup.run(), name="BlueFire J1708 startup"
                )
            while client.is_connected and not self._closed:
                if startup_task is not None and startup_task.done():
                    startup_task.result()
                    startup_task = None
                    _LOGGER.info(
                        "BlueFire J1708 startup complete; waiting for reports"
                    )
                    poll_task = asyncio.create_task(
                        self._async_poll(), name="BlueFire J1708 polling"
                    )
                if poll_task is not None and poll_task.done():
                    poll_task.result()
                    raise BleakError("BlueFire J1708 polling stopped")
                if self._overflow.is_set():
                    raise BleakError("BlueFire receive queue overflow")
                if self._reconnect_event.is_set():
                    raise BleakError("Passive J1708 monitoring restore failed")
                get_chunk = asyncio.create_task(self._queue.get())
                overflow = asyncio.create_task(self._overflow.wait())
                paused = asyncio.create_task(self._pause_event.wait())
                reconnect = asyncio.create_task(self._reconnect_event.wait())
                try:
                    waiting = {get_chunk, overflow, paused, reconnect}
                    if startup_task is not None and not startup_task.done():
                        waiting.add(startup_task)
                    if poll_task is not None:
                        waiting.add(poll_task)
                    done, pending = await asyncio.wait(
                        waiting,
                        timeout=1,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    pending.discard(startup_task)
                    pending.discard(poll_task)
                    for task in pending:
                        task.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    if not done:
                        continue
                    if overflow in done and overflow.result():
                        raise BleakError("BlueFire receive queue overflow")
                    if reconnect in done and reconnect.result():
                        raise BleakError(
                            "Passive J1708 monitoring restore failed"
                        )
                finally:
                    for task in (get_chunk, overflow, paused, reconnect):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(
                        get_chunk, overflow, paused, reconnect,
                        return_exceptions=True,
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
            ):
                self._startup.error = str(err)
                self._startup.stage = "failed"
            if isinstance(err, StartupError):
                raise HomeAssistantError(
                    f"J1708 startup failed: {err}"
                ) from err
            raise
        finally:
            if startup_task is not None:
                startup_task.cancel()
                await asyncio.gather(startup_task, return_exceptions=True)
            if self._startup is not None:
                self._startup.disconnected()
            if poll_task is not None:
                poll_task.cancel()
                await asyncio.gather(poll_task, return_exceptions=True)
            if self._read_waiter is not None and not self._read_waiter.done():
                self._read_waiter.set_exception(HomeAssistantError(
                    "BlueFire disconnected during J1708 read"
                ))
            self._decoder.reset()
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
        if self._startup is not None:
            if isinstance(message, AdapterMessage):
                handled = self._startup.receive(message)
                if handled and message.command != 255:
                    await asyncio.sleep(0)
                    return
            elif not self._startup.ready:
                self._startup.discarded_reports += 1
                return
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
            if (
                self._read_waiter is not None
                and not self._read_waiter.done()
                and message.pid == self._read_pid
            ):
                self._read_reports[message.mid] = decode_report(message)
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
