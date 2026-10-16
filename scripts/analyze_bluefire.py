"""Analyze local adapter-to-client hex chunks; never connect or transmit."""

import argparse
from collections.abc import Iterator
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.bluefire.catalog import (  # noqa: E402
    CATALOG_VERSION, lookup, source_name,
)
from custom_components.bluefire.faults import (  # noqa: E402
    decode_diagnostics,
)
from custom_components.bluefire.j1587 import (  # noqa: E402
    decode_report, parse_j1708_message,
)
from custom_components.bluefire.protocol import (  # noqa: E402
    AdapterMessage,
    J1587Report,
    ObdReport,
    PgnReport,
    ProtocolError,
    ReceiveDecoder,
    parse_message,
)
from custom_components.bluefire.signals import SIGNALS  # noqa: E402


def analyze_capture(
    capture: TextIO, *, padded_notifications: bool,
    j1587_extended: bool | None = None,
) -> Iterator[dict]:
    """Yield JSON-ready records; each line is one chunk/notification."""
    decoder = ReceiveDecoder(padded_notifications=padded_notifications)
    line_number = 0
    while line := capture.readline(4097):
        line_number += 1
        try:
            if len(line) > 4096:
                raise ProtocolError("Hex input line exceeds 4096 characters")
            if not line.strip():
                continue
            try:
                chunk = bytes.fromhex(line)
            except ValueError as err:
                raise ProtocolError("Expected a hexadecimal receive chunk") \
                    from err
            for body in decoder.feed(chunk):
                report = parse_message(body, j1587_extended=j1587_extended)
                record = asdict(report)
                record["data"] = report.data.hex()
                record["command"] = body[0]
                record["command_name"] = lookup("command", body[0])["name"]
                record["catalog_version"] = CATALOG_VERSION
                record["line"] = line_number
                record["hardware_verified"] = False
                if isinstance(report, PgnReport):
                    record["kind"] = "pgn_report"
                    record["source_name"] = source_name(report.source_address)
                    record["pgn_name"] = (
                        lookup("pgn", report.pgn)["name"]
                        if report.data_page == 0 else
                        "Unmapped nonzero-data-page parameter group"
                    )
                    record["signals"] = [
                        {
                            **signal.metadata(),
                            "value": signal.decode(report.data),
                        }
                        for signal in SIGNALS
                        if signal.pgn == report.pgn
                        and report.data_page == 0 and len(report.data) == 8
                    ]
                    if (
                        report.pgn in (65226, 65227)
                        and report.data_page == 0
                    ):
                        try:
                            record["diagnostics"] = decode_diagnostics(
                                report.pgn, report.data,
                                source=report.source_address,
                            )
                        except ValueError as err:
                            raise ProtocolError(str(err)) from err
                elif isinstance(report, J1587Report):
                    record["kind"] = "j1587_report"
                    record["source_name"] = source_name(
                        report.mid, j1587=True
                    )
                    record["parameter"] = lookup("pid", report.pid)
                    try:
                        record.update(decode_report(report))
                    except ValueError as err:
                        raise ProtocolError(str(err)) from err
                elif isinstance(report, ObdReport):
                    record["kind"] = "obd_report"
                    record["parameter"] = lookup(
                        "obd_pid", f"{report.mode:02X}:{report.pid:02X}"
                    ) if report.pid <= 255 else {
                        "known": False, "name": "Unmapped extended OBD PID",
                        "unit": None,
                    }
                    record["value_decoded"] = False
                elif isinstance(report, AdapterMessage):
                    record["kind"] = "adapter_message"
                yield record
        except ProtocolError as err:
            raise ProtocolError(f"Line {line_number}: {err}") from err
    decoder.finish()


def analyze_j1708(capture: TextIO) -> Iterator[dict]:
    """One complete, checksummed J1708 datagram per line, not BLE chunks."""
    line_number = 0
    while line := capture.readline(129):
        line_number += 1
        try:
            if len(line) > 128:
                raise ValueError("J1708 input line exceeds 128 characters")
            if not line.strip():
                continue
            message = parse_j1708_message(bytes.fromhex(line))
            # Decode before yielding so malformed datagrams emit no partials.
            parameters = [
                {**asdict(report), "data": report.data.hex(),
                 **decode_report(report)}
                for report in message.reports
            ]
            yield {
                "kind": "j1708_message", "line": line_number,
                "protocol": "j1587" if message.mid >= 128 else "j1708",
                "mid": message.mid, "data": message.data.hex(),
                "hardware_verified": False, "parameters": parameters,
                "source_name": (
                    source_name(message.mid, j1587=True)
                    if message.mid >= 128 else "Unmapped J1708 controller"
                ),
            }
        except ValueError as err:
            raise ProtocolError(f"Line {line_number}: {err}") from err


def main(argv: list[str] | None = None) -> int:
    """Print local analysis JSONL; return nonzero on any rejected input."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "capture", type=Path,
        help="ASCII receive hex or Adapter.txt, one ordered chunk per line",
    )
    parser.add_argument(
        "--transport", choices=("stream", "padded", "j1708"), required=True,
        help="Vendor stream/padded chunks or complete J1708 datagrams",
    )
    parser.add_argument(
        "--j1587-format", choices=("legacy", "extended"),
        help="Required for PIDData: firmware before 3.19 or 3.19+",
    )
    args = parser.parse_args(argv)
    if args.transport == "j1708" and args.j1587_format is not None:
        parser.error("--j1587-format applies only to vendor PIDData")
    extended = None
    if args.j1587_format is not None:
        extended = args.j1587_format == "extended"
    try:
        with args.capture.open(encoding="ascii") as capture:
            records = (
                analyze_j1708(capture) if args.transport == "j1708" else
                analyze_capture(
                    capture, padded_notifications=args.transport == "padded",
                    j1587_extended=extended,
                )
            )
            for record in records:
                print(json.dumps(record, allow_nan=False))
    except (OSError, UnicodeError, ProtocolError) as err:
        print(f"Analysis failed: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
