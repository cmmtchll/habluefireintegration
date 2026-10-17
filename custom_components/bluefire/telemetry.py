"""Transport-independent J1939 and J1708/J1587 telemetry and MQTT contracts.

BlueFire notification bytes must be decoded before constructing a Frame; they
are not raw CAN frames. The repository's documented receive observations may
guide internal implementation, but are not hardware-validated release evidence.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from time import monotonic

from .catalog import CATALOG_VERSION, lookup, source_label, source_name
from .const import TELEMETRY_TIMEOUT
from .faults import DIAGNOSTICS, Diagnostic, decode_diagnostics
from .j1587 import (
    ENTITIES as J1587_ENTITIES,
    DiagnosticParameter,
    Parameter,
    decode_report,
    parse_j1708_message,
)
from .protocol import J1587Report
from .signals import SIGNALS, Signal

ENTITIES = SIGNALS + DIAGNOSTICS


def valid_vehicle_id(value: str) -> bool:
    """Restrict vehicle identifiers to a single MQTT topic level."""
    return re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value) is not None


@dataclass(frozen=True)
class Frame:
    """One complete classic J1939 CAN data frame, not a BLE notification."""

    can_id: int
    data: bytes

    def __post_init__(self) -> None:
        if type(self.can_id) is not int or not 0 <= self.can_id <= 0x1FFFFFFF:
            raise ValueError("Expected a 29-bit CAN identifier")
        if not isinstance(self.data, bytes) or len(self.data) != 8:
            raise ValueError("Expected exactly eight CAN data bytes")

    @property
    def pgn(self) -> int:
        """Remove the destination address from PDU1 parameter group numbers."""
        value = (self.can_id >> 8) & 0x3FFFF
        return value & 0x3FF00 if ((value >> 8) & 0xFF) < 240 else value

    @property
    def source_address(self) -> int:
        return self.can_id & 0xFF

    @property
    def priority(self) -> int:
        return (self.can_id >> 26) & 7


# topic, JSON/string payload, retain. Inject Home Assistant's MQTT publisher.
Publish = Callable[[str, str, bool], Awaitable[None]]
SaveDiscovery = Callable[[list[list[int]]], Awaitable[None]]


def validated_signal_ids(value) -> list[list[int]]:
    """Filter persisted discovery metadata without trusting stored topics."""
    return _validated_ids(value, ENTITIES, 0, 253)


def validated_j1587_ids(value) -> list[list[int]]:
    """J1587 MIDs/PIDs use a separate ledger field, never SPN ownership."""
    return _validated_ids(value, J1587_ENTITIES, 128, 255)


def _validated_ids(value, entities, minimum, maximum) -> list[list[int]]:
    spns = {signal.spn for signal in entities}
    if not isinstance(value, list):
        return []
    return [
        item for item in value
        if isinstance(item, list) and len(item) == 2
        and type(item[0]) is int and minimum <= item[0] <= maximum
        and type(item[1]) is int and item[1] in spns
    ]


class MqttBridge:
    """Publish protocol-separated, unit-explicit measurements and diagnostics.

    This is a receiver sink, not a BLE decoder. Live state is never retained.
    Call async_disconnected on every transport loss and before reconnecting.
    """

    protocol = "j1939"
    entities = ENTITIES
    validate_ids = staticmethod(validated_signal_ids)

    def __init__(
        self,
        vehicle_id: str,
        publish: Publish,
        *,
        discovery_prefix: str = "homeassistant",
        device_name: str | None = None,
        known_signals: list[list[int]] | None = None,
        save_discovery: SaveDiscovery | None = None,
        clock: Callable[[], float] = monotonic,
        known_j1587: list[list[int]] | None = None,
        save_j1587: SaveDiscovery | None = None,
    ) -> None:
        if not valid_vehicle_id(vehicle_id):
            raise ValueError("Invalid vehicle identifier")
        self.vehicle_id = vehicle_id
        self.prefix = f"vehicle/{vehicle_id}/{self.protocol}"
        self.publish = publish
        self.discovery_prefix = discovery_prefix
        self.device_name = device_name or f"{vehicle_id} vehicle telemetry"
        self.discovery: dict[str, str] = {}
        self._known_signals: set[tuple[int, int]] = set()
        self._save_discovery = save_discovery
        self._clock = clock
        self._last_frame: float | None = None
        self._online = False
        self._frame_lock = asyncio.Lock()
        catalog = {signal.spn: signal for signal in self.entities}
        for source, spn in self.validate_ids(known_signals):
            self._known_signals.add((source, spn))
            topic, payload = self._discovery_message(source, catalog[spn])
            self.discovery[topic] = payload
        self.j1587 = (
            J1587MqttBridge(
                vehicle_id, publish, discovery_prefix=discovery_prefix,
                device_name=self.device_name, known_signals=known_j1587,
                save_discovery=save_j1587, clock=clock,
            ) if self.protocol == "j1939" else None
        )

    @property
    def availability_topic(self) -> str:
        return f"{self.prefix}/availability"

    def diagnostics(self) -> dict:
        """Snapshot bridge state for user-requested diagnostics."""
        result = {
            "protocol": self.protocol,
            "vehicle_id": self.vehicle_id,
            "prefix": self.prefix,
            "availability_topic": self.availability_topic,
            "discovery_prefix": self.discovery_prefix,
            "device_name": self.device_name,
            "online": self._online,
            "last_frame_age_s": (
                None if self._last_frame is None
                else round(self._clock() - self._last_frame, 3)
            ),
            "known_signals": [list(item) for item in sorted(
                self._known_signals
            )],
            "discovery_topics": sorted(self.discovery),
        }
        if self.j1587 is not None:
            result["j1587"] = self.j1587.diagnostics()
        return result

    async def async_disconnected(self) -> None:
        """Invalidate freshness and withdraw retained online state."""
        if self.j1587 is not None:
            await self.j1587.async_disconnected()
        async with self._frame_lock:
            self._last_frame = None
            self._online = False
            await self.publish(self.availability_topic, "offline", True)

    async def async_check_stale(self) -> None:
        """Expire device availability without replaying old measurements."""
        if self.j1587 is not None:
            await self.j1587.async_check_stale()
        async with self._frame_lock:
            if (
                self._last_frame is not None
                and self._clock() - self._last_frame >= TELEMETRY_TIMEOUT
            ):
                self._last_frame = None
                self._online = False
                await self.publish(self.availability_topic, "offline", True)

    async def async_rediscover(self) -> None:
        """Replay definitions, not cached readings, on MQTT/HA restart."""
        async with self._frame_lock:
            for topic, payload in self.discovery.items():
                await self.publish(topic, payload, True)
        if self.j1587 is not None:
            await self.j1587.async_rediscover()

    def _discovery_message(
        self, source: int,
        signal: Signal | Diagnostic | Parameter | DiagnosticParameter,
    ) -> tuple[str, str]:
        """Build discovery from trusted definitions, not stored payloads."""
        unique_id = f"bluefire_{self.vehicle_id}_{source}_{signal.spn}"
        label = source_label(source)
        namespace = "spn"
        if self.protocol == "j1587":
            unique_id = (
                f"bluefire_{self.vehicle_id}_j1587_{source}_{signal.spn}"
            )
            label = f"{source_name(source, j1587=True)} ({source})"
            namespace = "pid"
        config = {
            "name": f"{signal.name} - {label}",
            "unique_id": unique_id,
            "state_topic": f"{self.prefix}/{source}/{namespace}/{signal.spn}",
            "value_template": (
                "{{ value_json.value if value_json.value "
                "is not none else 'None' }}"
            ),
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "expire_after": TELEMETRY_TIMEOUT,
            "device": {
                "identifiers": [f"bluefire_{self.vehicle_id}"],
                "name": self.device_name,
                "manufacturer": "BlueFire",
            },
            "origin": {
                "name": "BlueFire",
                "support_url": (
                    "https://github.com/cmmtchll/habluefireintegration"
                ),
            },
        }
        if isinstance(signal, (Diagnostic, DiagnosticParameter)):
            code = (
                signal.pid if isinstance(signal, DiagnosticParameter)
                else signal.pgn
            )
            config["state_topic"] = (
                f"{self.prefix}/{source}/faults/{code}"
            )
            config["value_template"] = "{{ value_json.summary }}"
            config["entity_category"] = "diagnostic"
            config["json_attributes_topic"] = config["state_topic"]
        else:
            config["unit_of_measurement"] = signal.unit
            config["state_class"] = signal.state_class
            config["json_attributes_topic"] = config["state_topic"]
            config["json_attributes_template"] = (
                "{{ {'description': value_json.description, "
                "'source_name': value_json.source_name, "
                "'source_address': value_json.source_address, "
                "'spn': value_json.spn, 'pgn': value_json.pgn} | tojson }}"
            )
            if self.protocol == "j1587":
                config["json_attributes_template"] = (
                    "{{ {'description': value_json.description, "
                    "'source_name': value_json.source_name, "
                    "'mid': value_json.mid, 'pid': value_json.pid} | tojson }}"
                )
            if signal.device_class:
                config["device_class"] = signal.device_class
        topic = f"{self.discovery_prefix}/sensor/{unique_id}/config"
        return topic, json.dumps(config)

    async def _async_remember(self, source: int, spn: int) -> None:
        """Persist ownership before creating retained broker configuration."""
        identity = (source, spn)
        if identity in self._known_signals:
            return
        updated = self._known_signals | {identity}
        if self._save_discovery is not None:
            await self._save_discovery([
                list(item) for item in sorted(updated)
            ])
        self._known_signals = updated

    async def async_process_frame(self, frame: Frame) -> None:
        """Accept a verified, reassembled frame from a future BLE driver."""
        if not isinstance(frame, Frame):
            raise ValueError("Expected a verified complete CAN Frame")
        async with self._frame_lock:
            if frame.source_address >= 254:
                # Null/global addresses are not valid transmitter identities.
                return
            await self._async_process_frame(frame)

    async def async_process_j1587(self, report: J1587Report) -> None:
        """Route complete normalized J1708/J1587 reports, not CAN frames."""
        await self.j1587.async_process_j1587(report)

    async def async_process_j1708(self, datagram: bytes) -> None:
        """Accept a complete checksummed datagram from a driver/capture."""
        message = parse_j1708_message(datagram)
        if message.mid < 128:
            raise ValueError("Non-J1587 J1708 messages have no telemetry map")
        # Validate every parameter before publishing any part of the datagram.
        for report in message.reports:
            decode_report(report)
        for report in message.reports:
            await self.async_process_j1587(report)

    async def _async_process_frame(self, frame: Frame) -> None:
        diagnostic = next(
            (item for item in DIAGNOSTICS if item.pgn == frame.pgn), None
        )
        faults = (
            decode_diagnostics(
                frame.pgn, frame.data, source=frame.source_address
            ) if diagnostic else None
        )
        timestamp = datetime.now(timezone.utc).isoformat()
        common = {
            "schema_version": 1,
            "protocol": "j1939",
            "vehicle_id": self.vehicle_id,
            "pgn": frame.pgn,
            "source_address": frame.source_address,
            "source_name": source_name(frame.source_address),
            "source_name_basis": "conventional_address_not_verified_identity",
            "pgn_name": lookup("pgn", frame.pgn)["name"],
            "catalog_version": CATALOG_VERSION,
            "timestamp": timestamp,
        }
        await self.publish(
            f"{self.prefix}/{frame.source_address}/frame",
            json.dumps({
                **common,
                "can_id": frame.can_id,
                "arbitration_id": frame.can_id,
                "is_extended_id": True,
                "dlc": len(frame.data),
                "priority": frame.priority,
                "data": frame.data.hex(),
            }),
            False,
        )
        for signal in SIGNALS:
            if signal.pgn != frame.pgn:
                continue
            state_topic = (
                f"{self.prefix}/{frame.source_address}/spn/{signal.spn}"
            )
            discovery_topic, payload = self._discovery_message(
                frame.source_address, signal
            )
            if discovery_topic not in self.discovery:
                await self._async_remember(frame.source_address, signal.spn)
                await self.publish(discovery_topic, payload, True)
                self.discovery[discovery_topic] = payload
            await self.publish(
                state_topic,
                json.dumps({
                    **common,
                    **signal.metadata(),
                    "value": signal.decode(frame.data),
                }),
                False,
            )
        if diagnostic is not None:
            discovery_topic, payload = self._discovery_message(
                frame.source_address, diagnostic
            )
            if discovery_topic not in self.discovery:
                await self._async_remember(
                    frame.source_address, diagnostic.spn
                )
                await self.publish(discovery_topic, payload, True)
                self.discovery[discovery_topic] = payload
            await self.publish(
                f"{self.prefix}/{frame.source_address}/faults/{frame.pgn}",
                json.dumps({**common, **faults}), False,
            )
        # A transport connection alone is not evidence of usable vehicle data.
        self._last_frame = self._clock()
        if not self._online:
            await self.publish(self.availability_topic, "online", True)
            self._online = True

    async def async_remove_discovery(self) -> None:
        """Remove definitions including those restored from storage."""
        await self.async_disconnected()
        await self._async_remove_definitions()
        if self.j1587 is not None:
            await self.j1587._async_remove_definitions()

    async def _async_remove_definitions(self) -> None:
        async with self._frame_lock:
            for source, spn in sorted(self._known_signals):
                signal = next(
                    item for item in self.entities if item.spn == spn
                )
                topic, _ = self._discovery_message(source, signal)
                await self.publish(topic, "", True)
            if self._save_discovery is not None:
                await self._save_discovery([])
            self._known_signals.clear()
            self.discovery.clear()


class J1587MqttBridge(MqttBridge):
    """Independent MID/PID ownership and freshness for the same adapter."""

    protocol = "j1587"
    entities = J1587_ENTITIES
    validate_ids = staticmethod(validated_j1587_ids)

    async def async_process_frame(self, frame: Frame) -> None:
        raise ValueError("J1587 accepts parameter reports, not CAN frames")

    async def async_process_j1587(self, report: J1587Report) -> None:
        decoded = decode_report(report)
        async with self._frame_lock:
            common = {
                "schema_version": 1, "protocol": "j1587",
                "datalink": "j1708", "vehicle_id": self.vehicle_id,
                "mid": report.mid, "pid": report.pid,
                "source_name": source_name(report.mid, j1587=True),
                "source_name_basis": "conventional_mid_not_verified_identity",
                "catalog_version": CATALOG_VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await self.publish(
                f"{self.prefix}/{report.mid}/report",
                json.dumps({
                    **common, "data": report.data.hex(),
                    "parameter": lookup("pid", report.pid),
                }), False,
            )
            entity = next(
                (item for item in self.entities if item.pid == report.pid),
                None,
            )
            if entity is not None:
                topic, payload = self._discovery_message(report.mid, entity)
                if topic not in self.discovery:
                    await self._async_remember(report.mid, entity.pid)
                    await self.publish(topic, payload, True)
                    self.discovery[topic] = payload
                diagnostic = decoded.get("diagnostics")
                state = (
                    diagnostic if diagnostic is not None
                    else decoded["signals"][0]
                )
                kind = "faults" if diagnostic is not None else "pid"
                await self.publish(
                    f"{self.prefix}/{report.mid}/{kind}/{report.pid}",
                    json.dumps({**common, **state}), False,
                )
            self._last_frame = self._clock()
            if not self._online:
                await self.publish(self.availability_topic, "online", True)
                self._online = True
