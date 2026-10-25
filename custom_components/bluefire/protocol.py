"""Offline receive-format analysis, not a live BlueFire driver.

Based on static observations of Android 9.7.5/11.2.3 and Windows 12.5.6.
All formats remain hardware-unverified.
No authentication, writes, or CAN-ID fabrication. Offline decoding is strict;
the live receiver explicitly opts into bounded stream recovery.
"""

from dataclasses import dataclass


# An analysis safety limit based on the app's receive-buffer constant, not a
# claim about every adapter/firmware's maximum wire message size.
MAX_PACKET_SIZE = 264
MAX_BODY_SIZE = MAX_PACKET_SIZE - 4
PGN_DATA = 151
PID_DATA = 154
OBD_DATA = 174


class ProtocolError(ValueError):
    """Malformed, incomplete, or unsupported analysis input."""


def receive_checksum(body: bytes) -> int:
    """Return the complement of the payload's end-around-carry sum."""
    total = sum(body)
    while total > 255:
        total = (total & 255) + (total >> 8)
    return 255 - total


def _receive_length(header: bytes | bytearray) -> int:
    high, low, check = header
    if check != high ^ low:
        raise ProtocolError("Invalid receive length XOR")
    length = (high << 8) | low
    if not 1 <= length <= MAX_BODY_SIZE:
        raise ProtocolError("Receive length outside analysis limit")
    return length


class ReceiveDecoder:
    """Bounded, incremental adapter-to-client packet decoder.

    Use a separate instance per independently framed capture stream/session.
    Newer apps merge both EZ characteristic callbacks into one ordered queue;
    do not split or reorder their Adapter.txt recording lines. Stream mode
    preserves concatenated packets; padded-notification mode accepts one
    packet followed by zero padding in the completing notification. Nonzero
    tails are rejected rather than guessed to be padding or a second packet.
    This stricter policy needs checking against actual legacy BLE captures.

    A failing feed is atomic to its caller: no bodies from that call are
    returned and all pending bytes are cleared. Resume only at a known packet
    boundary. reset() must be called at disconnect/capture-session boundaries.
    """

    def __init__(self, *, padded_notifications: bool = False) -> None:
        self._padded_notifications = padded_notifications
        self._buffer = bytearray()

    @property
    def pending_bytes(self) -> int:
        """Expose buffered size without exposing capture contents."""
        return len(self._buffer)

    def reset(self) -> None:
        """Discard fragments from the previous capture session."""
        self._buffer.clear()

    def finish(self) -> None:
        """Reject a truncated capture and discard its partial packet."""
        if self._buffer:
            self.reset()
            raise ProtocolError("Capture ended with an incomplete packet")

    def feed(self, chunk: bytes) -> tuple[bytes, ...]:
        """Decode a stream chunk or a single legacy notification value."""
        if not isinstance(chunk, bytes):
            self.reset()
            raise ProtocolError("Expected immutable receive bytes")
        bodies = []
        offset = 0
        try:
            while offset < len(chunk):
                if len(self._buffer) < 3:
                    needed = 3 - len(self._buffer)
                else:
                    needed = int.from_bytes(self._buffer[:2], "big") + 4
                    needed -= len(self._buffer)
                end = min(len(chunk), offset + needed)
                self._buffer.extend(chunk[offset:end])
                offset = end
                if len(self._buffer) < 3:
                    continue
                length = _receive_length(self._buffer[:3])
                if len(self._buffer) < length + 4:
                    continue
                body = bytes(self._buffer[3:-1])
                if receive_checksum(body) != self._buffer[-1]:
                    raise ProtocolError("Invalid receive payload checksum")
                bodies.append(body)
                self.reset()
                if self._padded_notifications:
                    if any(chunk[offset:]):
                        raise ProtocolError("Nonzero notification padding")
                    break
        except ProtocolError:
            self.reset()
            raise
        return tuple(bodies)


class RecoveringReceiveDecoder(ReceiveDecoder):
    """Live stream decoder requiring two adjacent valid packets to recover.

    Corrupt data is never returned. Recovery checks both length headers and
    payload checksums, including across notifications, and buffers at most two
    maximum-sized packets. Strict offline and padded decoding stay unchanged.
    """

    def __init__(self) -> None:
        super().__init__()
        self.reset()

    def reset(self) -> None:
        super().reset()
        self.resynchronizing = False
        self.resynchronizations = 0
        self.framing_errors: tuple[str, ...] = ()

    def _packet_end(self, offset: int) -> int | None:
        try:
            length = _receive_length(self._buffer[offset:offset + 3])
        except ProtocolError:
            return None
        end = offset + length + 4
        if end > len(self._buffer):
            # Keep plausible fragmented candidates until more bytes arrive.
            return end
        body = bytes(self._buffer[offset + 3:end - 1])
        return end if receive_checksum(body) == self._buffer[end - 1] else None

    def _recover(self) -> tuple[bytes, ...]:
        keep = max(0, len(self._buffer) - 2)
        for offset in range(keep):
            first = self._packet_end(offset)
            if first is None:
                continue
            if first > len(self._buffer) or len(self._buffer) - first < 3:
                keep = min(keep, offset)
                continue
            second = self._packet_end(first)
            if second is None:
                continue
            if second > len(self._buffer):
                keep = min(keep, offset)
                continue
            bodies = (
                bytes(self._buffer[offset + 3:first - 1]),
                bytes(self._buffer[first + 3:second - 1]),
            )
            del self._buffer[:second]
            self.resynchronizing = False
            self.resynchronizations += 1
            return bodies
        del self._buffer[:keep]
        return ()

    def feed(self, chunk: bytes) -> tuple[bytes, ...]:
        if not isinstance(chunk, bytes):
            self.reset()
            raise ProtocolError("Expected immutable receive bytes")
        bodies = []
        errors = []
        offset = 0
        while offset < len(chunk):
            end = min(
                len(chunk), offset + MAX_PACKET_SIZE * 2 - len(self._buffer)
            )
            self._buffer.extend(chunk[offset:end])
            offset = end
            while self._buffer:
                if self.resynchronizing:
                    recovered = self._recover()
                    if not recovered:
                        break
                    bodies.extend(recovered)
                    continue
                if len(self._buffer) < 3:
                    break
                try:
                    length = _receive_length(self._buffer[:3])
                    if len(self._buffer) < length + 4:
                        break
                    body = bytes(self._buffer[3:length + 3])
                    if receive_checksum(body) != self._buffer[length + 3]:
                        raise ProtocolError("Invalid receive payload checksum")
                    bodies.append(body)
                    del self._buffer[:length + 4]
                except ProtocolError as err:
                    errors.append(str(err))
                    self.resynchronizing = True
        self.framing_errors = tuple(errors)
        return tuple(bodies)


@dataclass(frozen=True)
class AdapterMessage:
    """A control or unknown command, never evidence of vehicle telemetry."""

    command: int
    data: bytes


@dataclass(frozen=True)
class PgnReport:
    """Vendor PGN envelope, NOT an original CAN frame.

    Preserve the 16-bit PGN field and separate data-page/priority bytes as
    reported. PDU1 destination interpretation and metadata bit semantics
    still require hardware evidence; do not manufacture an arbitration ID.
    """

    source_address: int
    pgn: int
    priority: int
    data_page: int
    data: bytes


@dataclass(frozen=True)
class J1587Report:
    """J1708/J1587 MID/PID data, deliberately separate from J1939."""

    mid: int
    pid: int
    data: bytes


@dataclass(frozen=True)
class ObdReport:
    """OBD source/mode/PID data, deliberately separate from J1939."""

    source: int
    mode: int
    pid: int
    data: bytes


def _report_data(body: bytes, length_offset: int) -> bytes:
    if len(body) <= length_offset:
        raise ProtocolError("Truncated report header")
    if len(body) != length_offset + 1 + body[length_offset]:
        raise ProtocolError("Report data length does not match body")
    return body[length_offset + 1:]


def parse_message(
    body: bytes, *, j1587_extended: bool | None = None
) -> AdapterMessage | PgnReport | J1587Report | ObdReport:
    """Parse a checksum-verified receive body without guessing firmware.

    PIDData requires an explicit firmware format: pre-3.19 uses a big-endian
    16-bit PID; 3.19+ uses up to three 0xFF page-extension bytes. Unknown
    commands are preserved, not decoded as CAN or treated as online.
    """
    if not isinstance(body, bytes) or not 1 <= len(body) <= MAX_BODY_SIZE:
        raise ProtocolError("Expected a nonempty bounded message body")
    command = body[0]
    if command == PGN_DATA:
        data = _report_data(body, 6)
        return PgnReport(
            body[1], int.from_bytes(body[2:4], "big"),
            body[4], body[5], data,
        )
    if command == PID_DATA:
        if j1587_extended is None:
            raise ProtocolError("Select a J1587 firmware format explicitly")
        if not j1587_extended:
            data = _report_data(body, 4)
            pid = int.from_bytes(body[2:4], "big")
        else:
            offset = 2
            extensions = 0
            while offset < len(body) and body[offset] == 255:
                extensions += 1
                offset += 1
                if extensions > 3:
                    raise ProtocolError("J1587 PID exceeds three extensions")
            if offset >= len(body):
                raise ProtocolError("Truncated J1587 PID")
            pid = extensions * 256 + body[offset]
            data = _report_data(body, offset + 1)
        if pid > 1023:
            raise ProtocolError("J1587 PID outside supported range")
        # The vendor's component-identification value can include its MID.
        # Remove only that wrapper, not bytes from normalized/raw J1587.
        if (
            pid == 243 and data and data[0] >= 128
            and data != b"\xff" * len(data)
        ):
            if data[0] != body[1]:
                raise ProtocolError("Component identification MID mismatch")
            data = data[1:]
        return J1587Report(body[1], pid, data)
    if command == OBD_DATA:
        data = _report_data(body, 6)
        return ObdReport(
            int.from_bytes(body[1:3], "big"), body[3],
            int.from_bytes(body[4:6], "big"), data,
        )
    return AdapterMessage(command, body[1:])
