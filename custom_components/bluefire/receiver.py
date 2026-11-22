"""BlueFire EZ receiver with opt-in J1708 startup and minute polling."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import datetime, timezone
import logging
import sys
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
from .const import (
    J1708_POLL_INTERVAL, J1708_POLL_MAX_BACKOFF, J1708_POLL_PIDS,
    MAX_CAPTURE_NOTIFICATIONS,
)
from .j1587 import READABLE_PIDS, decode_report
from .protocol import (
    AdapterMessage,
    J1587Report,
    ObdReport,
    PID_DATA,
    PgnReport,
    ProtocolError,
    RecoveringReceiveDecoder,
    parse_message,
)
from .startup import J1708Startup, StartupError

_LOGGER = logging.getLogger(__name__)


class _ReceiverPaused(Exception):
    """Signal that the receiver must yield its BLE connection."""


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
CONNECTION_HISTORY = 10
RECENT_NOTIFICATIONS = 10
NOTIFICATION_BYTES = 512
RECEIVE_ERROR_LIMIT = 10
RECEIVE_ERROR_WINDOW = 10
RECEIVE_SILENCE_TIMEOUT = 30
GATT_HISTORY = 10
GATT_STALL_SECONDS = 2


def _exception_chain(error: BaseException | None) -> list[dict]:
    result = []
    while error is not None and len(result) < 3:
        result.append({
            "type": type(error).__name__,
            "message": str(error)[:512],
        })
        error = error.__cause__ or (
            error.__context__ if not error.__suppress_context__ else None
        )
    return result


def _connection_path(client) -> dict:
    # HA exposes no public connected-scanner accessor. Keep this optional,
    # and never substitute the latest advertisement's source.
    scanner = getattr(client, "_connected_scanner", None)
    source = getattr(scanner, "source", None)
    backend = getattr(client, "backend_id", None)
    return {
        "source": source if isinstance(source, str) else None,
        "source_status": (
            "reported" if isinstance(source, str) else "unavailable"
        ),
        "backend": str(backend) if backend is not None else None,
    }


class BlueFireReceiver:
    """Connect to the documented EZ service and route incoming reports."""

    def __init__(
        self, hass, address: str, bridge, *, health=None,
        j1587_extended=None, j1708_startup: bool = False,
        incidents=None,
    ):
        self.hass = hass
        self.address = address
        self.bridge = bridge
        self.health = health
        self.j1587_extended = j1587_extended
        self.j1708_startup = j1708_startup
        self.incidents = incidents
        self._notification_sequence = 0
        # One fetched notification can await dispatch beside the full queue.
        self._notification_times = deque(maxlen=129)
        self._previous_notification_time = None
        self._previous_notification_length = None
        self._processing = None
        self._processing_history = deque(maxlen=20)
        self._transport = None
        self._startup: J1708Startup | None = None
        self._decoder = RecoveringReceiveDecoder()
        self._control_decoder = RecoveringReceiveDecoder()
        self._framing_error_times: deque[float] = deque(
            maxlen=RECEIVE_ERROR_LIMIT
        )
        self._last_valid_packet: float | None = None
        self._receive_started = monotonic()
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
        self._retry_task: asyncio.Task | None = None
        self._read_waiter: asyncio.Future[None] | None = None
        self._read_pid: int | None = None
        self._read_mid = 0
        self._read_reports: dict[int, dict] = {}
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
        self._connection_history: deque[dict] = deque(
            maxlen=CONNECTION_HISTORY
        )
        self._connection_record: dict | None = None
        self._attempt = 0
        self._attempt_started = monotonic()
        self._initial_counters: dict[str, int] = {}
        self._recent_notifications: deque[dict] = deque(
            maxlen=RECENT_NOTIFICATIONS
        )
        self._last_write: dict | None = None
        self._gatt_operations: deque[dict] = deque(maxlen=GATT_HISTORY)
        self._phase = "idle"
        self._client = None
        self._connection_path: dict | None = None
        self.services: list[dict] = []

    async def async_read(self, pid: int, *, mid: int = 0) -> dict:
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
        if type(pid) is not int or pid not in READABLE_PIDS:
            raise HomeAssistantError(
                "Only supported J1708 sensor reads are allowed"
            )
        if type(mid) is not int or (mid != 0 and not 128 <= mid <= 255):
            raise HomeAssistantError(
                "Expected wildcard MID 0 or controller MID 128..255"
            )
        if self._read_waiter is not None:
            raise HomeAssistantError("A J1708 read is already running")
        waiter: asyncio.Future[None] = (
            asyncio.get_running_loop().create_future()
        )
        self._read_waiter = waiter
        self._read_pid = pid
        self._read_mid = mid
        self._read_reports = {}
        try:
            if mid:
                await startup.async_read(pid, mid=mid)
            else:
                await startup.async_read(pid)
            try:
                async with asyncio.timeout(READ_WINDOW_SECONDS):
                    await asyncio.shield(waiter)
            except TimeoutError:
                if not self._read_reports:
                    raise HomeAssistantError(
                        f"No J1708 PID {pid} report received "
                        f"during read window (requested MID {mid})"
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
                self._read_mid = 0
                self._read_reports = {}

    def connection_diagnostics(self) -> dict:
        """Expose bounded event and per-attempt disconnect histories."""
        return {
            "connected": self._connected,
            "client_connected": (
                self._client.is_connected if self._client is not None
                else None
            ),
            "phase": self._phase,
            "connection_path": deepcopy(self._connection_path),
            "gatt_operations": deepcopy(list(self._gatt_operations)),
            "retry_delay_s": self._reconnect_delay,
            "last_notification": self._last_notification,
            "receive_stream": self._receive_stream_diagnostics(),
            "events": deepcopy(list(self._connection_events)),
            "connection_history": deepcopy(list(self._connection_history)),
        }

    @property
    def connected(self) -> bool:
        """Whether the live BLE notification subscriptions are active."""
        return self._connected

    def _connection_event(self, event: str, reason: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._connection_events.append({
            "time": now,
            "event": event,
            "reason": reason,
        })
        if event == "connecting":
            if self.incidents is not None:
                self.incidents.new_session()
            self._notification_sequence = 0
            self._notification_times.clear()
            self._previous_notification_time = None
            self._previous_notification_length = None
            self._processing = None
            self._processing_history.clear()
            self._transport = None
            self._attempt += 1
            self._attempt_started = monotonic()
            self._initial_counters = (
                dict(self.health.counters) if self.health is not None else {}
            )
            self._recent_notifications.clear()
            self._last_write = None
            self._gatt_operations.clear()
            self._connection_path = None
            self._phase = "connecting"
            self._startup = None
            self._last_valid_packet = None
            self._framing_error_times.clear()
            self._connection_record = {
                "attempt": self._attempt,
                "started_at": now,
                "connected_at": None,
                "ready_at": None,
                "ended_at": None,
                "end_event": None,
                "reason": None,
                "retry_delay_s": None,
                "context": None,
                "connection_path": None,
                "disconnect_callbacks": [],
                "cleanup_operations": [],
            }
            self._connection_history.append(self._connection_record)
        elif self._connection_record is not None:
            if event == "connected":
                self._connection_record["connected_at"] = now
            elif event == "startup_ready":
                self._connection_record["ready_at"] = now
            elif event in ("disconnected", "paused"):
                self._remember_disconnect(event, reason)
                self._connection_record["reason"] = reason

    def _remember_disconnect(self, event: str, reason: str | None) -> None:
        """Freeze session evidence before cleanup clears pending state."""
        record = self._connection_record
        if record is None or record["ended_at"] is not None:
            return
        health = self.health
        now = datetime.now(timezone.utc)
        error = sys.exception()
        record.update({
            "ended_at": now.isoformat(),
            "end_event": event,
            "reason": reason,
            "context": {
                "duration_s": round(monotonic() - self._attempt_started, 3),
                "exception_type": (
                    type(error).__name__ if error is not None else None
                ),
                "exception_message": (
                    str(error) if error is not None else reason
                ),
                "exception_chain": _exception_chain(error),
                "phase": self._phase,
                "client_connected": (
                    self._client.is_connected if self._client is not None
                    else None
                ),
                "connection_path": deepcopy(self._connection_path),
                "gatt_operations": deepcopy(list(self._gatt_operations)),
                "startup": self.startup_diagnostics(),
                "last_notification": self._last_notification,
                "last_data": (
                    health.last_data.isoformat()
                    if health is not None and health.last_data else None
                ),
                "last_write": deepcopy(self._last_write),
                "queue_depth": self._queue.qsize(),
                "queue_capacity": self._queue.maxsize,
                "queue_overflow": self._overflow.is_set(),
                "pending_bytes": self._decoder.pending_bytes,
                "control_pending_bytes": self._control_decoder.pending_bytes,
                "receive_stream": self._receive_stream_diagnostics(),
                "counters": self._connection_counters(),
                "bluetooth": {
                    "rssi": health.rssi,
                    "source": health.source,
                    "present": health.present,
                    "last_advertisement": (
                        health.last_advertisement.isoformat()
                        if health.last_advertisement else None
                    ),
                } if health is not None else None,
                "recent_notifications": deepcopy(
                    list(self._recent_notifications)
                ),
            },
        })
        if event == "disconnected" and not self._closed and not self._paused:
            self._record_incident("connection_failure")

    def _incident_context(self):
        """Persist bounded metadata, never existing raw capture history."""
        return {
            "attempt": self._attempt,
            "phase": self._phase,
            "client_connected": (
                self._client.is_connected
                if self._client is not None else None
            ),
            "connection_path": deepcopy(self._connection_path),
            "transport": deepcopy(self._transport),
            "connection_times": (
                {
                    key: self._connection_record[key]
                    for key in (
                        "started_at", "connected_at", "ready_at", "ended_at",
                    )
                } if self._connection_record is not None else None
            ),
            "disconnect_callbacks": deepcopy(
                self._connection_record["disconnect_callbacks"]
                if self._connection_record is not None else []
            ),
            "cleanup_operations": deepcopy(
                self._connection_record["cleanup_operations"]
                if self._connection_record is not None else []
            ),
            "advertisement": {
                "rssi": self.health.rssi,
                "source": self.health.source,
                "observed_at": (
                    self.health.last_advertisement.isoformat()
                    if self.health.last_advertisement is not None else None
                ),
            } if self.health is not None else None,
            "startup": self.startup_diagnostics(),
            "gatt_operations": deepcopy(list(self._gatt_operations)),
            "receive_stream": self._receive_stream_diagnostics(),
            "processing": deepcopy(self._processing),
            "processing_history": deepcopy(list(self._processing_history)),
            "queue_depth": self._queue.qsize(),
            "queue_overflow": self._overflow.is_set(),
            "counters": self._connection_counters(),
            "failure": (
                {
                    "reason": str(self._connection_record["reason"])[:512],
                    "exception_chain": self._connection_record[
                        "context"
                    ]["exception_chain"],
                }
                if self._connection_record is not None
                and self._connection_record["context"] is not None else None
            ),
        }

    def _record_incident(self, kind):
        if self.incidents is not None:
            self.incidents.record(kind, self._incident_context())

    def _connection_counters(self) -> dict[str, int]:
        return {
            name: value - self._initial_counters.get(name, 0)
            for name, value in (
                self.health.counters.items()
                if self.health is not None else ()
            )
        }

    def _receive_is_recent(self) -> bool:
        return (
            self._last_valid_packet is not None
            and monotonic() - self._last_valid_packet < RECEIVE_SILENCE_TIMEOUT
        )

    def _receive_stream_diagnostics(self) -> dict:
        now = monotonic()
        return {
            "resynchronizing": self._decoder.resynchronizing,
            "resynchronizations": self._decoder.resynchronizations,
            "control_resynchronizing": self._control_decoder.resynchronizing,
            "received_bytes": self._control_decoder.received_bytes,
            "discarded_bytes": self._control_decoder.discarded_bytes,
            "buffer_start_offset": self._control_decoder.buffer_start_offset,
            "last_valid_packet_age_s": (
                round(now - self._last_valid_packet, 3)
                if self._last_valid_packet is not None else None
            ),
            "recent_framing_errors": sum(
                now - observed < RECEIVE_ERROR_WINDOW
                for observed in self._framing_error_times
            ),
            "error_limit": RECEIVE_ERROR_LIMIT,
            "error_window_s": RECEIVE_ERROR_WINDOW,
            "silence_timeout_s": RECEIVE_SILENCE_TIMEOUT,
        }

    def _record_stream_errors(self, *, recovered: bool = False) -> None:
        errors = self._decoder.framing_errors
        now = monotonic()
        for error in errors:
            self._framing_error_times.append(now)
            self._health_error("framing_errors", error)
            _LOGGER.warning("BlueFire receive stream recovering: %s", error)
        if recovered:
            # Recovered packets are progress, not a reason to restart a
            # working session and repeat authentication.
            self._framing_error_times.clear()
            return
        if sum(
            now - observed < RECEIVE_ERROR_WINDOW
            for observed in self._framing_error_times
        ) >= RECEIVE_ERROR_LIMIT:
            raise BleakError(
                "Too many malformed BlueFire receive packets "
                f"({RECEIVE_ERROR_LIMIT} in {RECEIVE_ERROR_WINDOW} seconds)"
            )

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
        started_at = datetime.now(timezone.utc).isoformat()
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
        self._connection_event("capture_started")
        try:
            try:
                async with asyncio.timeout(duration):
                    await ended.wait()
            except TimeoutError:
                pass
        finally:
            self._capture_callback = None
            stopped_at = datetime.now(timezone.utc).isoformat()
            self._connection_event("capture_stopped")
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
            "started_at": started_at,
            "stopped_at": stopped_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
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

    async def _async_poll(self) -> None:
        """Poll each minute, backing off each silent PID independently."""
        next_poll = monotonic() + J1708_POLL_INTERVAL
        retry_at = {pid: next_poll for pid in J1708_POLL_PIDS}
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
            self._session_healthy = False
            self._reconnect_delay = 0
            self._connection_event("connecting")
            session_task = asyncio.create_task(
                self._async_receive_session(), name="BlueFire BLE session"
            )
            self._session_task = session_task
            paused_session = False
            end_reason = "Receiver stopped"
            end_error_type = None
            end_exception_chain = []
            try:
                await session_task
                delay = RECONNECT_MIN
            except asyncio.CancelledError as err:
                end_error_type = "CancelledError"
                end_exception_chain = _exception_chain(err)
                current_task = asyncio.current_task()
                if current_task is not None and current_task.cancelling():
                    end_reason = "Receiver task cancelled"
                    raise
                if not (self._paused or self._closed):
                    raise
                paused_session = self._paused and not self._closed
                end_reason = (
                    "Receiver pause requested" if paused_session
                    else "Receiver stopped"
                )
            except _ReceiverPaused:
                paused_session = True
                end_reason = "Receiver pause requested"
            except (
                BleakError, HomeAssistantError, OSError, TimeoutError
            ) as err:
                end_reason = str(err)
                end_error_type = type(err).__name__
                end_exception_chain = _exception_chain(err)
                self._health_error("connection_errors", str(err))
                _LOGGER.warning("BlueFire BLE receiver unavailable: %s", err)
            except ProtocolError as err:
                end_reason = str(err)
                end_error_type = type(err).__name__
                end_exception_chain = _exception_chain(err)
                self._health_error("framing_errors", str(err))
                _LOGGER.warning("BlueFire receive stream rejected: %s", err)
            except Exception as err:
                end_reason = "Unexpected receiver session failure"
                end_error_type = type(err).__name__
                end_exception_chain = _exception_chain(err)
                _LOGGER.exception("BlueFire receiver session failed")
            finally:
                self._connection_event(
                    "paused" if paused_session else "disconnected", end_reason
                )
                if self._connection_record is not None:
                    context = self._connection_record["context"]
                    context["counters"] = self._connection_counters()
                    if end_error_type is not None:
                        context["exception_type"] = end_error_type
                    if end_exception_chain:
                        context["exception_chain"] = end_exception_chain
                if (
                    self.incidents is not None
                    and not self._closed and not self._paused
                ):
                    self.incidents.finish_session(self._incident_context())
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
                self._phase = "retry_wait"
                if self._connection_record is not None:
                    self._connection_record["retry_delay_s"] = delay
                self._retry_task = asyncio.create_task(asyncio.sleep(delay))
                try:
                    await self._retry_task
                except asyncio.CancelledError:
                    current_task = asyncio.current_task()
                    if current_task is not None and current_task.cancelling():
                        raise
                    delay = RECONNECT_MIN
                else:
                    delay = min(delay * 2, RECONNECT_MAX)
                finally:
                    self._retry_task = None

    def stop(self) -> None:
        """Stop retries and interrupt an active BLE session."""
        self._closed = True
        self._resume_event.set()
        if self._session_task is not None:
            self._session_task.cancel()
        if self._retry_task is not None:
            self._retry_task.cancel()

    async def async_pause(self) -> None:
        """Release BLE and suspend retries until explicitly resumed."""
        self._paused = True
        self._resume_event.clear()
        self._pause_event.set()
        if self._session_task is not None:
            self._session_task.cancel()
        if self._retry_task is not None:
            self._retry_task.cancel()
        try:
            async with asyncio.timeout(SESSION_CLOSE_TIMEOUT):
                await self._session_closed.wait()
        except TimeoutError as err:
            raise HomeAssistantError(
                "BlueFire receiver did not release its BLE connection"
            ) from err

    def async_resume(self) -> None:
        """Restart live reception after a pause."""
        self._paused = False
        self._pause_event.clear()
        self._resume_event.set()

    async def _async_gatt_operation(
        self, operation: str, action: Callable[[], Awaitable[None]],
        timeout: float, *, characteristic=None,
        command: int | None = None, length: int | None = None,
        lock: asyncio.Lock | None = None,
        request: dict | None = None,
    ) -> None:
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "characteristic": getattr(characteristic, "uuid", None),
            "command": command,
            "length": length,
            "status": "waiting_for_lock" if lock is not None else "pending",
            "started_at": None,
            "elapsed_s": None,
            "lock_wait_s": None,
            "io_elapsed_s": None,
            "exception_chain": [],
            "request": request,
        }
        self._gatt_operations.append(record)
        started = monotonic()
        io_started = None
        stalled = None
        if self.incidents is not None and operation == "write":
            async def watch_stall():
                await asyncio.sleep(GATT_STALL_SECONDS)
                if (
                    record["status"] in ("pending", "waiting_for_lock")
                    and not self._closed and not self._paused
                    and self._phase != "cleanup"
                ):
                    record["observed_elapsed_s"] = round(
                        monotonic() - started, 3,
                    )
                    self._record_incident("gatt_stall")

            stalled = asyncio.create_task(watch_stall())

        async def perform() -> None:
            nonlocal io_started
            io_started = monotonic()
            record["lock_wait_s"] = round(io_started - started, 4)
            record["status"] = "pending"
            record["started_at"] = datetime.now(timezone.utc).isoformat()
            if operation == "write":
                self._last_write = record
            await action()

        try:
            async with asyncio.timeout(timeout):
                if lock is not None:
                    async with lock:
                        await perform()
                else:
                    await perform()
        except (
            BleakError, OSError, TimeoutError, asyncio.CancelledError
        ) as err:
            record["status"] = (
                "cancelled" if isinstance(err, asyncio.CancelledError)
                else "failed"
            )
            record["exception_chain"] = _exception_chain(err)
            raise
        else:
            record["status"] = "completed"
        finally:
            record["elapsed_s"] = round(monotonic() - started, 3)
            record["io_elapsed_s"] = (
                round(monotonic() - io_started, 4)
                if io_started is not None else None
            )
            record["completed_at"] = datetime.now(timezone.utc).isoformat()
            if stalled is not None:
                stalled.cancel()
                try:
                    await stalled
                except asyncio.CancelledError:
                    current = asyncio.current_task()
                    if current is not None and current.cancelling():
                        raise
            if record["status"] == "failed" and self._phase != "cleanup":
                self._record_incident("gatt_failure")
            if self._phase == "cleanup" and (
                self._connection_record is not None
            ):
                self._connection_record["cleanup_operations"].append(
                    deepcopy(record)
                )

    async def _async_receive_session(self) -> None:
        self._phase = "locating_device"
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise HomeAssistantError(
                "BlueFire adapter is not visible to a connectable "
                "Bluetooth scanner"
            )

        record = self._connection_record
        cleanup_started = False

        def disconnected(client) -> None:
            callback = {
                "time": datetime.now(timezone.utc).isoformat(),
                "during_cleanup": cleanup_started,
                "during_establishment": (
                    self._client is None and not cleanup_started
                ),
                "client_connected": client.is_connected,
            }
            if record is not None:
                callbacks = record["disconnect_callbacks"]
                callbacks.append(callback)
                del callbacks[:-CONNECTION_HISTORY]
            if record is self._connection_record:
                self._connection_event(
                    "ble_disconnected",
                    "BLE cleanup" if cleanup_started else "BLE link lost",
                )

        self._phase = "connecting"
        try:
            async with asyncio.timeout(CONNECTION_TIMEOUT):
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    device,
                    "BlueFire receiver",
                    disconnected_callback=disconnected,
                    ble_device_callback=lambda: (
                        bluetooth.async_ble_device_from_address(
                            self.hass, self.address, connectable=True
                        )
                    ),
                )
        except TimeoutError as err:
            raise TimeoutError(
                "BlueFire Bluetooth connection timed out "
                f"(limit: {CONNECTION_TIMEOUT} seconds)"
            ) from err
        self._client = client
        started = []
        startup_task: asyncio.Task | None = None
        poll_task: asyncio.Task | None = None
        try:
            self._phase = "validating_services"
            self._connection_path = _connection_path(client)
            if record is not None:
                record["connection_path"] = deepcopy(self._connection_path)
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
            mtu = getattr(client, "mtu_size", None)
            self._transport = {
                "reported_mtu": mtu if type(mtu) is int else None,
                "mtu_source": "bleak.mtu_size; may be a backend default",
                "mtu_verified": False,
                "connection_parameters": None,
                "hci_disconnect_reason": None,
                "services": deepcopy(self.services),
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

                write_lock = asyncio.Lock()

                async def write(packet: bytes) -> None:
                    request = None
                    if packet[2] == 155 and len(packet) == 12:
                        request = {
                            "pid": int.from_bytes(packet[4:6], "big"),
                            "mid": packet[3],
                            "mode": (
                                "on_request" if packet[6] else "monitoring"
                            ),
                            "retrieval_type": packet[7],
                            "interval_ms": int.from_bytes(packet[8:10], "big"),
                        }
                    await self._async_gatt_operation(
                        "write",
                        lambda: client.write_gatt_char(
                            write_characteristic, packet, response=True
                        ),
                        BLE_OPERATION_TIMEOUT,
                        characteristic=write_characteristic,
                        command=packet[2], length=len(packet), lock=write_lock,
                        request=request,
                    )

                self._startup = J1708Startup(
                    write, getattr(device, "name", None),
                    self.j1587_extended,
                    is_receiving=self._receive_is_recent,
                )

            self._queue = asyncio.Queue(maxsize=128)
            self._notification_times.clear()
            self._overflow.clear()
            self._reconnect_event.clear()
            self._pause_event.clear()
            self._last_valid_packet = None
            self._receive_started = monotonic()
            self._phase = "subscribing"
            for uuid in notify_uuids:
                characteristic = characteristics[uuid]
                await self._async_gatt_operation(
                    "start_notify",
                    lambda: client.start_notify(
                        characteristic, self._notification_received
                    ),
                    BLE_OPERATION_TIMEOUT, characteristic=characteristic,
                )
                started.append(characteristic)
            _LOGGER.info(
                "BlueFire receiver subscribed to %d EZ characteristics",
                len(notify_uuids),
            )
            self._connected = True
            self._session_ended = asyncio.Event()
            self._connection_event("connected")

            async def maintain_session(startup: J1708Startup) -> None:
                nonlocal poll_task
                self._phase = "startup"
                await startup.run()
                self._phase = "receiving"
                self._session_healthy = True
                self._connection_event("startup_ready")
                poll_task = asyncio.create_task(
                    self._async_poll(), name="BlueFire J1708 polling"
                )
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
            else:
                self._phase = "receiving"
            while client.is_connected and not self._closed:
                if startup_task is not None and startup_task.done():
                    startup_task.result()
                    startup_task = None
                if poll_task is not None and poll_task.done():
                    poll_task.result()
                    raise BleakError("BlueFire J1708 polling stopped")
                if self._overflow.is_set():
                    raise BleakError("BlueFire receive queue overflow")
                if self._reconnect_event.is_set():
                    raise BleakError("Passive J1708 monitoring restore failed")
                last_received = (
                    self._last_valid_packet
                    if self._last_valid_packet is not None
                    else self._receive_started
                )
                if monotonic() - last_received >= RECEIVE_SILENCE_TIMEOUT:
                    raise BleakError(
                        "No valid BlueFire receive packets for "
                        f"{RECEIVE_SILENCE_TIMEOUT} seconds"
                    )
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
                observed = (
                    self._notification_times.popleft()
                    if self._notification_times else None
                )
                self._processing = {
                    "sequence": observed[0] if observed is not None else None,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "queue_wait_s": (
                        round(monotonic() - observed[1], 4)
                        if observed is not None else None
                    ),
                    "status": "decoding",
                }
                processing_started = monotonic()
                bodies = self._decoder.feed(chunk)
                self._record_stream_errors(recovered=bool(bodies))
                for body in bodies:
                    try:
                        await self._async_process_body(body)
                    except ProtocolError:
                        continue
                self._processing.update({
                    "status": "completed",
                    "elapsed_s": round(monotonic() - processing_started, 4),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                self._processing_history.append(deepcopy(self._processing))
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
            error = sys.exception()
            paused = self._paused and not self._closed
            if paused:
                reason = "Receiver pause requested"
            elif self._closed:
                reason = "Receiver stopped"
            elif error is not None:
                reason = str(error)
            else:
                reason = "Bluetooth session ended"
            self._remember_disconnect(
                "paused" if paused else "disconnected", reason
            )
            cleanup_started = True
            self._phase = "cleanup"
            self._connected = False
            self._session_ended.set()
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
            self._control_decoder.reset()
            for characteristic in reversed(started):
                try:
                    await self._async_gatt_operation(
                        "stop_notify",
                        lambda: client.stop_notify(characteristic),
                        BLE_CLEANUP_TIMEOUT, characteristic=characteristic,
                    )
                except (BleakError, OSError, TimeoutError):
                    _LOGGER.debug(
                        "Unable to stop BlueFire BLE notification",
                        exc_info=True,
                    )
            try:
                await self._async_gatt_operation(
                    "disconnect", client.disconnect, BLE_CLEANUP_TIMEOUT,
                )
            except (BleakError, OSError, TimeoutError):
                _LOGGER.debug(
                    "BlueFire BLE disconnect failed", exc_info=True
                )
            finally:
                self._client = None
                self._phase = "closed" if self._closed else "idle"

    def _notification_received(self, _characteristic, data: bytearray) -> None:
        """Queue callbacks from both EZ characteristics in arrival order."""
        self._last_notification = datetime.now(timezone.utc).isoformat()
        observed = monotonic()
        self._notification_sequence += 1
        if self._startup is None or self._startup.ready:
            self._recent_notifications.append({
                "time": self._last_notification,
                "characteristic": getattr(_characteristic, "uuid", ""),
                "handle": getattr(_characteristic, "handle", None),
                "length": len(data),
                "hex": bytes(data[:NOTIFICATION_BYTES]).hex(),
                "truncated": len(data) > NOTIFICATION_BYTES,
            })
        if self._capture_callback is not None:
            self._capture_callback(_characteristic, data)
        if self.health is not None:
            self.health.count("notifications")
            self.health.count("bytes", len(data))
        try:
            self._queue.put_nowait(bytes(data))
            self._notification_times.append((
                self._notification_sequence, observed,
            ))
        except asyncio.QueueFull:
            _LOGGER.warning("BlueFire receive queue overflow; reconnecting")
            self._overflow.set()
        try:
            pending = self._control_decoder.pending_bytes
            stream_start = self._control_decoder.received_bytes
            bodies = self._control_decoder.feed(bytes(data))
        except ProtocolError:
            # The queued live consumer records/rejects this same framing error.
            return
        if self.incidents is not None:
            note = {
                "sequence": self._notification_sequence,
                "time": self._last_notification,
                "characteristic": getattr(_characteristic, "uuid", None),
                "length": len(data),
                "previous_length": self._previous_notification_length,
                "gap_s": (
                    round(observed - self._previous_notification_time, 4)
                    if self._previous_notification_time is not None else None
                ),
                "stream_start": stream_start,
                "stream_end": self._control_decoder.received_bytes,
                "pending_before": pending,
                "pending_after": self._control_decoder.pending_bytes,
                "phase": self._phase,
                "commands": [
                    {"command": body[0], "body_length": len(body)}
                    for body in bodies[:32]
                ],
                "framing_errors": list(self._control_decoder.framing_errors),
                "error_offsets": list(
                    self._control_decoder.framing_error_offsets
                ),
                "recoveries": list(self._control_decoder.recovery_events),
                "discarded_bytes": self._control_decoder.discarded_bytes,
            }
            if self.incidents.raw_enabled and (
                not self.j1708_startup
                or self._startup is not None and self._startup.ready
            ):
                note["raw_reports"] = [
                    {"command": body[0], "body_hex": body.hex()}
                    for body in bodies if body[0] in (151, 154, 174)
                ][:4]
            self.incidents.observe(note)
            if self._control_decoder.framing_errors:
                self._record_incident("framing_error")
            if self._overflow.is_set():
                self._record_incident("queue_overflow")
        self._previous_notification_length = len(data)
        self._previous_notification_time = observed
        if bodies:
            self._last_valid_packet = monotonic()
        if self._startup is not None and self._startup.ready:
            for body in bodies:
                self._collect_read_report(body)
                if body[0] == 7:
                    # Resolve probes even while MQTT publication awaits IO.
                    self._startup.receive(AdapterMessage(7, body[1:]))

    def _decode_j1587_report(self, message: J1587Report) -> dict:
        return decode_report(
            message, profile=getattr(
                self.bridge, "diagnostic_profile", None,
            ) if message.mid == 128 else None,
        )

    def _collect_read_report(self, body: bytes) -> None:
        if (
            body[0] != PID_DATA or self._read_waiter is None
            or self._read_waiter.done() or self._overflow.is_set()
        ):
            return
        try:
            message = parse_message(
                body, j1587_extended=self.j1587_extended,
            )
            if (
                not isinstance(message, J1587Report)
                or message.pid != self._read_pid
                or self._read_mid not in (0, message.mid)
            ):
                return
            decoded = self._decode_j1587_report(message)
        except ValueError:
            # The queued consumer logs/counts invalid reports once.
            return
        self._read_reports[message.mid] = {
            "data": message.data.hex(), **decoded,
        }

    async def _async_publish_report(self, action):
        processing = self._processing
        started = monotonic()
        if processing is not None:
            processing.update({
                "status": "publishing",
                "publish_status": "pending",
                "publish_started_at": datetime.now(timezone.utc).isoformat(),
            })
        try:
            await action()
        finally:
            if processing is not None:
                processing.update({
                    "publish_elapsed_s": round(monotonic() - started, 4),
                    "publish_status": (
                        "failed"
                        if sys.exception() is not None else "completed"
                    ),
                })

    async def _async_process_body(self, body: bytes) -> None:
        try:
            message = parse_message(
                body, j1587_extended=self.j1587_extended
            )
            if isinstance(message, J1587Report):
                self._decode_j1587_report(message)
        except ValueError as err:
            self._health_error("parse_errors", str(err))
            _LOGGER.warning("BlueFire report rejected: %s", err)
            raise ProtocolError(str(err)) from err
        if self.health is not None:
            self.health.count("packets")
        if self._processing is not None:
            self._processing["status"] = "processing"
            self._processing["command"] = body[0]
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
            await self._async_publish_report(
                lambda: self.bridge.async_process_pgn_report(message),
            )
        elif isinstance(message, J1587Report):
            self._session_healthy = True
            if self.health is not None:
                self.health.count("j1587_reports")
                self.health.data_seen()
            await self._async_publish_report(
                lambda: self.bridge.async_process_j1587(message),
            )
        elif isinstance(message, ObdReport):
            self._session_healthy = True
            if self.health is not None:
                self.health.count("obd_reports")
                self.health.data_seen()
            await self._async_publish_report(
                lambda: self.bridge.async_process_obd_report(message),
            )
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
