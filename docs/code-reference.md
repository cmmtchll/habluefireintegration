# BlueFire vehicle code reference

[Integration README](../README.md)

Generated from the shared code dictionary. Do not edit tables by hand; update the dictionary and regenerate this file.

```powershell
python .\scripts\catalog_bluefire.py --markdown --output .\docs\code-reference.md
```

Catalog version: **3**. Curated, incomplete; unknown codes are not inferred.

Vehicle context: official labels and Prevost documentation identify **Detroit Diesel Series 60, 12.7 L, 500 HP, DDEC IV**. The coach build sheet specifies **Allison HD4000MH R**, not the B500 listed in the generic coach specification. Transmission control generation is not established. Engine interpretation requires explicit entry configuration; no profile is inferred from reported text.

J1939 SPNs, J1587 PIDs/SIDs, OBD mode/PIDs, Detroit flash codes and Allison main/subcodes are separate namespaces. A number alone is not enough to identify its meaning. Unknown codes retain their IDs and an explicit unmapped label; no meaning is guessed.

Source-address and MID labels are conventional roles unless engine MID 128 uses the configured official-label DDEC IV profile. Other controller identities are not inferred. These are independently worded factual summaries, not a complete service manual or a repair/safety assessment.

## J1939 decoded measurements

Offsets are zero-based byte offsets; values are little-endian. Engineering value = raw * resolution + offset. Numeric raw values at or above 0xFB shifted to the most-significant byte become null; this rule must not be applied to enumerations.

| PGN | SPN | Label | Unit | Byte | Bytes | Resolution | Offset | HA state class | Description |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 61444 | 190 | Engine speed | rpm | 3 | 2 | 0.125 | 0 | measurement | Engine speed, reported in revolutions per minute (rpm). Reserved, error and unavailable values are reported as null. |
| 61444 | 513 | Actual engine torque | % | 2 | 1 | 1 | -125 | measurement | Actual engine torque, reported in percent (%). Reserved, error and unavailable values are reported as null. |
| 61443 | 91 | Accelerator pedal position | % | 1 | 1 | 0.4 | 0 | measurement | Accelerator pedal position, reported in percent (%). Reserved, error and unavailable values are reported as null. |
| 61443 | 92 | Engine load | % | 2 | 1 | 1 | 0 | measurement | Engine load, reported in percent (%). Reserved, error and unavailable values are reported as null. |
| 65262 | 110 | Engine coolant temperature | °C | 0 | 1 | 1 | -40 | measurement | Engine coolant temperature, reported in degrees Celsius (°C). Reserved, error and unavailable values are reported as null. |
| 65262 | 175 | Engine oil temperature | °C | 2 | 2 | 0.03125 | -273 | measurement | Engine oil temperature, reported in degrees Celsius (°C). Reserved, error and unavailable values are reported as null. |
| 65263 | 100 | Engine oil pressure | kPa | 3 | 1 | 4 | 0 | measurement | Engine oil pressure, reported in kilopascals (kPa). Reserved, error and unavailable values are reported as null. |
| 65263 | 109 | Engine coolant pressure | kPa | 6 | 1 | 2 | 0 | measurement | Engine coolant pressure, reported in kilopascals (kPa). Reserved, error and unavailable values are reported as null. |
| 65263 | 111 | Engine coolant level | % | 7 | 1 | 0.4 | 0 | measurement | Engine coolant level, reported in percent (%). Reserved, error and unavailable values are reported as null. |
| 65265 | 84 | Wheel-based vehicle speed | km/h | 1 | 2 | 0.00390625 | 0 | measurement | Wheel-based vehicle speed, reported in kilometres per hour (km/h). Reserved, error and unavailable values are reported as null. |
| 65266 | 183 | Engine fuel rate | L/h | 0 | 2 | 0.05 | 0 | measurement | Engine fuel rate, reported in litres per hour (L/h). Reserved, error and unavailable values are reported as null. |
| 65253 | 247 | Engine total hours | h | 0 | 4 | 0.05 | 0 | total_increasing | Engine total hours, reported in hours (h). Reserved, error and unavailable values are reported as null. |
| 65248 | 245 | Total vehicle distance | km | 4 | 4 | 0.125 | 0 | total_increasing | Total vehicle distance, reported in kilometres (km). Reserved, error and unavailable values are reported as null. |
| 65271 | 168 | Battery potential | V | 4 | 2 | 0.05 | 0 | measurement | Battery potential, reported in volts (V). Reserved, error and unavailable values are reported as null. |
| 65276 | 96 | Fuel level | % | 1 | 1 | 0.4 | 0 | measurement | Fuel level, reported in percent (%). Reserved, error and unavailable values are reported as null. |
| 65269 | 108 | Barometric pressure | kPa | 0 | 1 | 0.5 | 0 | measurement | Barometric pressure, reported in kilopascals (kPa). Reserved, error and unavailable values are reported as null. |
| 65269 | 171 | Ambient air temperature | °C | 3 | 2 | 0.03125 | -273 | measurement | Ambient air temperature, reported in degrees Celsius (°C). Reserved, error and unavailable values are reported as null. |
| 65269 | 172 | Engine air intake temperature | °C | 5 | 1 | 1 | -40 | measurement | Engine air intake temperature, reported in degrees Celsius (°C). Reserved, error and unavailable values are reported as null. |
| 65270 | 102 | Intake manifold pressure | kPa | 1 | 1 | 2 | 0 | measurement | Intake manifold pressure, reported in kilopascals (kPa). Reserved, error and unavailable values are reported as null. |
| 65270 | 105 | Intake manifold temperature | °C | 2 | 1 | 1 | -40 | measurement | Intake manifold temperature, reported in degrees Celsius (°C). Reserved, error and unavailable values are reported as null. |
| 65270 | 106 | Air inlet pressure | kPa | 3 | 1 | 2 | 0 | measurement | Air inlet pressure, reported in kilopascals (kPa). Reserved, error and unavailable values are reported as null. |
| 65270 | 107 | Air filter differential pressure | kPa | 4 | 1 | 0.05 | 0 | measurement | Air filter differential pressure, reported in kilopascals (kPa). Reserved, error and unavailable values are reported as null. |
| 65270 | 173 | Exhaust gas temperature | °C | 5 | 2 | 0.03125 | -273 | measurement | Exhaust gas temperature, reported in degrees Celsius (°C). Reserved, error and unavailable values are reported as null. |
| 65272 | 124 | Transmission oil level | % | 1 | 1 | 0.4 | 0 | measurement | Transmission oil level, reported in percent (%). Reserved, error and unavailable values are reported as null. |
| 65272 | 126 | Transmission filter differential pressure | kPa | 2 | 1 | 2 | 0 | measurement | Transmission filter differential pressure, reported in kilopascals (kPa). Reserved, error and unavailable values are reported as null. |
| 65272 | 127 | Transmission oil pressure | kPa | 3 | 1 | 16 | 0 | measurement | Transmission oil pressure, reported in kilopascals (kPa). Reserved, error and unavailable values are reported as null. |
| 65272 | 177 | Transmission oil temperature | °C | 4 | 2 | 0.03125 | -273 | measurement | Transmission oil temperature, reported in degrees Celsius (°C). Reserved, error and unavailable values are reported as null. |
| 65257 | 182 | Engine trip fuel used | L | 0 | 4 | 0.5 | 0 | total_increasing | Engine trip fuel used, reported in litres (L). Reserved, error and unavailable values are reported as null. |
| 65257 | 250 | Engine total fuel used | L | 4 | 4 | 0.5 | 0 | total_increasing | Engine total fuel used, reported in litres (L). Reserved, error and unavailable values are reported as null. |
| 65244 | 236 | Engine total idle fuel used | L | 0 | 4 | 0.5 | 0 | total_increasing | Engine total idle fuel used, reported in litres (L). Reserved, error and unavailable values are reported as null. |
| 65244 | 235 | Engine total idle hours | h | 4 | 4 | 0.05 | 0 | total_increasing | Engine total idle hours, reported in hours (h). Reserved, error and unavailable values are reported as null. |
| 65271 | 167 | Charging system potential | V | 2 | 2 | 0.05 | 0 | measurement | Charging system potential, reported in volts (V). Reserved, error and unavailable values are reported as null. |
| 65263 | 94 | Engine fuel delivery pressure | kPa | 0 | 1 | 4 | 0 | measurement | Engine fuel delivery pressure, reported in kilopascals (kPa). Reserved, error and unavailable values are reported as null. |
| 65263 | 98 | Engine oil level | % | 2 | 1 | 0.4 | 0 | measurement | Engine oil level, reported in percent (%). Reserved, error and unavailable values are reported as null. |
| 65262 | 174 | Engine fuel temperature | °C | 1 | 1 | 1 | -40 | measurement | Engine fuel temperature, reported in degrees Celsius (°C). Reserved, error and unavailable values are reported as null. |
| 65262 | 176 | Engine turbocharger oil temperature | °C | 4 | 2 | 0.03125 | -273 | measurement | Engine turbocharger oil temperature, reported in degrees Celsius (°C). Reserved, error and unavailable values are reported as null. |
| 65262 | 52 | Engine intercooler temperature | °C | 6 | 1 | 1 | -40 | measurement | Engine intercooler temperature, reported in degrees Celsius (°C). Reserved, error and unavailable values are reported as null. |

Measurement provenance: https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns

## J1708/J1587 decoded measurements

These independent PID definitions are not J1939 layouts. The parameter value excludes its PID and any variable-parameter byte-count prefix. Engineering value = raw * resolution + offset, rounded to six decimals. All-ones values become null using the observed BlueFire unavailable convention; J1939's upper reserved ranges are not reused. Only PID 101 uses a signed two's-complement raw value; the other supported numeric PIDs are unsigned.

Native units include mph, psi, degrees Fahrenheit and US gallons. Conversions use 1 mile = 1.609344 km and 1 US gallon = 3.785411784 L. Other mapped PIDs below may have labels without a value decoder; they remain raw-only rather than borrowing a J1939 scale.

| PID | Label | Value bytes | Signed | Output unit | Resolution | Offset | HA state class | Description |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 26 | Fan speed percentage | 1 | False | % | 0.5 | 0 | measurement | Fan speed percentage, converted from J1587 units to %. An all-ones unavailable value is reported as null. |
| 51 | Throttle position | 1 | False | % | 0.4 | 0 | measurement | Throttle position, converted from J1587 units to %. An all-ones unavailable value is reported as null. |
| 68 | Engine torque factor | 1 | False | % | 0.5 | 0 | measurement | Engine torque factor, converted from J1587 units to %. An all-ones unavailable value is reported as null. |
| 74 | Maximum road speed | 1 | False | km/h | 0.804672 | 0 | measurement | Maximum road speed, converted from J1587 units to km/h. An all-ones unavailable value is reported as null. |
| 84 | Vehicle speed | 1 | False | km/h | 0.804672 | 0 | measurement | Vehicle speed, converted from J1587 units to km/h. An all-ones unavailable value is reported as null. |
| 86 | Cruise set speed | 1 | False | km/h | 0.804672 | 0 | measurement | Cruise set speed, converted from J1587 units to km/h. An all-ones unavailable value is reported as null. |
| 91 | Accelerator pedal position | 1 | False | % | 0.4 | 0 | measurement | Accelerator pedal position, converted from J1587 units to %. An all-ones unavailable value is reported as null. |
| 92 | Engine load | 1 | False | % | 0.5 | 0 | measurement | Engine load, converted from J1587 units to %. An all-ones unavailable value is reported as null. |
| 94 | Fuel delivery pressure | 1 | False | kPa | 3.447378646584 | 0 | measurement | Fuel delivery pressure, converted from J1587 units to kPa. An all-ones unavailable value is reported as null. |
| 96 | Fuel level | 1 | False | % | 0.5 | 0 | measurement | Fuel level, converted from J1587 units to %. An all-ones unavailable value is reported as null. |
| 100 | Engine oil pressure | 1 | False | kPa | 3.447378646584 | 0 | measurement | Engine oil pressure, converted from J1587 units to kPa. An all-ones unavailable value is reported as null. |
| 101 | Crankcase pressure | 1 | True | kPa | 0.861844661646 | 0 | measurement | Crankcase pressure, converted from J1587 units to kPa. An all-ones unavailable value is reported as null. |
| 102 | Intake manifold pressure | 1 | False | kPa | 0.861844661646 | 0 | measurement | Intake manifold pressure, converted from J1587 units to kPa. An all-ones unavailable value is reported as null. |
| 105 | Intake manifold temperature | 1 | False | °C | 0.5555555555555556 | -17.77777777777778 | measurement | Intake manifold temperature, converted from J1587 units to °C. An all-ones unavailable value is reported as null. |
| 108 | Barometric pressure | 1 | False | kPa | 0.430922330823 | 0 | measurement | Barometric pressure, converted from J1587 units to kPa. An all-ones unavailable value is reported as null. |
| 109 | Coolant pressure | 1 | False | kPa | 0.861844661646 | 0 | measurement | Coolant pressure, converted from J1587 units to kPa. An all-ones unavailable value is reported as null. |
| 110 | Coolant temperature | 1 | False | °C | 0.5555555555555556 | -17.77777777777778 | measurement | Coolant temperature, converted from J1587 units to °C. An all-ones unavailable value is reported as null. |
| 111 | Coolant level | 1 | False | % | 0.5 | 0 | measurement | Coolant level, converted from J1587 units to %. An all-ones unavailable value is reported as null. |
| 116 | Brake application pressure | 1 | False | kPa | 4.1368543759008 | 0 | measurement | Brake application pressure, converted from J1587 units to kPa. An all-ones unavailable value is reported as null. |
| 117 | Primary brake air pressure | 1 | False | kPa | 4.1368543759008 | 0 | measurement | Primary brake air pressure, converted from J1587 units to kPa. An all-ones unavailable value is reported as null. |
| 118 | Secondary brake air pressure | 1 | False | kPa | 4.1368543759008 | 0 | measurement | Secondary brake air pressure, converted from J1587 units to kPa. An all-ones unavailable value is reported as null. |
| 120 | Retarder oil temperature | 1 | False | °C | 1.1111111111111112 | -17.77777777777778 | measurement | Retarder oil temperature, converted from J1587 units to °C. An all-ones unavailable value is reported as null. |
| 122 | Retarder torque percentage | 1 | False | % | 0.5 | 0 | measurement | Retarder torque percentage, converted from J1587 units to %. An all-ones unavailable value is reported as null. |
| 168 | Electrical system voltage | 2 | False | V | 0.05 | 0 | measurement | Electrical system voltage, converted from J1587 units to V. An all-ones unavailable value is reported as null. |
| 171 | Ambient air temperature | 2 | False | °C | 0.1388888888888889 | -17.77777777777778 | measurement | Ambient air temperature, converted from J1587 units to °C. An all-ones unavailable value is reported as null. |
| 172 | Engine air intake temperature | 2 | False | °C | 0.1388888888888889 | -17.77777777777778 | measurement | Engine air intake temperature, converted from J1587 units to °C. An all-ones unavailable value is reported as null. |
| 173 | Exhaust gas temperature | 2 | False | °C | 0.1388888888888889 | -17.77777777777778 | measurement | Exhaust gas temperature, converted from J1587 units to °C. An all-ones unavailable value is reported as null. |
| 175 | Engine oil temperature | 2 | False | °C | 0.1388888888888889 | -17.77777777777778 | measurement | Engine oil temperature, converted from J1587 units to °C. An all-ones unavailable value is reported as null. |
| 177 | Transmission oil temperature | 2 | False | °C | 0.1388888888888889 | -17.77777777777778 | measurement | Transmission oil temperature, converted from J1587 units to °C. An all-ones unavailable value is reported as null. |
| 183 | Fuel rate | 2 | False | L/h | 0.059147059125 | 0 | measurement | Fuel rate, converted from J1587 units to L/h. An all-ones unavailable value is reported as null. |
| 184 | Instantaneous fuel economy | 2 | False | km/L | 0.0016607176071495 | 0 | measurement | Instantaneous fuel economy, converted from J1587 units to km/L. An all-ones unavailable value is reported as null. |
| 185 | Average fuel economy | 2 | False | km/L | 0.0016607176071495 | 0 | measurement | Average fuel economy, converted from J1587 units to km/L. An all-ones unavailable value is reported as null. |
| 190 | Engine speed | 2 | False | rpm | 0.25 | 0 | measurement | Engine speed, converted from J1587 units to rpm. An all-ones unavailable value is reported as null. |
| 235 | Engine idle hours | 4 | False | h | 0.05 | 0 | total_increasing | Engine idle hours, converted from J1587 units to h. An all-ones unavailable value is reported as null. |
| 236 | Engine idle fuel used | 4 | False | L | 0.473176473 | 0 | total_increasing | Engine idle fuel used, converted from J1587 units to L. An all-ones unavailable value is reported as null. |
| 245 | Total vehicle distance | 4 | False | km | 0.1609344 | 0 | total_increasing | Total vehicle distance, converted from J1587 units to km. An all-ones unavailable value is reported as null. |
| 247 | Total engine hours | 4 | False | h | 0.05 | 0 | total_increasing | Total engine hours, converted from J1587 units to h. An all-ones unavailable value is reported as null. |
| 250 | Total fuel used | 4 | False | L | 0.473176473 | 0 | total_increasing | Total fuel used, converted from J1587 units to L. An all-ones unavailable value is reported as null. |
| 439 | Extended intake manifold pressure | 2 | False | kPa | 0.125 | 0 | measurement | Extended intake manifold pressure, converted from J1587 units to kPa. An all-ones unavailable value is reported as null. |

J1587 provenance: Local Windows BlueFire 12.5.6 J1708 parameter scaling cross-check, including unsigned quarter-degree Fahrenheit temperatures and signed crankcase pressure; independent native-unit conversions. Datalink/diagnostic structure: https://github.com/ainfosec/pretty_j1587

## J1587 status and read-only request support

Switch and cruise values are one-byte bitfields; gear values are two printable ASCII characters. These are unitless sensors, not commands or numeric quantities. All-ones is unavailable; unsupported gear encodings retain raw bytes and a null value. Cruise status includes enabled/set/coast/resume/accelerate/brake/clutch/active attributes.

| PID | Label | Value bytes | Encoding |
| --- | --- | --- | --- |
| 40 | Retarder switch | 1 | switch |
| 70 | Parking brake status | 1 | switch |
| 85 | Cruise control status | 1 | cruise |
| 162 | Transmission selected gear | 2 | gear |
| 163 | Transmission current gear | 2 | gear |

The `bluefire.read_parameter` action accepts only these PIDs: 26, 40, 51, 68, 70, 74, 84, 85, 86, 91, 92, 94, 96, 100, 101, 102, 105, 108, 109, 110, 111, 116, 117, 118, 120, 122, 162, 163, 168, 171, 172, 173, 174, 175, 177, 183, 184, 185, 190, 194, 234, 235, 236, 237, 243, 245, 247, 250, 439.

Requests collect for five seconds and optionally target MID 128–255 (zero/omitted means wildcard). PID 174 fuel temperature is raw-only: Prevost documents the installed sensor, but the inspected vendor decoder does not establish its scale. The automatic poll set remains 96, 194, 245, 247 and 250; additional reads are manual only. No fault clearing, programming, arbitrary requests or actuator tests are exposed.

## Standard code labels

For J1587 PID lookups, units mean preferred display units only; an actual conversion is implemented only for the decoded subset above. Faults do not carry measurement units. OBD labels are mode-specific and do not imply an OBD value decoder.

### PGN

| Code / ID | Label string | Unit | Description | Reference |
| --- | --- | --- | --- | --- |
| 59904 | Parameter group request | - | Parameter group request | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 60160 | Transport protocol data transfer | - | Transport protocol data transfer | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 60416 | Transport protocol connection management | - | Transport protocol connection management | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 60928 | Address claim | - | Address claim | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 61443 | Electronic engine controller 2 | - | Electronic engine controller 2 | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 61444 | Electronic engine controller 1 | - | Electronic engine controller 1 | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 65226 | Active diagnostic faults | - | Active diagnostic faults | https://www.csselectronics.com/pages/j1939-73-dm1-diagnostic-message-dtc |
| 65227 | Previously active diagnostic faults | - | Previously active diagnostic faults | https://www.csselectronics.com/pages/j1939-73-dm1-diagnostic-message-dtc |
| 65244 | Engine idle operation | - | Engine idle operation | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 65248 | Vehicle distance | - | Vehicle distance | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 65253 | Engine hours and revolutions | - | Engine hours and revolutions | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 65257 | Fuel consumption | - | Fuel consumption | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 65262 | Engine temperature | - | Engine temperature | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 65263 | Engine fluid levels and pressures | - | Engine fluid levels and pressures | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 65265 | Cruise control and vehicle speed | - | Cruise control and vehicle speed | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 65266 | Fuel economy | - | Fuel economy | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 65269 | Ambient conditions | - | Ambient conditions | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 65270 | Engine inlet and exhaust conditions | - | Engine inlet and exhaust conditions | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 65271 | Vehicle electrical power | - | Vehicle electrical power | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 65272 | Transmission fluids | - | Transmission fluids | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 65276 | Vehicle fluids | - | Vehicle fluids | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |

### SPN

| Code / ID | Label string | Unit | Description | Reference |
| --- | --- | --- | --- | --- |
| 52 | Engine intercooler temperature | °C | Engine intercooler temperature | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 84 | Wheel-based vehicle speed | km/h | Wheel-based vehicle speed | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 91 | Accelerator pedal position | % | Accelerator pedal position | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 92 | Engine load | % | Engine load | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 94 | Engine fuel delivery pressure | kPa | Engine fuel delivery pressure | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 96 | Fuel level | % | Fuel level | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 98 | Engine oil level | % | Engine oil level | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 100 | Engine oil pressure | kPa | Engine oil pressure | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 102 | Intake manifold pressure | kPa | Intake manifold pressure | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 105 | Intake manifold temperature | °C | Intake manifold temperature | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 106 | Air inlet pressure | kPa | Air inlet pressure | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 107 | Air filter differential pressure | kPa | Air filter differential pressure | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 108 | Barometric pressure | kPa | Barometric pressure | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 109 | Engine coolant pressure | kPa | Engine coolant pressure | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 110 | Engine coolant temperature | °C | Engine coolant temperature | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 111 | Engine coolant level | % | Engine coolant level | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 116 | Brake application pressure | - | Brake application pressure | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 117 | Primary brake air pressure | - | Primary brake air pressure | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 118 | Secondary brake air pressure | - | Secondary brake air pressure | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 120 | Retarder oil temperature | - | Retarder oil temperature | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 124 | Transmission oil level | % | Transmission oil level | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 126 | Transmission filter differential pressure | kPa | Transmission filter differential pressure | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 127 | Transmission oil pressure | kPa | Transmission oil pressure | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 167 | Charging system potential | V | Charging system potential | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 168 | Battery potential | V | Battery potential | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 171 | Ambient air temperature | °C | Ambient air temperature | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 172 | Engine air intake temperature | °C | Engine air intake temperature | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 173 | Exhaust gas temperature | °C | Exhaust gas temperature | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 174 | Engine fuel temperature | °C | Engine fuel temperature | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 175 | Engine oil temperature | °C | Engine oil temperature | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 176 | Engine turbocharger oil temperature | °C | Engine turbocharger oil temperature | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 177 | Transmission oil temperature | °C | Transmission oil temperature | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 182 | Engine trip fuel used | L | Engine trip fuel used | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 183 | Engine fuel rate | L/h | Engine fuel rate | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 190 | Engine speed | rpm | Engine speed | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 235 | Engine total idle hours | h | Engine total idle hours | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 236 | Engine total idle fuel used | L | Engine total idle fuel used | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 245 | Total vehicle distance | km | Total vehicle distance | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 247 | Engine total hours | h | Engine total hours | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 250 | Engine total fuel used | L | Engine total fuel used | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 513 | Actual engine torque | % | Actual engine torque | https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns |
| 623 | Red stop lamp | - | Red stop lamp | https://www.csselectronics.com/pages/j1939-73-dm1-diagnostic-message-dtc |
| 624 | Amber warning lamp | - | Amber warning lamp | https://www.csselectronics.com/pages/j1939-73-dm1-diagnostic-message-dtc |
| 987 | Protect lamp | - | Protect lamp | https://www.csselectronics.com/pages/j1939-73-dm1-diagnostic-message-dtc |
| 1213 | Malfunction indicator lamp | - | Malfunction indicator lamp | https://www.csselectronics.com/pages/j1939-73-dm1-diagnostic-message-dtc |

### SOURCE

| Code / ID | Label string | Unit | Description | Reference |
| --- | --- | --- | --- | --- |
| 0 | Engine | - | Engine | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 1 | Engine 2 | - | Engine 2 | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 3 | Transmission | - | Transmission | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 11 | Brakes | - | Brakes | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 15 | Retarder | - | Retarder | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 17 | Cruise control | - | Cruise control | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 23 | Instrument cluster | - | Instrument cluster | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 25 | Climate control | - | Climate control | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 33 | Body controller | - | Body controller | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 49 | Cab controller | - | Cab controller | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 51 | Tire pressure monitor | - | Tire pressure monitor | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 61 | Exhaust system | - | Exhaust system | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 85 | Aftertreatment | - | Aftertreatment | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 254 | Null address | - | Null address | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 255 | Global address | - | Global address | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |

### MID

| Code / ID | Label string | Unit | Description | Reference |
| --- | --- | --- | --- | --- |
| 128 | Engine | - | Engine | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 130 | Transmission | - | Transmission | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 136 | Brakes | - | Brakes | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 140 | Instrument cluster | - | Instrument cluster | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 142 | Vehicle management | - | Vehicle management | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 146 | Climate control | - | Climate control | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 171 | Driver information | - | Driver information | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 249 | Body controller | - | Body controller | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |

### PID

| Code / ID | Label string | Unit | Description | Reference |
| --- | --- | --- | --- | --- |
| 26 | Fan speed percentage | % | Fan speed percentage | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 40 | Retarder switch | - | Retarder switch | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 51 | Throttle position | % | Throttle position | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 68 | Engine torque factor | % | Engine torque factor | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 70 | Parking brake status | - | Parking brake status | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 73 | External pump pressure | - | External pump pressure | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/405602.html |
| 74 | Maximum road speed | km/h | Maximum road speed | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 81 | Exhaust back pressure | - | Exhaust back pressure | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404d02.html |
| 84 | Vehicle speed | km/h | Vehicle speed | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 85 | Cruise control status | - | Cruise control status | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 86 | Cruise set speed | km/h | Cruise set speed | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 91 | Accelerator pedal position | % | Accelerator pedal position | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 92 | Engine load | % | Engine load | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 93 | Actual engine torque | % | Actual engine torque | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 94 | Fuel delivery pressure | kPa | Fuel delivery pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 95 | Fuel inlet restriction | - | Fuel inlet restriction | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402502.html |
| 96 | Fuel level | % | Fuel level | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 98 | Engine oil level | - | Engine oil level | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/405102.html |
| 99 | Oil filter restriction | - | Oil filter restriction | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404202.html |
| 100 | Engine oil pressure | kPa | Engine oil pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 101 | Crankcase pressure | kPa | Crankcase pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 102 | Intake manifold pressure | kPa | Intake manifold pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 103 | Turbocharger speed | - | Turbocharger speed | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404002.html |
| 105 | Intake manifold temperature | °C | Intake manifold temperature | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 106 | Air inlet pressure | - | Air inlet pressure | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402f02.html |
| 107 | Air filter restriction | - | Air filter restriction | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404102.html |
| 108 | Barometric pressure | kPa | Barometric pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 109 | Coolant pressure | kPa | Coolant pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 110 | Coolant temperature | °C | Coolant temperature | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 111 | Coolant level | % | Coolant level | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 116 | Brake application pressure | kPa | Brake application pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 117 | Primary brake air pressure | kPa | Primary brake air pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 118 | Secondary brake air pressure | kPa | Secondary brake air pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 120 | Retarder oil temperature | °C | Retarder oil temperature | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 121 | Engine retarder status | - | Engine retarder status | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 122 | Retarder torque percentage | % | Retarder torque percentage | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 154 | Legacy EGR temperature | - | Legacy EGR temperature | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403002.html |
| 155 | Legacy EGR differential pressure | - | Legacy EGR differential pressure | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403002.html |
| 162 | Transmission selected gear | - | Transmission selected gear | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 163 | Transmission current gear | - | Transmission current gear | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 168 | Electrical system voltage | V | Electrical system voltage | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 171 | Ambient air temperature | °C | Ambient air temperature | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 172 | Engine air intake temperature | °C | Engine air intake temperature | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 173 | Exhaust gas temperature | °C | Exhaust gas temperature | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 174 | Fuel temperature | °C | Fuel temperature | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 175 | Engine oil temperature | °C | Engine oil temperature | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 177 | Transmission oil temperature | °C | Transmission oil temperature | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 183 | Fuel rate | L/h | Fuel rate | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 184 | Instantaneous fuel economy | km/L | Instantaneous fuel economy | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 185 | Average fuel economy | km/L | Average fuel economy | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 187 | Variable speed governor input | - | Variable speed governor input | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/400b02.html |
| 190 | Engine speed | rpm | Engine speed | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 192 | Multisection parameter | - | Multisection parameter | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 194 | Diagnostic trouble codes | - | Diagnostic trouble codes | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 195 | Diagnostic clearing request | - | Diagnostic clearing request | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 196 | Diagnostic clearing response | - | Diagnostic clearing response | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 222 | Anti-theft status | - | Anti-theft status | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404d02.html |
| 234 | Software identification | - | Software identification | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 235 | Engine idle hours | h | Engine idle hours | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 236 | Engine idle fuel used | L | Engine idle fuel used | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 237 | Vehicle identification | - | Vehicle identification | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 243 | Component identification | - | Component identification | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 245 | Total vehicle distance | km | Total vehicle distance | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 247 | Total engine hours | h | Total engine hours | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 250 | Total fuel used | L | Total fuel used | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 251 | Clock module | - | Clock module | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404d02.html |
| 252 | Clock module extension | - | Clock module extension | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404d02.html |
| 351 | Turbo compressor inlet temperature | - | Turbo compressor inlet temperature | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401d02.html |
| 354 | Relative humidity | - | Relative humidity | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401102.html |
| 404 | Turbo compressor outlet temperature | - | Turbo compressor outlet temperature | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401d02.html |
| 411 | EGR differential pressure | - | EGR differential pressure | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403002.html |
| 412 | EGR temperature | - | EGR temperature | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403002.html |
| 439 | Extended intake manifold pressure | kPa | Extended intake manifold pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |

### FMI

These FMI values apply to J1939. J1587 uses the separate four-bit table below.

| Code / ID | Label string | Unit | Description | Reference |
| --- | --- | --- | --- | --- |
| 0 | Above normal range (most severe) | - | Above normal range (most severe) | https://j1939hub.com/fmi-decoder/ |
| 1 | Below normal range (most severe) | - | Below normal range (most severe) | https://j1939hub.com/fmi-decoder/ |
| 2 | Erratic, intermittent or incorrect data | - | Erratic, intermittent or incorrect data | https://j1939hub.com/fmi-decoder/ |
| 3 | Voltage high or short to high supply | - | Voltage high or short to high supply | https://j1939hub.com/fmi-decoder/ |
| 4 | Voltage low or short to low supply | - | Voltage low or short to low supply | https://j1939hub.com/fmi-decoder/ |
| 5 | Current low or open circuit | - | Current low or open circuit | https://j1939hub.com/fmi-decoder/ |
| 6 | Current high or grounded circuit | - | Current high or grounded circuit | https://j1939hub.com/fmi-decoder/ |
| 7 | Mechanical system not responding correctly | - | Mechanical system not responding correctly | https://j1939hub.com/fmi-decoder/ |
| 8 | Abnormal frequency, pulse width or period | - | Abnormal frequency, pulse width or period | https://j1939hub.com/fmi-decoder/ |
| 9 | Abnormal update rate | - | Abnormal update rate | https://j1939hub.com/fmi-decoder/ |
| 10 | Abnormal rate of change | - | Abnormal rate of change | https://j1939hub.com/fmi-decoder/ |
| 11 | Root cause not identified | - | Root cause not identified | https://j1939hub.com/fmi-decoder/ |
| 12 | Faulty intelligent device or component | - | Faulty intelligent device or component | https://j1939hub.com/fmi-decoder/ |
| 13 | Calibration required | - | Calibration required | https://j1939hub.com/fmi-decoder/ |
| 14 | Special instructions required | - | Special instructions required | https://j1939hub.com/fmi-decoder/ |
| 15 | Above normal range (least severe) | - | Above normal range (least severe) | https://j1939hub.com/fmi-decoder/ |
| 16 | Above normal range (moderately severe) | - | Above normal range (moderately severe) | https://j1939hub.com/fmi-decoder/ |
| 17 | Below normal range (least severe) | - | Below normal range (least severe) | https://j1939hub.com/fmi-decoder/ |
| 18 | Below normal range (moderately severe) | - | Below normal range (moderately severe) | https://j1939hub.com/fmi-decoder/ |
| 19 | Received network data contains an error | - | Received network data contains an error | https://j1939hub.com/fmi-decoder/ |
| 20 | Data drifted high | - | Data drifted high | https://j1939hub.com/fmi-decoder/ |
| 21 | Data drifted low | - | Data drifted low | https://j1939hub.com/fmi-decoder/ |
| 22 | Reserved failure mode | - | Reserved failure mode | https://j1939hub.com/fmi-decoder/ |
| 23 | Reserved failure mode | - | Reserved failure mode | https://j1939hub.com/fmi-decoder/ |
| 24 | Reserved failure mode | - | Reserved failure mode | https://j1939hub.com/fmi-decoder/ |
| 25 | Reserved failure mode | - | Reserved failure mode | https://j1939hub.com/fmi-decoder/ |
| 26 | Reserved failure mode | - | Reserved failure mode | https://j1939hub.com/fmi-decoder/ |
| 27 | Reserved failure mode | - | Reserved failure mode | https://j1939hub.com/fmi-decoder/ |
| 28 | Reserved failure mode | - | Reserved failure mode | https://j1939hub.com/fmi-decoder/ |
| 29 | Reserved failure mode | - | Reserved failure mode | https://j1939hub.com/fmi-decoder/ |
| 30 | Reserved failure mode | - | Reserved failure mode | https://j1939hub.com/fmi-decoder/ |
| 31 | Condition exists | - | Condition exists | https://j1939hub.com/fmi-decoder/ |

### COMMAND

| Code / ID | Label string | Unit | Description | Reference |
| --- | --- | --- | --- | --- |
| 7 | J1708 availability | - | J1708 availability | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 151 | J1939 parameter group report | - | J1939 parameter group report | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 154 | J1587 parameter report | - | J1587 parameter report | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 169 | Authentication | - | Authentication | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 174 | OBD report | - | OBD report | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 177 | Firmware/build date response (app-version dependent) | - | Firmware/build date response (app-version dependent) | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 201 | Arbitration identifier response | - | Arbitration identifier response | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 255 | Heartbeat | - | Heartbeat | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |

### OBD_PID

| Code / ID | Label string | Unit | Description | Reference |
| --- | --- | --- | --- | --- |
| 01:05 | Engine coolant temperature | °C | Engine coolant temperature | https://www.csselectronics.com/pages/obd2-pid-table-on-board-diagnostics-j1979 |
| 01:0C | Engine speed | rpm | Engine speed | https://www.csselectronics.com/pages/obd2-pid-table-on-board-diagnostics-j1979 |
| 01:0D | Vehicle speed | km/h | Vehicle speed | https://www.csselectronics.com/pages/obd2-pid-table-on-board-diagnostics-j1979 |
| 01:0F | Intake air temperature | °C | Intake air temperature | https://www.csselectronics.com/pages/obd2-pid-table-on-board-diagnostics-j1979 |
| 01:10 | Mass air flow | g/s | Mass air flow | https://www.csselectronics.com/pages/obd2-pid-table-on-board-diagnostics-j1979 |
| 01:11 | Throttle position | % | Throttle position | https://www.csselectronics.com/pages/obd2-pid-table-on-board-diagnostics-j1979 |

## J1587 failure modes

| FMI | Description |
| --- | --- |
| 0 | Above normal range (most severe) |
| 1 | Below normal range (most severe) |
| 2 | Erratic, intermittent or incorrect data |
| 3 | Voltage high or short to high supply |
| 4 | Voltage low or short to low supply |
| 5 | Current low or open circuit |
| 6 | Current high or grounded circuit |
| 7 | Mechanical system not responding correctly |
| 8 | Abnormal frequency, pulse width or period |
| 9 | Abnormal update rate |
| 10 | Abnormal rate of change |
| 11 | Failure mode not identifiable |
| 12 | Faulty intelligent device or component |
| 13 | Calibration required |
| 14 | Special instructions required |
| 15 | Reserved failure mode |

## J1939 diagnostic lamp strings

Lamp status and flash are separate two-bit fields, shared by the report rather than assigned to individual DTCs.

| Code | Status string | Flash string |
| --- | --- | --- |
| 0 | Off | Slow flash |
| 1 | On | Fast flash |
| 2 | Reserved | Reserved |
| 3 | Unavailable | Unavailable |

Lamp provenance: https://www.csselectronics.com/pages/j1939-73-dm1-diagnostic-message-dtc

## Manufacturer-scoped references

Codes are matched only inside the specified profile/namespace. PID/SID equivalents are J1587 codes, not J1939 SPNs. No Allison selector-to-SPN or P-code translation is inferred.

### Detroit Diesel DDEC III/IV (`detroit_ddec_iii_iv`)

DDEC III/IV single-ECM reference (6SE497). The coach's official labels and Prevost PA1163 identify its 500 HP Series 60 and DDEC IV; select the confirmed engine profile in configuration. Other installations remain standard J1587 unless selected.

All 66 flash-code sections indexed by the referenced 6SE497 edition, with independently summarized labels and verified equivalents. Conflicting/ambiguous crosswalks are withheld, not guessed. Gas, EGR, ESS, Optimized Idle and optional sensor references do not establish installed equipment or calibration.

| Namespace | Code | Label / description | J1587 equivalents (code / FMI) | Applicability / exceptions | Reference |
| --- | --- | --- | --- | --- | --- |
| detroit_flash | 11 | Variable speed governor input voltage low | PID 187 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/400b02.html |
| detroit_flash | 12 | Variable speed governor input voltage high | PID 187 / 3 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/400c02.html |
| detroit_flash | 13 | Coolant level sensor circuit low | PID 111 / 4, PID 111 / 6 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/400d02.html |
| detroit_flash | 14 | Coolant or oil temperature sensor circuit high | PID 110 / 3, PID 175 / 3 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/400e02.html |
| detroit_flash | 15 | Coolant or oil temperature sensor circuit low | PID 110 / 4, PID 175 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/400f02.html |
| detroit_flash | 16 | Coolant level sensor circuit high | PID 111 / 3, PID 111 / 5 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401002.html |
| detroit_flash | 17 | Throttle plate or humidity input voltage high | PID 51 / 3, PID 354 / 3 | Application-dependent sensors | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401102.html |
| detroit_flash | 18 | Throttle plate or humidity input voltage low | PID 51 / 4, PID 354 / 4 | Application-dependent sensors | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401202.html |
| detroit_flash | 21 | Throttle position sensor circuit high | PID 91 / 3 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401502.html |
| detroit_flash | 22 | Throttle position sensor circuit low | PID 91 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401602.html |
| detroit_flash | 23 | Fuel temperature sensor circuit high | PID 174 / 3 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401702.html |
| detroit_flash | 24 | Fuel temperature sensor circuit low | PID 174 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401802.html |
| detroit_flash | 26 | Auxiliary engine shutdown input active | SID 25 / 11, SID 61 / 11 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401a02.html |
| detroit_flash | 27 | Air inlet temperature input voltage high | PID 172 / 3 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401b02.html |
| detroit_flash | 28 | Air inlet temperature input voltage low | PID 172 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401c02.html |
| detroit_flash | 29 | Turbo compressor temperature input voltage low | PID 351 / 4, PID 404 / 4 | Optional turbo/EGR sensors | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401d02.html |
| detroit_flash | 31 | Engine brake output circuit fault | SID 51 / 3, SID 51 / 4, SID 52 / 3, SID 52 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401f02.html |
| detroit_flash | 32 | Stop or check engine lamp circuit fault | SID 238 / 3, SID 238 / 4, SID 239 / 3, SID 239 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402002.html |
| detroit_flash | 33 | Boost pressure input voltage high | PID 102 / 3 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402102.html |
| detroit_flash | 34 | Boost pressure input voltage low | PID 102 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402202.html |
| detroit_flash | 35 | Oil pressure input voltage high | PID 100 / 3 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402302.html |
| detroit_flash | 36 | Oil pressure input voltage low | PID 100 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402402.html |
| detroit_flash | 37 | Fuel pressure or restriction input voltage high | PID 94 / 3, PID 95 / 3 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402502.html |
| detroit_flash | 38 | Fuel pressure or restriction input voltage low | PID 94 / 4, PID 95 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402602.html |
| detroit_flash | 39 | EGR valve or variable-nozzle turbo response fault | SID 146 / 2, SID 146 / 12, SID 146 / 7, SID 152 / 7, SID 147 / 2, SID 147 / 12, SID 147 / 14, SID 147 / 11, SID 147 / 7, SID 153 / 7 | EGR/VNT applications only; not assumed installed | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402702.html |
| detroit_flash | 41 | Missing timing reference or extra synchronous pulses | SID 21 / 0 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402902.html |
| detroit_flash | 42 | Missing synchronous reference or extra timing pulses | SID 21 / 1 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402a02.html |
| detroit_flash | 43 | Coolant level below normal | PID 111 / 1 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402b02.html |
| detroit_flash | 44 | Coolant or engine oil temperature above normal | PID 110 / 0, PID 175 / 0 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402c02.html |
| detroit_flash | 45 | Engine oil pressure below normal | PID 100 / 1 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402d02.html |
| detroit_flash | 46 | ECM battery supply voltage low | PID 168 / 1 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402e02.html |
| detroit_flash | 47 | Fuel, boost or gas-engine inlet pressure above range | PID 94 / 0, PID 102 / 0, PID 106 / 0 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402f02.html |
| detroit_flash | 48 | Fuel pressure or optional inlet/EGR data below range | PID 94 / 1, PID 106 / 1, PID 412 / 1, PID 154 / 1, PID 411 / 1, PID 155 / 1, PID 351 / 1, PID 404 / 1 | EGR PID numbering depends on ECM software | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403002.html |
| detroit_flash | 49 | Turbo compressor temperature above range or derate | PID 351 / 0, PID 404 / 0, PID 404 / 14 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403102.html |
| detroit_flash | 51 | Turbo compressor temperature input voltage high | PID 351 / 3, PID 404 / 3 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403302.html |
| detroit_flash | 52 | ECM analog-to-digital conversion fault | SID 254 / 12 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403402.html |
| detroit_flash | 53 | Engine controller nonvolatile memory error | SID 253 / 12, SID 253 / 2 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403502.html |
| detroit_flash | 54 | Vehicle speed signal fault | PID 84 / 12 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403602.html |
| detroit_flash | 55 | J1939 link or other-controller communication fault | SID 231 / 12, SID 216 / 14 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403702.html |
| detroit_flash | 56 | J1587 diagnostic data link fault | SID 250 / 12 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403802.html |
| detroit_flash | 57 | J1922 data link fault | SID 249 / 12 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403902.html |
| detroit_flash | 58 | Engine torque overload | PID 92 / 0 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403a02.html |
| detroit_flash | 61 | Injector response too slow | SID 1 / 0, SID 2 / 0, SID 3 / 0, SID 4 / 0, SID 5 / 0, SID 6 / 0 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403d02.html |
| detroit_flash | 62 | Auxiliary output open or short to supply | SID 26 / 3, SID 26 / 4, SID 40 / 3, SID 40 / 4, SID 53 / 3, SID 53 / 4, SID 54 / 3, SID 54 / 4, SID 55 / 3, SID 55 / 4, SID 56 / 3, SID 56 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403e02.html |
| detroit_flash | 63 | PWM output open or short to supply | SID 57 / 3, SID 57 / 4, SID 58 / 3, SID 58 / 4, SID 59 / 3, SID 59 / 4, SID 60 / 3, SID 60 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403f02.html |
| detroit_flash | 64 | Turbo speed excessive or speed sensor failure | PID 103 / 0, PID 103 / 8 | Turbo speed sensor required | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404002.html |
| detroit_flash | 65 | Air filter sensor or gas-engine throttle response fault | PID 107 / 3, PID 107 / 4, PID 51 / 0, PID 51 / 1, PID 51 / 7 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404102.html |
| detroit_flash | 66 | Oil filter sensor or gas-engine knock sensor fault | PID 99 / 3, PID 99 / 4, SID 76 / 0, SID 76 / 7, SID 76 / 3, SID 76 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404202.html |
| detroit_flash | 67 | Coolant pressure or gas-engine inlet pressure circuit fault | PID 109 / 3, PID 109 / 4, PID 106 / 3, PID 106 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404302.html |
| detroit_flash | 68 | Throttle idle-validation circuit fault | SID 230 / 5, SID 230 / 6 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404402.html |
| detroit_flash | 71 | Injector response too fast | SID 1 / 1, SID 2 / 1, SID 3 / 1, SID 4 / 1, SID 5 / 1, SID 6 / 1 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404702.html |
| detroit_flash | 72 | Vehicle overspeed | PID 84 / 0, PID 84 / 11 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404802.html |
| detroit_flash | 73 | Air restriction, ESS shift input or gas valve fault | SID 227 / 2, SID 227 / 3, SID 227 / 4, SID 226 / 11, SID 151 / 14, SID 77 / 0, SID 77 / 1, SID 77 / 3, SID 77 / 4 | ESS/gas options are not assumed. Air restriction 107/0 is omitted: 6SE497 says SID, 7SA743 Appendix A says PID. | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404902.html |
| detroit_flash | 74 | Optimized Idle interlock or oil filter restriction fault | - | Equivalence withheld: 6SE497 reports PID 70/4 and an Optimized Idle interlock; 7SA743 reports PID 99/0. Select the applicable calibration/service reference. | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404a02.html |
| detroit_flash | 75 | ECM battery supply voltage high | PID 168 / 0 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404b02.html |
| detroit_flash | 76 | Engine overspeed with engine brake | PID 121 / 0 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404c02.html |
| detroit_flash | 77 | Application-specific range, clock or anti-theft fault | PID 73 / 1, PID 81 / 0, PID 81 / 1, PID 81 / 12, PID 81 / 3, PID 81 / 4, PID 95 / 1, PID 99 / 1, PID 100 / 0, PID 102 / 1, PID 105 / 1, PID 107 / 1, PID 108 / 0, PID 108 / 1, PID 109 / 0, PID 110 / 1, PID 111 / 0, PID 171 / 0, PID 171 / 1, PID 172 / 1, PID 175 / 1, PID 222 / 14, PID 251 / 10, PID 251 / 13, PID 252 / 10, PID 252 / 13, PID 354 / 0, PID 354 / 1 | Many entries are not on-highway Series 60 features. PID 174/0 and 174/1 withheld: the guide assigns both fuel temperature and temporary TCO meanings. | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404d02.html |
| detroit_flash | 78 | Cruise or adaptive-cruise system fault | PID 86 / 14 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404e02.html |
| detroit_flash | 81 | Oil level or exhaust/EGR sensor input voltage high | PID 98 / 3, PID 173 / 3 | EGR equivalents withheld because the source editions disagree on PID/SID namespace and legacy numbering. | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/405102.html |
| detroit_flash | 82 | Oil level or exhaust/EGR sensor input voltage low | PID 98 / 4, PID 173 / 4 | EGR crosswalk withheld; see flash 81 notes | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/405202.html |
| detroit_flash | 83 | Exhaust temperature, pump pressure or EGR value high | PID 173 / 0, PID 73 / 0 | EGR crosswalk withheld; see flash 81 notes | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/405302.html |
| detroit_flash | 84 | Engine oil level low | PID 98 / 1 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/405402.html |
| detroit_flash | 85 | Engine overspeed | PID 190 / 0 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/405502.html |
| detroit_flash | 86 | External pump pressure input voltage high | PID 73 / 3 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/405602.html |
| detroit_flash | 87 | External pump pressure input voltage low | PID 73 / 4 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/405702.html |
| detroit_flash | 89 | Fuel restriction or maintenance coolant-level fault | PID 95 / 0, PID 111 / 12 | - | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/405902.html |

### Allison B500 with WTEC III controls (`allison_wtec_iii`)

B500 only when WTEC III controls are confirmed. Not WTEC II or Allison 4th/5th-generation P-codes; no automatic selection.

Curated two-part selector codes, not all calibrations.

| Namespace | Code | Label / description | J1587 equivalents (code / FMI) | Applicability / exceptions | Reference |
| --- | --- | --- | --- | --- | --- |
| allison_wtec | 13-12 | Transmission controller supply voltage low | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 13-13 | Transmission controller supply voltage moderately low | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 13-23 | Transmission controller supply voltage high | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 14-12 | Transmission oil level sensor signal low | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 14-23 | Transmission oil level sensor signal high | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 21-12 | Transmission throttle position signal low | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 21-23 | Transmission throttle position signal high | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 22-14 | Transmission engine speed sensor fault | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 22-15 | Transmission turbine speed sensor fault | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 22-16 | Transmission output speed sensor fault | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 23-12 | Primary transmission selector fault | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 23-13 | Primary transmission selector mode fault | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 23-14 | Secondary transmission selector fault | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 23-15 | Secondary transmission selector mode fault | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 23-16 | Transmission selector display connection fault | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 24-12 | Transmission sump fluid temperature below range | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 24-23 | Transmission sump fluid temperature above range | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 26-00 | Transmission cannot detect throttle data source | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 26-11 | Transmission cannot detect engine coolant data source | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 33-12 | Transmission sump temperature sensor signal low | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 33-23 | Transmission sump temperature sensor signal high | - | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |

## Controller-scoped SID labels

These require engine MID 128 and the explicit Detroit DDEC III/IV reference profile. Injector/cylinder/bank numbering must be checked against the actual engine manual.

| Profile | MID | SID | Label / description | Reference |
| --- | --- | --- | --- | --- |
| detroit_ddec_iii_iv | 128 | 1 | Engine injector 1 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403d01.html |
| detroit_ddec_iii_iv | 128 | 2 | Engine injector 2 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403d01.html |
| detroit_ddec_iii_iv | 128 | 3 | Engine injector 3 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403d01.html |
| detroit_ddec_iii_iv | 128 | 4 | Engine injector 4 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403d01.html |
| detroit_ddec_iii_iv | 128 | 5 | Engine injector 5 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403d01.html |
| detroit_ddec_iii_iv | 128 | 6 | Engine injector 6 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403d01.html |
| detroit_ddec_iii_iv | 128 | 21 | Engine timing and synchronous reference sensors | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402902.html |
| detroit_ddec_iii_iv | 128 | 25 | Auxiliary shutdown input 1 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401a02.html |
| detroit_ddec_iii_iv | 128 | 26 | Auxiliary output 1 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403e02.html |
| detroit_ddec_iii_iv | 128 | 40 | Auxiliary output 2 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403e02.html |
| detroit_ddec_iii_iv | 128 | 51 | Engine brake output 1 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401f02.html |
| detroit_ddec_iii_iv | 128 | 52 | Engine brake output 2 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401f02.html |
| detroit_ddec_iii_iv | 128 | 53 | Auxiliary output 5 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403e02.html |
| detroit_ddec_iii_iv | 128 | 54 | Auxiliary output 6 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403e02.html |
| detroit_ddec_iii_iv | 128 | 55 | Auxiliary output 7 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403e02.html |
| detroit_ddec_iii_iv | 128 | 56 | Auxiliary output 8 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403e02.html |
| detroit_ddec_iii_iv | 128 | 57 | PWM output 1 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403f02.html |
| detroit_ddec_iii_iv | 128 | 58 | PWM output 2 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403f02.html |
| detroit_ddec_iii_iv | 128 | 59 | PWM output 3 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403f02.html |
| detroit_ddec_iii_iv | 128 | 60 | PWM output 4 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403f02.html |
| detroit_ddec_iii_iv | 128 | 61 | Auxiliary shutdown input 2 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401a02.html |
| detroit_ddec_iii_iv | 128 | 76 | Gas-engine knock sensor | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404202.html |
| detroit_ddec_iii_iv | 128 | 77 | Gas metering valve | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404902.html |
| detroit_ddec_iii_iv | 128 | 146 | EGR valve | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402702.html |
| detroit_ddec_iii_iv | 128 | 147 | Variable-nozzle turbo vanes | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402702.html |
| detroit_ddec_iii_iv | 128 | 151 | ESS transmission gear state | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404902.html |
| detroit_ddec_iii_iv | 128 | 152 | Legacy EGR valve response | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402702.html |
| detroit_ddec_iii_iv | 128 | 153 | Legacy turbo vane response | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402702.html |
| detroit_ddec_iii_iv | 128 | 216 | Other-controller communications | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403702.html |
| detroit_ddec_iii_iv | 128 | 226 | ESS neutral switch | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404902.html |
| detroit_ddec_iii_iv | 128 | 227 | ESS shift knob | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404902.html |
| detroit_ddec_iii_iv | 128 | 230 | Throttle idle-validation switch | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/404402.html |
| detroit_ddec_iii_iv | 128 | 231 | J1939 data link | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403702.html |
| detroit_ddec_iii_iv | 128 | 238 | Stop engine lamp circuit | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402002.html |
| detroit_ddec_iii_iv | 128 | 239 | Check engine lamp circuit | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402002.html |
| detroit_ddec_iii_iv | 128 | 249 | J1922 data link | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403902.html |
| detroit_ddec_iii_iv | 128 | 250 | J1587 data link | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403802.html |
| detroit_ddec_iii_iv | 128 | 253 | Engine controller nonvolatile memory | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403501.html |
| detroit_ddec_iii_iv | 128 | 254 | ECM analog-to-digital converter | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403402.html |

## Diagnostic framing and output strings

- J1939 DM1 is PGN 65226 (active); DM2 is PGN 65227 (previously active). Conversion method 0 is decoded. Method 1 is `unsupported_conversion` and has no inferred SPN.
- J1939 decode statuses: `decoded`, `unavailable`, `unsupported_conversion`. All-zero DTC: `No active faults` or `No previously active faults`. All-FF DTC: `Diagnostics unavailable`, never healthy.
- J1587 PID 194: each entry has code, flags/FMI and an optional occurrence byte. Bit 4 selects SID (otherwise PID); bit 5 clear adds 256; bit 6 means inactive; bit 7 includes occurrence count. Low four bits are FMI. Raw bytes and active/inactive status remain in the output.
- J1587 empty diagnostic list: `No faults in this report`, not vehicle-wide health. Otherwise the summary gives active/inactive entry counts. Diagnostic lookup never auto-selects a profile.
- Unknowns: `Unmapped <NAMESPACE> <code>`, `Unidentified controller`; known source labels do not establish hardware identity.

## MQTT mapping

Live measurement and fault states are non-retained. Discovery, availability, last-data timestamps, controller identification and cumulative counters are retained. Identification/counters remain visible as timestamped last-known values without a live availability gate; unavailable reports never overwrite valid retained values. Native controller identification is also persisted locally across HA restarts. Each protocol has independent freshness: live sensors expire after 60 seconds, or 180 seconds for polled J1587 fuel/fault readings. MQTT last-data sensors update at most every 15 seconds and flush the latest observation on disconnect/expiry. The provisional modern EZ BLE receiver is enabled; adapter compatibility remains hardware-unverified. Opt-in unsecured J1708 startup negotiates firmware compatibility, authenticates, subscribes to passive PID reports and enables report flow. Secured adapters are unsupported.

| Meaning | Topic pattern |
| --- | --- |
| J1939 raw frame | vehicle/{vehicle}/j1939/{source}/frame |
| J1939 vendor PGN report | vehicle/{vehicle}/j1939/{source}/report/{pgn} |
| J1939 measurement | vehicle/{vehicle}/j1939/{source}/spn/{spn} |
| J1939 diagnostic report | vehicle/{vehicle}/j1939/{source}/faults/{pgn} |
| J1587 normalized raw parameter | vehicle/{vehicle}/j1587/{mid}/report |
| J1587 measurement | vehicle/{vehicle}/j1587/{mid}/pid/{pid} |
| J1587 diagnostic entries | vehicle/{vehicle}/j1587/{mid}/faults/194 |
| OBD report | vehicle/{vehicle}/obd/{source}/{mode}/{pid} |
| Protocol availability | vehicle/{vehicle}/{j1939-or-j1587}/availability |
