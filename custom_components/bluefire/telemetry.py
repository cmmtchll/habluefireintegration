"""Transport-independent J1939 telemetry and MQTT contract.

BlueFire notification bytes MUST be unwrapped by a verified vendor protocol
implementation before constructing a Frame. They are not raw CAN frames.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re


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


@dataclass(frozen=True)
class Signal:
    """A byte-aligned SAE J1939 signal in engineering units."""

    pgn: int
    spn: int
    name: str
    start: int
    length: int
    resolution: float
    offset: float
    unit: str
    device_class: str | None = None
    state_class: str = "measurement"

    def decode(self, data: bytes) -> float | None:
        """Decode a catalogued numeric SPN from a complete J1939 payload."""
        raw = int.from_bytes(
            data[self.start:self.start + self.length], "little"
        )
        # These numeric SPNs reserve the upper raw ranges. Do not apply this
        # rule to enumerations (for example gear 0xFB means Park).
        if raw >= 0xFB << (8 * (self.length - 1)):
            return None
        return round(raw * self.resolution + self.offset, 6)


SIGNALS = (
    Signal(61444, 190, "Engine speed", 3, 2, 0.125, 0, "rpm"),
    Signal(61444, 513, "Actual engine torque", 2, 1, 1, -125, "%"),
    Signal(61443, 91, "Accelerator pedal position", 1, 1, 0.4, 0, "%"),
    Signal(61443, 92, "Engine load", 2, 1, 1, 0, "%"),
    Signal(65262, 110, "Engine coolant temperature",
           0, 1, 1, -40, "°C", "temperature"),
    Signal(65262, 175, "Engine oil temperature", 2,
           2, 0.03125, -273, "°C", "temperature"),
    Signal(65263, 100, "Engine oil pressure", 3, 1, 4, 0, "kPa", "pressure"),
    Signal(65263, 109, "Engine coolant pressure",
           6, 1, 2, 0, "kPa", "pressure"),
    Signal(65263, 111, "Engine coolant level", 7, 1, 0.4, 0, "%"),
    Signal(65265, 84, "Wheel-based vehicle speed",
           1, 2, 1 / 256, 0, "km/h", "speed"),
    Signal(65266, 183, "Engine fuel rate", 0, 2,
           0.05, 0, "L/h", "volume_flow_rate"),
    Signal(65253, 247, "Engine total hours", 0, 4, 0.05,
           0, "h", "duration", "total_increasing"),
    Signal(65248, 245, "Total vehicle distance", 4, 4,
           0.125, 0, "km", "distance", "total_increasing"),
    Signal(65271, 168, "Battery potential", 4, 2, 0.05, 0, "V", "voltage"),
    Signal(65276, 96, "Fuel level", 1, 1, 0.4, 0, "%"),
    Signal(65269, 108, "Barometric pressure", 0, 1, 0.5, 0, "kPa", "pressure"),
    Signal(65269, 171, "Ambient air temperature", 3, 2, 0.03125, -273,
           "°C", "temperature"),
    Signal(65269, 172, "Engine air intake temperature", 5, 1, 1, -40,
           "°C", "temperature"),
    Signal(65270, 102, "Intake manifold pressure", 1, 1, 2, 0,
           "kPa", "pressure"),
    Signal(65270, 105, "Intake manifold temperature", 2, 1, 1, -40,
           "°C", "temperature"),
    Signal(65270, 106, "Air inlet pressure", 3, 1, 2, 0, "kPa", "pressure"),
    Signal(65270, 107, "Air filter differential pressure", 4, 1, 0.05, 0,
           "kPa", "pressure"),
    Signal(65270, 173, "Exhaust gas temperature", 5, 2, 0.03125, -273,
           "°C", "temperature"),
    Signal(65272, 124, "Transmission oil level", 1, 1, 0.4, 0, "%"),
    Signal(65272, 126, "Transmission filter differential pressure", 2, 1, 2, 0,
           "kPa", "pressure"),
    Signal(65272, 127, "Transmission oil pressure", 3, 1, 16, 0,
           "kPa", "pressure"),
    Signal(65272, 177, "Transmission oil temperature", 4, 2, 0.03125, -273,
           "°C", "temperature"),
    Signal(65257, 182, "Engine trip fuel used", 0, 4, 0.5, 0,
           "L", "volume", "total_increasing"),
    Signal(65257, 250, "Engine total fuel used", 4, 4, 0.5, 0,
           "L", "volume", "total_increasing"),
    Signal(65244, 236, "Engine total idle fuel used", 0, 4, 0.5, 0,
           "L", "volume", "total_increasing"),
    Signal(65244, 235, "Engine total idle hours", 4, 4, 0.05, 0,
           "h", "duration", "total_increasing"),
    Signal(65271, 167, "Charging system potential", 2, 2, 0.05, 0,
           "V", "voltage"),
    Signal(65263, 94, "Engine fuel delivery pressure", 0, 1, 4, 0,
           "kPa", "pressure"),
    Signal(65263, 98, "Engine oil level", 2, 1, 0.4, 0, "%"),
    Signal(65262, 174, "Engine fuel temperature", 1, 1, 1, -40,
           "°C", "temperature"),
    Signal(65262, 176, "Engine turbocharger oil temperature", 4, 2, 0.03125,
           -273, "°C", "temperature"),
    Signal(65262, 52, "Engine intercooler temperature", 6, 1, 1, -40,
           "°C", "temperature"),
)

# topic, JSON/string payload, retain. Inject Home Assistant's MQTT publisher.
Publish = Callable[[str, str, bool], Awaitable[None]]


class MqttBridge:
    """Publish source-address-scoped, unit-explicit J1939 measurements.

    This is a receiver sink, not a BLE decoder. Live state is never retained.
    Call async_disconnected on every transport loss and before reconnecting.
    """

    def __init__(self, vehicle_id: str, publish: Publish) -> None:
        if not valid_vehicle_id(vehicle_id):
            raise ValueError("Invalid vehicle identifier")
        self.vehicle_id = vehicle_id
        self.prefix = f"vehicle/{vehicle_id}/j1939"
        self.publish = publish
        self.discovery: dict[str, str] = {}
        self._frame_lock = asyncio.Lock()

    @property
    def availability_topic(self) -> str:
        return f"{self.prefix}/availability"

    async def async_disconnected(self) -> None:
        """Never leave retained adapter-online state behind."""
        await self.publish(self.availability_topic, "offline", True)

    async def async_rediscover(self) -> None:
        """Replay definitions, not cached readings, on MQTT/HA restart."""
        for topic, payload in tuple(self.discovery.items()):
            await self.publish(topic, payload, True)

    async def async_process_frame(self, frame: Frame) -> None:
        """Accept a verified, reassembled frame from a future BLE driver."""
        async with self._frame_lock:
            await self._async_process_frame(frame)

    async def _async_process_frame(self, frame: Frame) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        common = {
            "schema_version": 1,
            "protocol": "j1939",
            "vehicle_id": self.vehicle_id,
            "pgn": frame.pgn,
            "source_address": frame.source_address,
            "timestamp": timestamp,
        }
        await self.publish(
            f"{self.prefix}/{frame.source_address}/frame",
            json.dumps({
                **common,
                "can_id": frame.can_id,
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
            unique_id = (
                f"bluefire_{self.vehicle_id}_"
                f"{frame.source_address}_{signal.spn}"
            )
            discovery_topic = f"homeassistant/sensor/{unique_id}/config"
            if discovery_topic not in self.discovery:
                config = {
                    "name": signal.name,
                    "unique_id": unique_id,
                    "state_topic": state_topic,
                    "value_template": (
                        "{{ value_json.value if value_json.value "
                        "is not none else 'None' }}"
                    ),
                    "unit_of_measurement": signal.unit,
                    "state_class": signal.state_class,
                    "availability_topic": self.availability_topic,
                    "expire_after": 60,
                    "device": {
                        "identifiers": [f"bluefire_{self.vehicle_id}"],
                        "name": f"{self.vehicle_id} J1939",
                        "manufacturer": "BlueFire",
                    },
                }
                if signal.device_class:
                    config["device_class"] = signal.device_class
                payload = json.dumps(config)
                await self.publish(discovery_topic, payload, True)
                self.discovery[discovery_topic] = payload
            await self.publish(
                state_topic,
                json.dumps({
                    **common,
                    "spn": signal.spn,
                    "value": signal.decode(frame.data),
                    "unit": signal.unit,
                }),
                False,
            )
        # A transport connection alone is not evidence of usable vehicle data.
        # Leave retained "offline" in the broker. After a process crash, a new
        # subscriber must not resurrect cached availability as live telemetry.
        await self.publish(self.availability_topic, "online", False)

    async def async_remove_discovery(self) -> None:
        """Remove this runtime's retained discovery definitions."""
        await self.async_disconnected()
        for topic in tuple(self.discovery):
            await self.publish(topic, "", True)
        self.discovery.clear()
