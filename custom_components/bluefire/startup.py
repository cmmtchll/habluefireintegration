"""Guarded EZ startup, passive monitoring and allowlisted J1708 reads."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
import re

from .const import J1708_READ_ACTIONS
from .j1587 import ENTITIES
from .protocol import AdapterMessage, receive_checksum

STEP_TIMEOUT = 10
# Wire compatibility version, not the integration version or an app identity.
CLIENT_COMPATIBILITY = (12, 5, 6)
PLATFORM_UNSPECIFIED = 0
REPORT_INTERVAL_MS = 1000
_LOGGER = logging.getLogger(__name__)


class StartupError(ValueError):
    """Startup was rejected, malformed, incompatible or timed out."""


def client_packet(body: bytes) -> bytes:
    """Encode client framing; it is not an adapter receive packet."""
    if not isinstance(body, bytes) or not 1 <= len(body) <= 17:
        raise StartupError("Expected a client body of 1..17 bytes")
    packet = len(body).to_bytes(2, "big") + body
    return packet + bytes((receive_checksum(packet),))


def pid_subscription(pid: int, *, on_request: bool = False) -> bytes:
    """Wildcard MID; one-shot ECU retrieval or the normal passive monitor."""
    if type(pid) is not int or pid not in {p.pid for p in ENTITIES}:
        raise StartupError("Unsupported J1708 PID")
    return client_packet(
        b"\x9b\x00" + pid.to_bytes(2, "big")
        + bytes((int(on_request), 1 if on_request else 2))
        + (0 if on_request else REPORT_INTERVAL_MS).to_bytes(2, "big")
        + b"\x00"
    )


class J1708Startup:
    """One session's response-driven startup; never set or reset security."""

    def __init__(
        self, write: Callable[[bytes], Awaitable[None]],
        name: str | None, extended: bool,
    ) -> None:
        self._write = write
        self._heartbeat = asyncio.Event()
        self._response: asyncio.Future[bytes] | None = None
        self.expected_command: int | None = None
        self.stage = "waiting_for_heartbeat"
        self.error: str | None = None
        self.firmware: tuple[int, ...] | None = None
        match = re.fullmatch(
            r"BlueFire[^\r\n]*-(4\.\d+(?:\.\d+){0,2})", name or ""
        )
        if match:
            self.firmware = tuple(int(v) for v in match[1].split("."))
        self.profile = 4 if match else 3
        self.extended = extended
        self.j1708_available: bool | None = None
        self.subscriptions_sent = 0
        self.discarded_reports = 0

    @property
    def ready(self) -> bool:
        return self.stage == "ready"

    def diagnostics(self) -> dict:
        return {
            "stage": self.stage,
            "profile": self.profile,
            "firmware": list(self.firmware) if self.firmware else None,
            "expected_command": self.expected_command,
            "j1708_available": self.j1708_available,
            "subscriptions_sent": self.subscriptions_sent,
            "discarded_reports": self.discarded_reports,
            "error": self.error,
        }

    def disconnected(self) -> None:
        if self.stage != "failed":
            self.stage = "disconnected"

    async def async_read(self, pid: int, *, restore: bool = False) -> None:
        """Request allowlisted readings, never arbitrary bus writes."""
        if not self.ready:
            raise StartupError("J1708 startup is not ready")
        if type(pid) is not int or pid not in J1708_READ_ACTIONS.values():
            raise StartupError(
                "Only supported J1708 sensor reads are allowed"
            )
        await self._write(pid_subscription(pid, on_request=not restore))

    def receive(self, message: AdapterMessage) -> bool:
        """Correlate controls without interpreting heartbeats as telemetry."""
        if message.command == 255:
            if message.data:
                raise StartupError("Malformed heartbeat")
            self._heartbeat.set()
            return True
        if message.command == 155 and message.data == b"\x00":
            raise StartupError("Adapter rejected a J1708 PID subscription")
        if (
            message.command == self.expected_command
            and self._response is not None
            and not self._response.done()
        ):
            self._response.set_result(message.data)
            return True
        if message.command in (130, 169, 171) and message.data == b"\x00":
            raise StartupError("Adapter revoked or rejected authentication")
        return message.command in (
            0, 7, 8, 9, 130, 150, 153, 155, 169, 171, 206,
        )

    async def _request(self, stage: str, body: bytes) -> bytes:
        self.stage = stage
        self.expected_command = body[0]
        response: asyncio.Future[bytes] = (
            asyncio.get_running_loop().create_future()
        )
        self._response = response
        try:
            async with asyncio.timeout(STEP_TIMEOUT):
                await self._write(client_packet(body))
                return await response
        finally:
            self.expected_command = None
            response.cancel()
            self._response = None

    async def _accepted(self, stage: str, body: bytes) -> None:
        result = await self._request(stage, body)
        if result == b"\x00":
            detail = (
                "; secured adapters are not supported"
                if stage.startswith("authentication") else ""
            )
            raise StartupError(f"{stage} rejected{detail}")
        if result != b"\x01":
            raise StartupError(f"Malformed {stage} response")

    async def _ack(self, stage: str, body: bytes, value: int = 1) -> None:
        result = await self._request(stage, body)
        if result not in (b"", bytes((value,))):
            raise StartupError(f"Unexpected {stage} acknowledgement")

    async def run(self) -> None:
        """Negotiate, authenticate, subscribe and start reports."""
        try:
            async with asyncio.timeout(STEP_TIMEOUT):
                await self._heartbeat.wait()
            if self.profile == 3:
                result = await self._request("version", b"\x00")
                if len(result) != 21 or not any(result[2:4]):
                    raise StartupError("Malformed firmware/hardware version")
                self.firmware = (result[0], result[1], result[4])
                if self.firmware[0] != 3 or self.firmware < (3, 14):
                    raise StartupError("Unsupported firmware; expected 3.14+")
                await self._write(client_packet(bytes((
                    150, CLIENT_COMPATIBILITY[1], PLATFORM_UNSPECIFIED,
                ))))
                version_body = bytes((9, *CLIENT_COMPATIBILITY[:2]))
            else:
                version_body = bytes((
                    9, *CLIENT_COMPATIBILITY, PLATFORM_UNSPECIFIED,
                ))
            if self.extended != (
                self.profile == 4
                or self.firmware is not None and self.firmware >= (3, 19)
            ):
                raise StartupError(
                    "J1587 format disagrees with firmware; reconfigure it"
                )
            await self._accepted("compatibility", version_body)
            if self.profile == 3:
                await self._accepted("authentication_1", b"\x82\x00")
                await self._accepted("authentication_2", b"\xab\x00")
            else:
                await self._accepted("authentication", b"\xa9\x00\x00\x00")
            variables = await self._request("adapter_variables", b"\xce")
            if self.profile == 3:
                if len(variables) != 15:
                    raise StartupError("Malformed firmware 3.x variables")
            else:
                newer = self.firmware is not None and self.firmware >= (4, 1)
                minimum, ignore_index = (32, 11) if newer else (33, 13)
                if len(variables) < minimum:
                    raise StartupError("Truncated firmware 4.x variables")
                if variables[ignore_index] != 0:
                    raise StartupError(
                        "J1708 is disabled in adapter settings; enable it "
                        "in the vendor app before connecting"
                    )
            available = await self._request("j1708_availability", b"\x07")
            if available not in (b"\x00", b"\x01"):
                raise StartupError("Malformed J1708 availability response")
            self.j1708_available = available == b"\x01"
            if not self.j1708_available:
                # The vendor queries this status without gating report setup.
                _LOGGER.warning(
                    "Adapter reported J1708 unavailable during initialization;"
                    " continuing passive report setup; waiting for telemetry"
                )
            await self._ack("application_connected", b"\x08")
            await self._ack("stop_reports", b"\x99\x00", 0)
            self.stage = "subscribing"
            for parameter in ENTITIES:
                # Vendor MID 0 is a wildcard, not the source of reports.
                await self._write(pid_subscription(parameter.pid))
                self.subscriptions_sent += 1
            await self._ack("start_reports", b"\x99\x01")
            self.stage = "ready"
        except (StartupError, TimeoutError) as err:
            self.error = (
                f"Timed out during {self.stage}"
                if isinstance(err, TimeoutError) else str(err)
            )
            self.stage = "failed"
            raise StartupError(self.error) from err
