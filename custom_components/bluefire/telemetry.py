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

from .catalog import CATALOG_VERSION, lookup, source_name
from .const import (
    ENGINE_PROFILES, J1708_POLL_PIDS, J1708_POLL_TIMEOUT, TELEMETRY_TIMEOUT,
)
from .faults import DIAGNOSTICS, Diagnostic, decode_diagnostics
from .j1587 import (
    ENTITIES as J1587_ENTITIES,
    DiagnosticParameter,
    IdentificationParameter,
    Parameter,
    StatusParameter,
    decode_report,
    parse_j1708_message,
)
from .protocol import J1587Report, ObdReport, PgnReport
from .signals import SIGNALS, Signal

ENTITIES = SIGNALS + DIAGNOSTICS

_DISPLAY_NAMES = {
    "Electrical system voltage": "Supply voltage",
    "Battery potential": "Supply voltage",
    "Charging system potential": "Charging voltage",
}
_DISPLAY_PRECISION = {
    "%": 1, "°C": 1, "rpm": 2, "kPa": 2, "km/h": 2,
    "L/h": 2, "h": 2, "km": 2, "V": 2, "L": 2, "km/L": 2,
}
LAST_DATA_PUBLISH_INTERVAL = 15


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
SaveIdentification = Callable[[list[dict]], Awaitable[None]]


def last_known_entity(signal) -> bool:
    """Static identities and cumulative counters are not live measurements."""
    return (
        isinstance(signal, IdentificationParameter)
        or getattr(signal, "state_class", None) == "total_increasing"
    )


def validated_identification(value) -> list[dict]:
    """Restore bounded, decodable identity bytes, never stored metadata."""
    if not isinstance(value, list):
        return []
    records = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        mid, pid = item.get("mid"), item.get("pid")
        data, timestamp = item.get("data"), item.get("timestamp")
        if (
            type(mid) is not int or not 128 <= mid <= 255
            or type(pid) is not int or pid not in (234, 237, 243)
            or not isinstance(data, str) or len(data) > 510
            or not isinstance(timestamp, str)
        ):
            continue
        try:
            observed = datetime.fromisoformat(timestamp)
            report = J1587Report(mid, pid, bytes.fromhex(data))
            decoded = decode_report(report)["identification"]
        except ValueError:
            continue
        if observed.tzinfo is None or decoded["value"] is None:
            continue
        records[mid, pid] = {
            "mid": mid, "pid": pid, "data": report.data.hex(),
            "timestamp": observed.isoformat(),
        }
    return [records[key] for key in sorted(records)]


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

    Live state is never retained; identity and counters are last-known values.
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
        j1708_polling: bool = False,
        engine_profile: str = "generic",
        known_identification: list[dict] | None = None,
        save_identification: SaveIdentification | None = None,
    ) -> None:
        if not valid_vehicle_id(vehicle_id):
            raise ValueError("Invalid vehicle identifier")
        if engine_profile not in ENGINE_PROFILES:
            raise ValueError("Unknown engine profile")
        self.engine_profile = engine_profile
        self.diagnostic_profile = (
            "detroit_ddec_iii_iv"
            if engine_profile == "detroit_series_60_ddec_iv" else None
        )
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
        self._last_data: str | None = None
        self._last_data_published: str | None = None
        self._last_data_publish_time: float | None = None
        self._online = False
        self._identification: dict[int, dict[int, dict]] = {}
        self._save_identification = save_identification
        self._identification_listeners: list[Callable[[], None]] = []
        self._j1708_polling = j1708_polling
        self._availability_timeout = (
            J1708_POLL_TIMEOUT
            if self.protocol == "j1587" and j1708_polling
            else TELEMETRY_TIMEOUT
        )
        self._frame_lock = asyncio.Lock()
        catalog = {signal.spn: signal for signal in self.entities}
        for source, spn in self.validate_ids(known_signals):
            self._known_signals.add((source, spn))
            topic, payload = self._discovery_message(source, catalog[spn])
            self.discovery[topic] = payload
        if self.protocol == "j1587":
            for record in validated_identification(known_identification):
                report = J1587Report(
                    record["mid"], record["pid"], bytes.fromhex(record["data"])
                )
                self._identification.setdefault(report.mid, {})[
                    report.pid
                ] = {
                    **self._j1587_metadata(report, record["timestamp"]),
                    **decode_report(report)["identification"],
                    "value_basis": "last_observed",
                    "last_observed": record["timestamp"],
                }
                self._known_signals.add((report.mid, report.pid))
                topic, payload = self._discovery_message(
                    report.mid, catalog[report.pid]
                )
                self.discovery[topic] = payload
        self.j1587 = (
            J1587MqttBridge(
                vehicle_id, publish, discovery_prefix=discovery_prefix,
                device_name=self.device_name, known_signals=known_j1587,
                save_discovery=save_j1587, clock=clock,
                j1708_polling=j1708_polling,
                engine_profile=engine_profile,
                known_identification=known_identification,
                save_identification=save_identification,
            ) if self.protocol == "j1939" else None
        )

    @property
    def availability_topic(self) -> str:
        return f"{self.prefix}/availability"

    @property
    def identification_reports(self) -> list[dict]:
        """Snapshot decoded identification without an MQTT round trip."""
        return [
            dict(value) for parameters in self._identification.values()
            for value in parameters.values()
        ]

    def identification_report(self, mid: int, pid: int) -> dict | None:
        report = self._identification.get(mid, {}).get(pid)
        return dict(report) if report is not None else None

    def add_identification_listener(
        self, listener: Callable[[], None],
    ) -> Callable[[], None]:
        self._identification_listeners.append(listener)
        return lambda: self._identification_listeners.remove(listener)

    def _identification_changed(self) -> None:
        for listener in tuple(self._identification_listeners):
            listener()

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
            "last_data": self._last_data,
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
        if self.protocol == "j1587":
            result["engine_profile"] = self.engine_profile
            result["diagnostic_profile"] = self.diagnostic_profile
            result["controller_identification"] = {
                str(mid): {
                    str(pid): dict(value) for pid, value in parameters.items()
                }
                for mid, parameters in self._identification.items()
            }
        return result

    async def async_disconnected(
        self, *, clear_identification: bool = False,
    ) -> None:
        """Invalidate freshness and withdraw retained online state."""
        if self.j1587 is not None:
            await self.j1587.async_disconnected(
                clear_identification=clear_identification
            )
        async with self._frame_lock:
            self._last_frame = None
            self._online = False
            if clear_identification:
                self._identification.clear()
                self._identification_changed()
            await self.publish(self.availability_topic, "offline", True)
            await self._async_publish_last_data()

    async def async_check_stale(self) -> None:
        """Expire device availability without replaying old measurements."""
        if self.j1587 is not None:
            await self.j1587.async_check_stale()
        async with self._frame_lock:
            if (
                self._last_frame is not None
                and self._clock() - self._last_frame
                >= self._availability_timeout
            ):
                self._last_frame = None
                self._online = False
                await self.publish(self.availability_topic, "offline", True)
                await self._async_publish_last_data()

    async def async_rediscover(self) -> None:
        """Replay definitions and static identities, never live readings."""
        async with self._frame_lock:
            topic, payload = self._connectivity_discovery_message()
            await self.publish(topic, payload, True)
            topic, payload = self._last_data_discovery_message()
            await self.publish(topic, payload, True)
            for topic, payload in self.discovery.items():
                await self.publish(topic, payload, True)
            for report in self.identification_reports:
                if report["value"] is not None:
                    await self.publish(
                        f"{self.prefix}/{report['mid']}/pid/{report['pid']}",
                        json.dumps(report), True,
                    )
        if self.j1587 is not None:
            await self.j1587.async_rediscover()

    def _last_data_discovery_message(self) -> tuple[str, str]:
        _, payload = self._connectivity_discovery_message()
        config = json.loads(payload)
        unique_id = f"bluefire_{self.vehicle_id}_{self.protocol}_last_data"
        for key in ("payload_on", "payload_off"):
            del config[key]
        config.update(
            name=f"{self.protocol.upper()} last data seen",
            unique_id=unique_id,
            state_topic=f"{self.prefix}/last_data",
            device_class="timestamp",
            value_template="{{ value_json.timestamp }}",
        )
        return (
            f"{self.discovery_prefix}/sensor/{unique_id}/config",
            json.dumps(config),
        )

    async def _async_publish_last_data(self) -> None:
        if (
            self._last_data is not None
            and self._last_data != self._last_data_published
        ):
            await self.publish(
                f"{self.prefix}/last_data",
                json.dumps({"timestamp": self._last_data}), True,
            )
            self._last_data_published = self._last_data
            self._last_data_publish_time = self._clock()

    async def _async_data_seen(self, timestamp: str) -> None:
        self._last_frame = self._clock()
        self._last_data = timestamp
        if (
            self._last_data_publish_time is None
            or self._last_frame - self._last_data_publish_time
            >= LAST_DATA_PUBLISH_INTERVAL
        ):
            await self._async_publish_last_data()
        if not self._online:
            await self.publish(self.availability_topic, "online", True)
            self._online = True

    def _connectivity_discovery_message(self) -> tuple[str, str]:
        unique_id = (
            f"bluefire_{self.vehicle_id}_{self.protocol}_connectivity"
        )
        return (
            f"{self.discovery_prefix}/binary_sensor/{unique_id}/config",
            json.dumps({
                "name": f"{self.protocol.upper()} telemetry connectivity",
                "unique_id": unique_id,
                "state_topic": self.availability_topic,
                "payload_on": "online",
                "payload_off": "offline",
                "device_class": "connectivity",
                "entity_category": "diagnostic",
                # Offline is a state here, not entity unavailability.
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
            }),
        )

    def _discovery_message(
        self, source: int,
        signal: (
            Signal | Diagnostic | Parameter | DiagnosticParameter
            | IdentificationParameter | StatusParameter
        ),
    ) -> tuple[str, str]:
        """Build discovery from trusted definitions, not stored payloads."""
        unique_id = f"bluefire_{self.vehicle_id}_{source}_{signal.spn}"
        label = source_name(source, j1587=self.protocol == "j1587")
        if label == "Unidentified controller":
            label = f"Controller {source}"
        if (
            self.protocol == "j1587" and source == 128
            and self.diagnostic_profile is not None
        ):
            label = ENGINE_PROFILES[self.engine_profile]
        namespace = "spn"
        if self.protocol == "j1587":
            unique_id = (
                f"bluefire_{self.vehicle_id}_j1587_{source}_{signal.spn}"
            )
            namespace = "pid"
        name = _DISPLAY_NAMES.get(signal.name, signal.name)
        name = name.removeprefix(f"{label} ")
        name = name[0].upper() + name[1:]
        config = {
            "name": f"{label}: {name}",
            "unique_id": unique_id,
            "state_topic": f"{self.prefix}/{source}/{namespace}/{signal.spn}",
            "value_template": (
                "{{ value_json.value if value_json.value "
                "is not none else 'None' }}"
            ),
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "expire_after": (
                J1708_POLL_TIMEOUT
                if self.protocol == "j1587" and self._j1708_polling
                and signal.spn in J1708_POLL_PIDS
                else TELEMETRY_TIMEOUT
            ),
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
        elif isinstance(signal, IdentificationParameter):
            config["entity_category"] = "diagnostic"
            config["json_attributes_topic"] = config["state_topic"]
        elif isinstance(signal, StatusParameter):
            config["json_attributes_topic"] = config["state_topic"]
        else:
            config["unit_of_measurement"] = signal.unit
            config["suggested_display_precision"] = (
                _DISPLAY_PRECISION[signal.unit]
            )
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
                    "'source_name_basis': value_json.source_name_basis, "
                    "'mid': value_json.mid, 'pid': value_json.pid} | tojson }}"
                )
            if signal.device_class:
                config["device_class"] = signal.device_class
        if last_known_entity(signal):
            for key in (
                "expire_after", "availability_topic",
                "payload_available", "payload_not_available",
            ):
                del config[key]
            if "json_attributes_template" in config:
                config["json_attributes_template"] = (
                    config["json_attributes_template"].replace(
                        "} | tojson",
                        ", 'last_observed': value_json.last_observed, "
                        "'value_basis': value_json.value_basis} | tojson",
                    )
                )
        topic = f"{self.discovery_prefix}/sensor/{unique_id}/config"
        return topic, json.dumps(config)

    async def _async_publish_value(
        self, source: int, signal, state: dict,
    ) -> None:
        retained = last_known_entity(signal)
        if retained:
            if state["value"] is None:
                return
            state = {
                **state, "value_basis": "last_observed",
                "last_observed": state["timestamp"],
            }
        namespace = "pid" if self.protocol == "j1587" else "spn"
        await self.publish(
            f"{self.prefix}/{source}/{namespace}/{signal.spn}",
            json.dumps(state), retained,
        )

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

    async def async_process_pgn_report(self, report: PgnReport) -> None:
        """Publish a vendor PGN report without inventing a CAN identifier."""
        if not isinstance(report, PgnReport):
            raise ValueError("Expected a parsed vendor PGN report")
        async with self._frame_lock:
            timestamp = datetime.now(timezone.utc).isoformat()
            common = {
                "schema_version": 1,
                "protocol": "j1939",
                "vehicle_id": self.vehicle_id,
                "pgn": report.pgn,
                "source_address": report.source_address,
                "source_name": source_name(report.source_address),
                "source_name_basis": (
                    "conventional_address_not_verified_identity"
                ),
                "priority": report.priority,
                "data_page": report.data_page,
                "catalog_version": CATALOG_VERSION,
                "timestamp": timestamp,
            }
            await self.publish(
                f"{self.prefix}/{report.source_address}/report/{report.pgn}",
                json.dumps({**common, "data": report.data.hex()}),
                False,
            )
            if report.source_address < 254 and report.data_page == 0:
                for signal in SIGNALS:
                    if (
                        signal.pgn != report.pgn
                        or len(report.data) != 8
                    ):
                        continue
                    topic, payload = self._discovery_message(
                        report.source_address, signal
                    )
                    if topic not in self.discovery:
                        await self._async_remember(
                            report.source_address, signal.spn
                        )
                        await self.publish(topic, payload, True)
                        self.discovery[topic] = payload
                    await self._async_publish_value(
                        report.source_address, signal, {
                            **common,
                            **signal.metadata(),
                            "value": signal.decode(report.data),
                        },
                    )
                diagnostic = next(
                    (
                        item for item in DIAGNOSTICS
                        if item.pgn == report.pgn
                    ),
                    None,
                )
                if diagnostic is not None and len(report.data) == 8:
                    topic, payload = self._discovery_message(
                        report.source_address, diagnostic
                    )
                    if topic not in self.discovery:
                        await self._async_remember(
                            report.source_address, diagnostic.spn
                        )
                        await self.publish(topic, payload, True)
                        self.discovery[topic] = payload
                    faults = decode_diagnostics(
                        report.pgn, report.data,
                        source=report.source_address,
                    )
                    await self.publish(
                        (
                            f"{self.prefix}/{report.source_address}"
                            f"/faults/{report.pgn}"
                        ),
                        json.dumps({**common, **faults}),
                        False,
                    )
            if report.source_address < 254 and report.data:
                await self._async_data_seen(timestamp)

    async def async_process_obd_report(self, report: ObdReport) -> None:
        """Preserve OBD reports separately without relabeling them."""
        if not isinstance(report, ObdReport):
            raise ValueError("Expected a parsed OBD report")
        await self.publish(
            f"vehicle/{self.vehicle_id}/obd/"
            f"{report.source}/{report.mode}/{report.pid}",
            json.dumps({
                "schema_version": 1,
                "protocol": "obd",
                "vehicle_id": self.vehicle_id,
                "source": report.source,
                "mode": report.mode,
                "pid": report.pid,
                "data": report.data.hex(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }),
            False,
        )

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
            discovery_topic, payload = self._discovery_message(
                frame.source_address, signal
            )
            if discovery_topic not in self.discovery:
                await self._async_remember(frame.source_address, signal.spn)
                await self.publish(discovery_topic, payload, True)
                self.discovery[discovery_topic] = payload
            await self._async_publish_value(
                frame.source_address, signal, {
                    **common,
                    **signal.metadata(),
                    "value": signal.decode(frame.data),
                },
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
        await self._async_data_seen(timestamp)

    async def async_remove_discovery(
        self, *, clear_retained: bool = True,
    ) -> None:
        """Remove definitions including those restored from storage."""
        await self.async_disconnected(clear_identification=True)
        await self._async_remove_definitions(clear_retained=clear_retained)
        if self.j1587 is not None:
            await self.j1587._async_remove_definitions(
                clear_retained=clear_retained
            )

    async def _async_remove_definitions(
        self, *, clear_retained: bool = True,
    ) -> None:
        async with self._frame_lock:
            topic, _ = self._connectivity_discovery_message()
            await self.publish(topic, "", True)
            topic, _ = self._last_data_discovery_message()
            await self.publish(topic, "", True)
            if clear_retained:
                await self.publish(f"{self.prefix}/last_data", "", True)
            for source, spn in sorted(self._known_signals):
                signal = next(
                    item for item in self.entities if item.spn == spn
                )
                topic, _ = self._discovery_message(source, signal)
                await self.publish(topic, "", True)
                if clear_retained and last_known_entity(signal):
                    namespace = "pid" if self.protocol == "j1587" else "spn"
                    await self.publish(
                        f"{self.prefix}/{source}/{namespace}/{spn}", "", True
                    )
            if self._save_discovery is not None:
                await self._save_discovery([])
            self._known_signals.clear()
            self.discovery.clear()


class J1587MqttBridge(MqttBridge):
    """Independent MID/PID ownership and freshness for the same adapter."""

    protocol = "j1587"
    entities = J1587_ENTITIES
    validate_ids = staticmethod(validated_j1587_ids)

    def _j1587_metadata(self, report: J1587Report, timestamp: str) -> dict:
        common = {
            "schema_version": 1, "protocol": "j1587",
            "datalink": "j1708", "vehicle_id": self.vehicle_id,
            "mid": report.mid, "pid": report.pid,
            "source_name": source_name(report.mid, j1587=True),
            "source_name_basis": "conventional_mid_not_verified_identity",
            "catalog_version": CATALOG_VERSION,
            "timestamp": timestamp,
        }
        if report.mid == 128 and self.diagnostic_profile is not None:
            common.update(
                source_name=ENGINE_PROFILES[self.engine_profile],
                source_name_basis="configured_official_equipment_labels",
                engine_profile=self.engine_profile,
                diagnostic_profile=self.diagnostic_profile,
            )
        return common

    async def async_process_frame(self, frame: Frame) -> None:
        raise ValueError("J1587 accepts parameter reports, not CAN frames")

    async def async_process_j1587(self, report: J1587Report) -> None:
        decoded = decode_report(
            report,
            profile=self.diagnostic_profile if report.mid == 128 else None,
        )
        async with self._frame_lock:
            common = self._j1587_metadata(
                report, datetime.now(timezone.utc).isoformat()
            )
            identification = decoded.get("identification")
            if identification is not None:
                previous = self.identification_report(report.mid, report.pid)
                if (
                    identification["value"] is not None or previous is None
                    or previous["value"] is None
                ):
                    self._identification.setdefault(report.mid, {})[
                        report.pid
                    ] = {
                        **common, **identification,
                        "value_basis": "last_observed",
                        "last_observed": common["timestamp"],
                    }
                    self._identification_changed()
                if self._save_identification is not None:
                    await self._async_remember(report.mid, report.pid)
                    await self._save_identification(validated_identification(
                        self.identification_reports
                    ))
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
                    else identification if identification is not None
                    else decoded["signals"][0]
                )
                if diagnostic is not None:
                    await self.publish(
                        f"{self.prefix}/{report.mid}/faults/{report.pid}",
                        json.dumps({**common, **state}), False,
                    )
                else:
                    await self._async_publish_value(
                        report.mid, entity, {**common, **state},
                    )
            await self._async_data_seen(common["timestamp"])
