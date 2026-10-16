"""Shared, transport-independent definitions in engineering units."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    """A byte-aligned SAE J1939 signal, not a PID or proprietary code."""

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

    @property
    def description(self) -> str:
        unit_name = {
            "rpm": "revolutions per minute", "%": "percent",
            "°C": "degrees Celsius", "kPa": "kilopascals",
            "km/h": "kilometres per hour", "L/h": "litres per hour",
            "h": "hours", "km": "kilometres", "V": "volts", "L": "litres",
        }[self.unit]
        return (
            f"{self.name}, reported in {unit_name} ({self.unit}). "
            "Reserved, error and unavailable values are reported as null."
        )

    def decode(self, data: bytes) -> float | None:
        """Decode a complete J1939 payload without retaining an old reading."""
        if not isinstance(data, bytes) or len(data) != 8:
            raise ValueError("Expected exactly eight CAN data bytes")
        raw = int.from_bytes(
            data[self.start:self.start + self.length], "little"
        )
        # Numeric SPNs reserve this range; gear/enumeration rules differ.
        if raw >= 0xFB << (8 * (self.length - 1)):
            return None
        return round(raw * self.resolution + self.offset, 6)

    def metadata(self) -> dict:
        """Use the same labels and units in MQTT, replay and catalog export."""
        return {
            "spn": self.spn, "name": self.name,
            "description": self.description, "unit": self.unit,
        }


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
