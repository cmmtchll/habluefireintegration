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

from custom_components.bluefire.protocol import (  # noqa: E402
    AdapterMessage,
    J1587Report,
    ObdReport,
    PgnReport,
    ProtocolError,
    ReceiveDecoder,
    parse_message,
)
from custom_components.bluefire.telemetry import SIGNALS  # noqa: E402


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
                record["line"] = line_number
                record["hardware_verified"] = False
                if isinstance(report, PgnReport):
                    record["kind"] = "pgn_report"
                    record["signals"] = [
                        {
                            "spn": signal.spn,
                            "value": signal.decode(report.data),
                            "unit": signal.unit,
                        }
                        for signal in SIGNALS
                        if signal.pgn == report.pgn
                        and report.data_page == 0 and len(report.data) == 8
                    ]
                elif isinstance(report, J1587Report):
                    record["kind"] = "j1587_report"
                elif isinstance(report, ObdReport):
                    record["kind"] = "obd_report"
                elif isinstance(report, AdapterMessage):
                    record["kind"] = "adapter_message"
                yield record
        except ProtocolError as err:
            raise ProtocolError(f"Line {line_number}: {err}") from err
    decoder.finish()


def main(argv: list[str] | None = None) -> int:
    """Print local analysis JSONL; return nonzero on any rejected input."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "capture", type=Path,
        help="ASCII receive hex or Adapter.txt, one ordered chunk per line",
    )
    parser.add_argument(
        "--transport", choices=("stream", "padded"), required=True,
        help="Unpadded byte stream or legacy zero-padded BLE notifications",
    )
    parser.add_argument(
        "--j1587-format", choices=("legacy", "extended"),
        help="Required for PIDData: firmware before 3.19 or 3.19+",
    )
    args = parser.parse_args(argv)
    extended = None
    if args.j1587_format is not None:
        extended = args.j1587_format == "extended"
    try:
        with args.capture.open(encoding="ascii") as capture:
            for record in analyze_capture(
                capture, padded_notifications=args.transport == "padded",
                j1587_extended=extended,
            ):
                print(json.dumps(record, allow_nan=False))
    except (OSError, UnicodeError, ProtocolError) as err:
        print(f"Analysis failed: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
