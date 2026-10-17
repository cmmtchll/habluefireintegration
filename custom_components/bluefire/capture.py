"""Offline analysis of raw BLE notifications from a user-requested capture.

Notification framing is hardware-unverified, so each characteristic is
decoded independently in both stream and padded-notification modes. Results
are evidence for protocol work; nothing here publishes vehicle telemetry.
"""

from collections import Counter
from dataclasses import asdict

from .catalog import lookup
from .protocol import (
    PID_DATA,
    AdapterMessage,
    J1587Report,
    ObdReport,
    PgnReport,
    ProtocolError,
    ReceiveDecoder,
    parse_message,
)

HEARTBEAT = 255
SAMPLE_LIMIT = 25
MODES = (("stream", False), ("padded", True))


def _hex(record) -> dict:
    return {
        key: value.hex() if isinstance(value, bytes) else value
        for key, value in asdict(record).items()
    }


def _parse(body: bytes):
    """Parse one body; J1587 is tried in both firmware formats."""
    if body[0] != PID_DATA:
        return parse_message(body), None
    results = {}
    for name, extended in (("legacy", False), ("extended", True)):
        try:
            results[name] = parse_message(body, j1587_extended=extended)
        except ProtocolError as err:
            results[name] = err
    valid = [name for name, item in results.items()
             if not isinstance(item, ProtocolError)]
    if not valid:
        raise results["extended"]
    return results[valid[-1]], valid


def _framing_summary(notifications: list[dict], padded: bool) -> dict:
    decoder = ReceiveDecoder(padded_notifications=padded)
    framing_errors: Counter[str] = Counter()
    parse_errors: Counter[str] = Counter()
    commands: Counter[int] = Counter()
    pgns: Counter[int] = Counter()
    pgn_sources: dict[int, set[int]] = {}
    j1587: Counter[str] = Counter()
    j1587_formats: Counter[str] = Counter()
    obd: Counter[str] = Counter()
    unknown_commands = 0
    unrecognized_pgns = 0
    heartbeats = 0
    packets = 0
    samples = []
    for notification in notifications:
        try:
            bodies = decoder.feed(notification["data"])
        except ProtocolError as err:
            framing_errors[str(err)] += 1
            continue
        for body in bodies:
            commands[body[0]] += 1
            try:
                record, formats = _parse(body)
            except ProtocolError as err:
                parse_errors[str(err)] += 1
                continue
            packets += 1
            for name in formats or ():
                j1587_formats[name] += 1
            if isinstance(record, PgnReport):
                pgns[record.pgn] += 1
                pgn_sources.setdefault(record.pgn, set()).add(
                    record.source_address
                )
                if not lookup("pgn", record.pgn)["known"]:
                    unrecognized_pgns += 1
            elif isinstance(record, J1587Report):
                j1587[f"{record.mid}:{record.pid}"] += 1
            elif isinstance(record, ObdReport):
                obd[f"{record.source}:{record.mode}:{record.pid}"] += 1
            elif record.command == HEARTBEAT:
                heartbeats += 1
            elif not lookup("command", record.command)["known"]:
                unknown_commands += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append({
                    "t": notification["t"],
                    "kind": type(record).__name__,
                    "body": body.hex(),
                    **_hex(record),
                })
    attempts = packets + sum(parse_errors.values()) + sum(
        framing_errors.values()
    )
    return {
        "packets": packets,
        "framing_errors": sum(framing_errors.values()),
        "framing_error_messages": dict(framing_errors),
        "parse_errors": sum(parse_errors.values()),
        "parse_error_messages": dict(parse_errors),
        "decode_success_rate": (
            round(packets * 100 / attempts, 1) if attempts else None
        ),
        "pending_bytes_at_end": decoder.pending_bytes,
        "heartbeats": heartbeats,
        "unknown_commands": unknown_commands,
        "unrecognized_pgns": unrecognized_pgns,
        "commands": {
            str(command): {
                "count": count, "name": lookup("command", command)["name"],
            }
            for command, count in sorted(commands.items())
        },
        "pgns": {
            str(pgn): {
                "count": count,
                "name": lookup("pgn", pgn)["name"],
                "known": lookup("pgn", pgn)["known"],
                "sources": sorted(pgn_sources[pgn]),
            }
            for pgn, count in sorted(pgns.items())
        },
        "j1587_mid_pid": dict(sorted(j1587.items())),
        "j1587_formats_accepted": dict(j1587_formats),
        "obd_source_mode_pid": dict(sorted(obd.items())),
        "pgn_reports": sum(pgns.values()),
        "j1587_reports": sum(j1587.values()),
        "obd_reports": sum(obd.values()),
        "samples": samples,
    }


def _timing(notifications: list[dict]) -> dict:
    times = [item["t"] for item in notifications]
    lengths = [len(item["data"]) for item in notifications]
    gaps = [later - earlier for earlier, later in zip(times, times[1:])]
    span = times[-1] - times[0] if times else 0
    return {
        "notifications": len(notifications),
        "bytes": sum(lengths),
        "first_t": times[0] if times else None,
        "last_t": times[-1] if times else None,
        "min_length": min(lengths, default=None),
        "max_length": max(lengths, default=None),
        "length_histogram": {
            str(length): count
            for length, count in Counter(lengths).most_common(10)
        },
        "mean_interval_s": (
            round(sum(gaps) / len(gaps), 4) if gaps else None
        ),
        "max_gap_s": round(max(gaps), 4) if gaps else None,
        "rate_per_s": round(len(times) / span, 2) if span else None,
        "zero_filled": sum(1 for item in notifications if not any(
            item["data"]
        )),
    }


def analyze_notifications(notifications: list[dict]) -> dict:
    """Summarize timing, framing and parse results per characteristic."""
    by_characteristic: dict[str, list[dict]] = {}
    for item in notifications:
        key = f"{item['characteristic']}#{item['handle']}"
        by_characteristic.setdefault(key, []).append(item)
    characteristics = {}
    totals = {mode: Counter() for mode, _ in MODES}
    numeric = (
        "packets", "framing_errors", "parse_errors", "heartbeats",
        "unknown_commands", "unrecognized_pgns", "pgn_reports",
        "j1587_reports", "obd_reports",
    )
    for key, items in by_characteristic.items():
        framing = {
            mode: _framing_summary(items, padded) for mode, padded in MODES
        }
        for mode, summary in framing.items():
            totals[mode].update({name: summary[name] for name in numeric})
        characteristics[key] = {"timing": _timing(items), "framing": framing}
    # Prefer the framing mode that explains the data with fewer errors.
    selected = min(
        (mode for mode, _ in MODES),
        key=lambda mode: (
            totals[mode]["framing_errors"] + totals[mode]["parse_errors"],
            -totals[mode]["packets"],
        ),
    )
    return {
        "timing": _timing(notifications),
        "selected_framing": selected,
        "totals": {
            mode: {name: totals[mode][name] for name in numeric}
            for mode, _ in MODES
        },
        "characteristics": characteristics,
    }


def serialize_notifications(notifications: list[dict]) -> list[dict]:
    """Raw capture rows: relative time, characteristic and payload hex."""
    return [
        {
            "t": item["t"],
            "characteristic": item["characteristic"],
            "handle": item["handle"],
            "length": len(item["data"]),
            "hex": item["data"].hex(),
        }
        for item in notifications
    ]


def record_capture(health, analysis: dict, *, notify: bool = True) -> None:
    """Fold the selected framing mode's totals into the entry counters."""
    totals = analysis["totals"][analysis["selected_framing"]]
    timing = analysis["timing"]
    health.count("notifications", timing["notifications"])
    health.count("bytes", timing["bytes"])
    for name in (
        "packets", "heartbeats", "unknown_commands", "unrecognized_pgns",
        "pgn_reports", "j1587_reports", "obd_reports",
    ):
        health.count(name, totals[name])
    selected = analysis["selected_framing"]
    for characteristic in analysis["characteristics"].values():
        summary = characteristic["framing"][selected]
        for kind in ("framing_errors", "parse_errors"):
            messages = summary[kind.replace("errors", "error_messages")]
            for message, count in messages.items():
                health.error(kind, message, amount=count, notify=False)
    if timing["notifications"]:
        health.data_seen()
    health.capture_completed({
        "selected_framing": selected, **timing, **totals,
    }, notify=notify)
