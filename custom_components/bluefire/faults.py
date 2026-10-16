"""Read-only DM1/DM2 interpretation after complete payload reassembly."""

from dataclasses import dataclass

from .catalog import LAMP_FLASH, LAMP_STATUS, describe_fault


@dataclass(frozen=True)
class Diagnostic:
    """Discovery ownership uses negative PGNs, disjoint from positive SPNs."""

    pgn: int
    name: str

    @property
    def spn(self) -> int:
        return -self.pgn


DIAGNOSTICS = (
    Diagnostic(65226, "Active faults"),
    Diagnostic(65227, "Previously active faults"),
)


def decode_diagnostics(pgn: int, data: bytes, *, source: int) -> dict:
    """Decode standard conversion-method-zero DTCs; do not guess legacy SPNs.

    Single-frame payloads have two FF filler bytes. Longer payloads must
    already be reassembled; this function does not implement J1939 TP.
    """
    if pgn not in (65226, 65227):
        raise ValueError("Expected DM1 or DM2 PGN")
    if type(source) is not int or not 0 <= source <= 255:
        raise ValueError("Expected a diagnostic source address byte")
    if not isinstance(data, bytes) or len(data) < 6:
        raise ValueError("Incomplete diagnostic payload")
    if len(data) == 8:
        if data[6:] != b"\xff\xff":
            raise ValueError("Invalid diagnostic filler bytes")
        body = data[2:6]
    elif (len(data) - 2) % 4 == 0:
        body = data[2:]
    else:
        raise ValueError("Incomplete diagnostic trouble code")
    lamps = {}
    for name, shift in (
        ("malfunction", 6), ("red_stop", 4), ("amber_warning", 2),
        ("protect", 0),
    ):
        state, flash = (data[0] >> shift) & 3, (data[1] >> shift) & 3
        lamps[name] = {
            "status_code": state, "status": LAMP_STATUS[state],
            "flash_code": flash, "flash": LAMP_FLASH[flash],
        }
    faults = []
    unavailable = False
    unsupported = False
    for index in range(0, len(body), 4):
        dtc = body[index:index + 4]
        if dtc == bytes(4):
            if len(body) != 4:
                raise ValueError("No-fault marker mixed with diagnostic codes")
            continue
        if dtc == b"\xff" * 4:
            if len(body) != 4:
                raise ValueError("Unavailable marker mixed with fault codes")
            unavailable = True
            continue
        occurrence = dtc[3] & 0x7F
        conversion = dtc[3] >> 7
        if conversion:
            unsupported = True
            fault = {
                "spn": None, "fmi": dtc[2] & 31, "known": False,
                "name": "Unresolved legacy diagnostic code",
                "description": (
                    "Legacy SPN conversion needs controller-specific "
                    "information; no SPN has been inferred."
                ),
            }
        else:
            spn = dtc[0] | (dtc[1] << 8) | ((dtc[2] & 0xE0) << 11)
            fault = {
                **describe_fault("spn", spn, dtc[2] & 31, source=source),
                "spn": spn,
            }
        faults.append({
            **fault, "raw": dtc.hex(), "conversion_method": conversion,
            "occurrence_count": None if occurrence == 127 else occurrence,
        })
    status = (
        "unavailable" if unavailable else
        "unsupported_conversion" if unsupported else "decoded"
    )
    summary = (
        "Diagnostics unavailable" if unavailable else
        faults[0]["description"] if len(faults) == 1 else
        f"{len(faults)} faults reported" if faults else
        "No active faults" if pgn == 65226 else "No previously active faults"
    )
    return {
        "name": (
            "Active faults" if pgn == 65226 else "Previously active faults"
        ),
        "description": (
            "Controller diagnostic report, not a measurement or repair "
            "instruction. Lamp status is shared by the complete report."
        ),
        "summary": summary, "decode_status": status,
        "fault_count": None if unavailable else len(faults),
        "faults": faults, "lamps": lamps,
    }
