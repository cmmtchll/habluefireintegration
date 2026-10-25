"""Read-only J1708 datagrams and normalized J1587 parameter values.

Datagram boundaries must come from the capture/driver, never a checksum scan.
J1587Report.data excludes PID and variable-parameter byte-count fields.
"""

from dataclasses import asdict, dataclass

from .catalog import describe_fault, lookup
from .protocol import J1587Report


@dataclass(frozen=True)
class Parameter:
    """An independently defined J1587 PID, not a J1939 SPN layout."""

    pid: int
    length: int
    resolution: float
    offset: float
    unit: str
    device_class: str | None = None
    state_class: str = "measurement"
    signed: bool = False

    @property
    def name(self) -> str:
        return lookup("pid", self.pid)["name"]

    @property
    def spn(self) -> int:
        """Internal discovery ledger key only; wire output always uses PID."""
        return self.pid

    def decode(self, data: bytes) -> float | None:
        if not isinstance(data, bytes) or len(data) != self.length:
            raise ValueError("J1587 parameter value length does not match PID")
        if data == b"\xff" * self.length:
            return None
        raw = int.from_bytes(data, "little", signed=self.signed)
        return round(raw * self.resolution + self.offset, 6)

    def metadata(self) -> dict:
        return {
            "pid": self.pid, "name": self.name, "unit": self.unit,
            "description": (
                f"{self.name}, converted from J1587 units to {self.unit}. "
                "An all-ones unavailable value is reported as null."
            ),
        }


# Native J1587 units include mph, psi, Fahrenheit and US gallons.
_MILE_KM = 1.609344
_PSI_KPA = 6.894757293168
_GALLON_LITRES = 3.785411784
PARAMETERS = (
    Parameter(26, 1, 0.5, 0, "%"),
    Parameter(51, 1, 0.4, 0, "%"),
    Parameter(68, 1, 0.5, 0, "%"),
    Parameter(74, 1, 0.5 * _MILE_KM, 0, "km/h", "speed"),
    Parameter(84, 1, 0.5 * _MILE_KM, 0, "km/h", "speed"),
    Parameter(86, 1, 0.5 * _MILE_KM, 0, "km/h", "speed"),
    Parameter(91, 1, 0.4, 0, "%"),
    Parameter(92, 1, 0.5, 0, "%"),
    Parameter(94, 1, 0.5 * _PSI_KPA, 0, "kPa", "pressure"),
    Parameter(96, 1, 0.5, 0, "%"),
    Parameter(100, 1, 0.5 * _PSI_KPA, 0, "kPa", "pressure"),
    Parameter(101, 1, _PSI_KPA / 8, 0, "kPa", "pressure", signed=True),
    Parameter(102, 1, _PSI_KPA / 8, 0, "kPa", "pressure"),
    Parameter(105, 1, 5 / 9, -32 * 5 / 9, "°C", "temperature"),
    Parameter(108, 1, _PSI_KPA / 16, 0, "kPa", "pressure"),
    Parameter(109, 1, _PSI_KPA / 8, 0, "kPa", "pressure"),
    Parameter(110, 1, 5 / 9, -32 * 5 / 9, "°C", "temperature"),
    Parameter(111, 1, 0.5, 0, "%"),
    Parameter(116, 1, 0.6 * _PSI_KPA, 0, "kPa", "pressure"),
    Parameter(117, 1, 0.6 * _PSI_KPA, 0, "kPa", "pressure"),
    Parameter(118, 1, 0.6 * _PSI_KPA, 0, "kPa", "pressure"),
    Parameter(120, 1, 10 / 9, -32 * 5 / 9, "°C", "temperature"),
    Parameter(122, 1, 0.5, 0, "%"),
    Parameter(168, 2, 0.05, 0, "V", "voltage"),
    Parameter(171, 2, 5 / 36, -32 * 5 / 9, "°C", "temperature"),
    Parameter(172, 2, 5 / 36, -32 * 5 / 9, "°C", "temperature"),
    Parameter(173, 2, 5 / 36, -32 * 5 / 9, "°C", "temperature"),
    Parameter(175, 2, 5 / 36, -32 * 5 / 9, "°C", "temperature"),
    Parameter(177, 2, 5 / 36, -32 * 5 / 9, "°C", "temperature"),
    Parameter(183, 2, _GALLON_LITRES / 64, 0, "L/h", "volume_flow_rate"),
    Parameter(184, 2, _MILE_KM / _GALLON_LITRES / 256, 0, "km/L"),
    Parameter(185, 2, _MILE_KM / _GALLON_LITRES / 256, 0, "km/L"),
    Parameter(190, 2, 0.25, 0, "rpm"),
    Parameter(235, 4, 0.05, 0, "h", "duration", "total_increasing"),
    Parameter(236, 4, _GALLON_LITRES / 8, 0, "L",
              "volume", "total_increasing"),
    Parameter(245, 4, _MILE_KM / 10, 0, "km",
              "distance", "total_increasing"),
    Parameter(247, 4, 0.05, 0, "h", "duration", "total_increasing"),
    Parameter(250, 4, _GALLON_LITRES / 8, 0, "L",
              "volume", "total_increasing"),
    Parameter(439, 2, 0.125, 0, "kPa", "pressure"),
)


@dataclass(frozen=True)
class StatusParameter:
    """Unitless switch fields or two-character gear text, not magnitudes."""

    pid: int
    kind: str

    @property
    def name(self) -> str:
        return lookup("pid", self.pid)["name"]

    @property
    def spn(self) -> int:
        return self.pid

    @property
    def length(self) -> int:
        return 2 if self.kind == "gear" else 1

    def decode(self, data: bytes) -> dict:
        if not isinstance(data, bytes) or len(data) != self.length:
            raise ValueError("J1587 status value length does not match PID")
        value = None
        status = "unavailable"
        switches = {}
        if data != b"\xff" * self.length:
            status = "decoded"
            if self.kind == "gear":
                if all(32 <= byte <= 126 for byte in data):
                    value = data.decode("ascii").strip() or None
                    if value is None:
                        status = "unavailable"
                else:
                    status = "unsupported_encoding"
            elif self.kind == "cruise":
                switches = {
                    label: bool(data[0] & (1 << bit))
                    for bit, label in enumerate((
                        "enabled", "set", "coast", "resume", "accelerate",
                        "brake", "clutch", "active",
                    ))
                }
                value = "Active" if switches["active"] else "Inactive"
            else:
                value = "On" if data[0] & 1 else "Off"
        return {
            "pid": self.pid, "name": self.name,
            "description": (
                f"{self.name}, reported as J1587 {self.kind} data; "
                "not a command or safety assessment."
            ),
            "value": value, "data": data.hex(), "decode_status": status,
            **({"switches": switches} if self.kind == "cruise" else {}),
        }


STATUS_PARAMETERS = (
    StatusParameter(40, "switch"), StatusParameter(70, "switch"),
    StatusParameter(85, "cruise"), StatusParameter(162, "gear"),
    StatusParameter(163, "gear"),
)


@dataclass(frozen=True)
class DiagnosticParameter:
    pid: int = 194
    name: str = "Diagnostic faults"

    @property
    def spn(self) -> int:
        return self.pid


@dataclass(frozen=True)
class IdentificationParameter:
    """Controller-reported text, not an inferred hardware/control profile."""

    pid: int

    @property
    def name(self) -> str:
        return lookup("pid", self.pid)["name"]

    @property
    def spn(self) -> int:
        return self.pid

    def decode(self, data: bytes) -> dict:
        status = "decoded"
        value = None
        if not data or data == b"\xff" * len(data):
            status = "unavailable"
        elif not all(32 <= byte <= 126 for byte in data):
            status = "unsupported_encoding"
        else:
            value = data.decode("ascii").strip()
            if not value:
                status = "unavailable"
                value = None
        return {
            "pid": self.pid, "name": self.name,
            "description": (
                "Controller-reported identification text; not independently "
                "verified and not used to select an ECU diagnostic profile."
            ),
            "value": value, "decode_status": status, "data": data.hex(),
            "identity_basis": "controller_reported",
        }


IDENTIFICATION_PARAMETERS = tuple(
    IdentificationParameter(pid) for pid in (234, 237, 243)
)
ENTITIES = (
    PARAMETERS + STATUS_PARAMETERS + (DiagnosticParameter(),)
    + IDENTIFICATION_PARAMETERS
)
# PID 174 is a documented engine sensor but its scaling is not established
# by the inspected BlueFire implementation. Explicit reads retain raw bytes.
READABLE_PIDS = tuple(p.pid for p in ENTITIES) + (174,)


def validate_report(report: J1587Report) -> None:
    """Reject malformed envelopes before any MQTT side effects."""
    if not isinstance(report, J1587Report):
        raise ValueError("Expected a normalized J1587Report")
    if type(report.mid) is not int or not 128 <= report.mid <= 255:
        raise ValueError("Expected a J1587 MID in 128..255")
    if type(report.pid) is not int or not 0 <= report.pid <= 1023:
        raise ValueError("J1587 PID outside supported range")
    if not isinstance(report.data, bytes) or len(report.data) > 255:
        raise ValueError("Expected bounded immutable J1587 value bytes")
    low = report.pid % 256
    length = 1 if low < 128 else 2
    if low < 192 and len(report.data) != length:
        raise ValueError("J1587 fixed-width PID has incorrect value length")


def decode_faults(
    data: bytes, *, mid: int, profile: str | None = None,
) -> dict:
    """PID 194 entries without the outer variable-parameter length byte.

    Each entry is code, flags/FMI and optional occurrence count.
    Bit 5 clear expands the PID/SID by 256; bit 6 marks inactive faults.
    An empty list clears the reported list, not every ECU on the vehicle.
    """
    validate_report(J1587Report(mid, 194, data))
    # Validate even when the list is empty.
    lookup("pid", 194, profile=profile)
    faults = []
    index = 0
    while index < len(data):
        if len(data) - index < 2:
            raise ValueError("Truncated J1587 diagnostic entry")
        start = index
        code, flags = data[index:index + 2]
        index += 2
        occurrence = None
        if flags & 0x80:
            if index == len(data):
                raise ValueError("Missing J1587 diagnostic occurrence count")
            occurrence = data[index]
            index += 1
        expanded = not bool(flags & 0x20)
        code += 256 if expanded else 0
        faults.append({
            **describe_fault(
                "sid" if flags & 0x10 else "pid", code, flags & 15,
                source=mid, profile=profile,
            ),
            "active": not bool(flags & 0x40), "expanded": expanded,
            "occurrence_count": occurrence,
            "raw": data[start:index].hex(),
        })
    active = sum(fault["active"] for fault in faults)
    return {
        "name": "Diagnostic faults", "decode_status": "decoded",
        "description": (
            "J1587 diagnostic entries reported by this MID only; "
            "not a vehicle-wide health or safety assessment."
        ),
        "summary": (
            f"{active} active, {len(faults) - active} inactive faults"
            if faults else "No faults in this report"
        ),
        "fault_count": len(faults), "active_fault_count": active,
        "inactive_fault_count": len(faults) - active, "faults": faults,
    }


def decode_report(
    report: J1587Report, *, profile: str | None = None,
) -> dict:
    """Decode only known complete values, preserving unknown PIDs as raw."""
    validate_report(report)
    parameter = lookup("pid", report.pid, profile=profile)
    if report.pid == 194:
        return {
            "value_decoded": True,
            "diagnostics": decode_faults(
                report.data, mid=report.mid, profile=profile
            ),
        }
    identification = next(
        (p for p in IDENTIFICATION_PARAMETERS if p.pid == report.pid), None
    )
    if identification is not None:
        value = identification.decode(report.data)
        return {
            "parameter": parameter,
            "value_decoded": value["decode_status"] == "decoded",
            "identification": value,
        }
    status = next((p for p in STATUS_PARAMETERS if p.pid == report.pid), None)
    if status is not None:
        value = status.decode(report.data)
        return {
            "parameter": parameter,
            "value_decoded": value["decode_status"] == "decoded",
            "signals": [value],
        }
    signal = next((p for p in PARAMETERS if p.pid == report.pid), None)
    return {
        "parameter": parameter, "value_decoded": signal is not None,
        "signals": (
            [{**signal.metadata(), "value": signal.decode(report.data)}]
            if signal else []
        ),
    }


@dataclass(frozen=True)
class J1708Message:
    """A checksummed datagram, possibly an opaque non-J1587 message."""

    mid: int
    data: bytes
    reports: tuple[J1587Report, ...]


def parse_j1708_message(message: bytes) -> J1708Message:
    """Validate one 2..21-byte datagram including checksum; never transmit.

    Non-J1587 MIDs stay opaque. PID 254 special/proprietary framing is
    deliberately rejected; multisection PID 192 remains opaque parameter data.
    """
    if not isinstance(message, bytes) or not 2 <= len(message) <= 21:
        raise ValueError("Expected one complete 2..21-byte J1708 datagram")
    if sum(message) & 255:
        raise ValueError("J1708 checksum mismatch")
    mid, data = message[0], message[1:-1]
    reports = []
    if mid < 128:
        return J1708Message(mid, data, ())
    if not data:
        raise ValueError("J1587 datagram contains no parameters")
    offset, page = 0, 0
    while offset < len(data) and data[offset] == 255:
        page += 256
        offset += 1
        if page > 768:
            raise ValueError("Too many J1587 page extensions")
    if offset == len(data):
        raise ValueError("J1587 page extension has no PID")
    while offset < len(data):
        low_pid = data[offset]
        offset += 1
        if low_pid >= 254:
            raise ValueError("Unsupported special J1587 PID framing")
        pid = page + low_pid
        length = 1 if low_pid < 128 else 2
        if low_pid >= 192:
            if offset == len(data):
                raise ValueError("Missing J1587 variable parameter length")
            length = data[offset]
            offset += 1
        if offset + length > len(data):
            raise ValueError("Truncated J1587 parameter")
        reports.append(J1587Report(mid, pid, data[offset:offset + length]))
        offset += length
    return J1708Message(mid, data, tuple(reports))


def export_parameters() -> list[dict]:
    """Expose independent layouts and conversions for dictionary consumers."""
    return [{**asdict(p), **p.metadata()} for p in PARAMETERS]
