"""Per-entry receive-quality counters shared by captures and diagnostics.

Pure Python so a future live receiver can feed the same counters. Counters
reset on Home Assistant restart; sensors use total_increasing semantics.
"""

from collections import Counter, deque
from collections.abc import Callable
from datetime import datetime, timezone

COUNTERS = (
    "notifications",
    "bytes",
    "packets",
    "framing_errors",
    "parse_errors",
    "unknown_commands",
    "unrecognized_pgns",
    "heartbeats",
    "pgn_reports",
    "j1587_reports",
    "obd_reports",
    "mqtt_published",
    "mqtt_errors",
    "connection_errors",
    "advertisements",
    "captures",
)
ERROR_COUNTERS = (
    "framing_errors", "parse_errors", "mqtt_errors", "connection_errors",
)
RSSI_HISTORY = 120
ERROR_HISTORY = 50
ERROR_MESSAGES = 100


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Health:
    """Tallies, last-seen times, RSSI history and recent errors."""

    def __init__(self, clock: Callable[[], datetime] = utcnow) -> None:
        self._clock = clock
        self.counters = dict.fromkeys(COUNTERS, 0)
        self.error_messages: Counter[str] = Counter()
        self.recent_errors: deque[dict] = deque(maxlen=ERROR_HISTORY)
        self.rssi_history: deque[dict] = deque(maxlen=RSSI_HISTORY)
        self.started = clock()
        self.last_data: datetime | None = None
        self.last_advertisement: datetime | None = None
        self.last_capture: datetime | None = None
        self.last_capture_summary: dict | None = None
        self.last_error: str | None = None
        self.last_error_at: datetime | None = None
        self.rssi: int | None = None
        self.source: str | None = None
        self.present: bool | None = None
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Notify on significant events; routine counts are polled."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def count(self, name: str, amount: int = 1) -> None:
        self.counters[name] += amount

    def error(
        self, name: str, message: str, *, amount: int = 1,
        notify: bool = True,
    ) -> None:
        """Record an error class/message without raising."""
        self.counters[name] += amount
        key = f"{name}: {message}"
        if (
            key not in self.error_messages
            and len(self.error_messages) >= ERROR_MESSAGES
        ):
            # Bound memory; the counters and recent_errors stay exact.
            self.error_messages[f"{name}: (other messages)"] += amount
        else:
            self.error_messages[key] += amount
        now = self._clock()
        self.last_error = key
        self.last_error_at = now
        self.recent_errors.append({
            "time": now.isoformat(), "kind": name, "message": message,
            "count": amount,
        })
        if notify:
            self.notify()

    def data_seen(self) -> None:
        self.last_data = self._clock()

    def advertisement(self, rssi: int | None, source: str | None) -> None:
        """Track passive advertisements; never connects to the adapter."""
        now = self._clock()
        changed = self.present is not True
        self.counters["advertisements"] += 1
        self.last_advertisement = now
        self.rssi = rssi
        self.source = source
        self.present = True
        self.rssi_history.append({
            "time": now.isoformat(), "rssi": rssi, "source": source,
        })
        if changed:
            self.notify()

    def capture_completed(self, summary: dict, *, notify: bool = True) -> None:
        self.counters["captures"] += 1
        self.last_capture = self._clock()
        self.last_capture_summary = summary
        if notify:
            self.notify()

    def unavailable(self) -> None:
        """HA's Bluetooth stack no longer sees advertisements."""
        self.present = False
        self.rssi = None
        self.notify()

    @property
    def unrecognized(self) -> int:
        return (
            self.counters["unknown_commands"]
            + self.counters["unrecognized_pgns"]
        )

    @property
    def decode_success_rate(self) -> float | None:
        """Percentage of framed packets that decoded without an error."""
        good = self.counters["packets"]
        total = (
            good + self.counters["framing_errors"]
            + self.counters["parse_errors"]
        )
        return round(good * 100 / total, 1) if total else None

    def rssi_statistics(self) -> dict | None:
        values = [
            item["rssi"] for item in self.rssi_history
            if item["rssi"] is not None
        ]
        if not values:
            return None
        return {
            "samples": len(values),
            "min": min(values),
            "max": max(values),
            "mean": round(sum(values) / len(values), 1),
            "spread": max(values) - min(values),
        }

    def as_dict(self) -> dict:
        def iso(value: datetime | None) -> str | None:
            return value.isoformat() if value is not None else None

        return {
            "started": iso(self.started),
            "counters": dict(self.counters),
            "unrecognized": self.unrecognized,
            "decode_success_rate": self.decode_success_rate,
            "last_data": iso(self.last_data),
            "last_advertisement": iso(self.last_advertisement),
            "last_capture": iso(self.last_capture),
            "last_capture_summary": self.last_capture_summary,
            "last_error": self.last_error,
            "last_error_at": iso(self.last_error_at),
            "present": self.present,
            "rssi": self.rssi,
            "source": self.source,
            "rssi_statistics": self.rssi_statistics(),
            "rssi_history": list(self.rssi_history),
            "error_messages": dict(self.error_messages),
            "recent_errors": list(self.recent_errors),
        }
