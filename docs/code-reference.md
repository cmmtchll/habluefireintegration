# BlueFire vehicle code reference

[Integration README](../README.md)

Generated from the shared code dictionary. Do not edit tables by hand; update the dictionary and regenerate this file.

```powershell
python .\scripts\catalog_bluefire.py --markdown --output .\docs\code-reference.md
```

Catalog version: **1**. Curated, incomplete; unknown codes are not inferred.

Vehicle context: **2003-era Detroit Diesel, 500 HP, Allison B500**. Year, horsepower and transmission model do not identify the ECM/controller generation or calibration. Profiles below are reference-only and never selected automatically.

J1939 SPNs, J1587 PIDs/SIDs, OBD mode/PIDs, Detroit flash codes and Allison main/subcodes are separate namespaces. A number alone is not enough to identify its meaning. Unknown codes retain their IDs and an explicit unmapped label; no meaning is guessed.

Source-address and MID labels are conventional roles, not verified ECU identities. These are independently worded factual summaries, not a complete service manual or a repair/safety assessment.

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

These independent PID definitions are not J1939 layouts. The parameter value excludes its PID and any variable-parameter byte-count prefix. Engineering value = raw * resolution + offset, rounded to six decimals. All-ones values become null using the observed BlueFire unavailable convention; J1939's upper reserved ranges are not reused.

Native units include mph, psi, degrees Fahrenheit and US gallons. Conversions use 1 mile = 1.609344 km and 1 US gallon = 3.785411784 L. Other mapped PIDs below may have labels without a value decoder; they remain raw-only rather than borrowing a J1939 scale.

| PID | Label | Value bytes | Output unit | Resolution | Offset | HA state class | Description |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 84 | Vehicle speed | 1 | km/h | 0.804672 | 0 | measurement | Vehicle speed, converted from J1587 units to km/h. An all-ones unavailable value is reported as null. |
| 91 | Accelerator pedal position | 1 | % | 0.4 | 0 | measurement | Accelerator pedal position, converted from J1587 units to %. An all-ones unavailable value is reported as null. |
| 92 | Engine load | 1 | % | 0.5 | 0 | measurement | Engine load, converted from J1587 units to %. An all-ones unavailable value is reported as null. |
| 96 | Fuel level | 1 | % | 0.5 | 0 | measurement | Fuel level, converted from J1587 units to %. An all-ones unavailable value is reported as null. |
| 100 | Engine oil pressure | 1 | kPa | 3.447378646584 | 0 | measurement | Engine oil pressure, converted from J1587 units to kPa. An all-ones unavailable value is reported as null. |
| 105 | Intake manifold temperature | 1 | °C | 0.5555555555555556 | -17.77777777777778 | measurement | Intake manifold temperature, converted from J1587 units to °C. An all-ones unavailable value is reported as null. |
| 110 | Coolant temperature | 1 | °C | 0.5555555555555556 | -17.77777777777778 | measurement | Coolant temperature, converted from J1587 units to °C. An all-ones unavailable value is reported as null. |
| 168 | Electrical system voltage | 2 | V | 0.05 | 0 | measurement | Electrical system voltage, converted from J1587 units to V. An all-ones unavailable value is reported as null. |
| 183 | Fuel rate | 2 | L/h | 0.059147059125 | 0 | measurement | Fuel rate, converted from J1587 units to L/h. An all-ones unavailable value is reported as null. |
| 190 | Engine speed | 2 | rpm | 0.25 | 0 | measurement | Engine speed, converted from J1587 units to rpm. An all-ones unavailable value is reported as null. |
| 235 | Engine idle hours | 4 | h | 0.05 | 0 | total_increasing | Engine idle hours, converted from J1587 units to h. An all-ones unavailable value is reported as null. |
| 236 | Engine idle fuel used | 4 | L | 0.473176473 | 0 | total_increasing | Engine idle fuel used, converted from J1587 units to L. An all-ones unavailable value is reported as null. |
| 245 | Total vehicle distance | 4 | km | 0.1609344 | 0 | total_increasing | Total vehicle distance, converted from J1587 units to km. An all-ones unavailable value is reported as null. |
| 247 | Total engine hours | 4 | h | 0.05 | 0 | total_increasing | Total engine hours, converted from J1587 units to h. An all-ones unavailable value is reported as null. |
| 250 | Total fuel used | 4 | L | 0.473176473 | 0 | total_increasing | Total fuel used, converted from J1587 units to L. An all-ones unavailable value is reported as null. |

J1587 provenance: Local BlueFire J1708 parameter scaling cross-check; independent J1587 native-unit conversions. Datalink/diagnostic structure: https://github.com/ainfosec/pretty_j1587

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
| 51 | Throttle position | % | Throttle position | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 70 | Parking brake status | - | Parking brake status | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 84 | Vehicle speed | km/h | Vehicle speed | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 91 | Accelerator pedal position | % | Accelerator pedal position | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 92 | Engine load | % | Engine load | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 93 | Actual engine torque | % | Actual engine torque | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 94 | Fuel delivery pressure | kPa | Fuel delivery pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 96 | Fuel level | % | Fuel level | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 100 | Engine oil pressure | kPa | Engine oil pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 101 | Crankcase pressure | kPa | Crankcase pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 102 | Intake manifold pressure | kPa | Intake manifold pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 105 | Intake manifold temperature | °C | Intake manifold temperature | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 108 | Barometric pressure | kPa | Barometric pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 109 | Coolant pressure | kPa | Coolant pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 110 | Coolant temperature | °C | Coolant temperature | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 111 | Coolant level | % | Coolant level | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 116 | Brake application pressure | kPa | Brake application pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 117 | Primary brake air pressure | kPa | Primary brake air pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 118 | Secondary brake air pressure | kPa | Secondary brake air pressure | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 120 | Retarder oil temperature | °C | Retarder oil temperature | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
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
| 184 | Instantaneous fuel economy | - | Instantaneous fuel economy | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 185 | Average fuel economy | - | Average fuel economy | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 190 | Engine speed | rpm | Engine speed | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 192 | Multisection parameter | - | Multisection parameter | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 194 | Diagnostic trouble codes | - | Diagnostic trouble codes | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 195 | Diagnostic clearing request | - | Diagnostic clearing request | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 196 | Diagnostic clearing response | - | Diagnostic clearing response | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 234 | Software identification | - | Software identification | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 235 | Engine idle hours | h | Engine idle hours | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 236 | Engine idle fuel used | L | Engine idle fuel used | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 237 | Vehicle identification | - | Vehicle identification | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 243 | Component identification | - | Component identification | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 245 | Total vehicle distance | km | Total vehicle distance | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 247 | Total engine hours | h | Total engine hours | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |
| 250 | Total fuel used | L | Total fuel used | Local static inspection: Android 9.7.5/11.2.3 and Windows 12.5.6; J1939/J1708 enums and FaultDescriptions namespace boundaries. Default source roles are hints, not ECU identity verification. |

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

Reference for a 2003-era 500 HP Detroit Diesel only if its ECM is confirmed as DDEC III/IV. Horsepower does not identify an ECM.

Curated flash codes and J1587 PID/SID/FMI equivalents, including a six-cylinder injector reference subset.

| Namespace | Code | Label / description | J1587 equivalents (code / FMI) | Reference |
| --- | --- | --- | --- | --- |
| detroit_flash | 13 | Coolant level sensor circuit low | PID 111 / 4, PID 111 / 6 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/400d02.html |
| detroit_flash | 14 | Coolant or oil temperature sensor circuit high | PID 110 / 3, PID 175 / 3 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/400e02.html |
| detroit_flash | 15 | Coolant or oil temperature sensor circuit low | PID 110 / 4, PID 175 / 4 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/400f02.html |
| detroit_flash | 16 | Coolant level sensor circuit high | PID 111 / 3, PID 111 / 5 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401002.html |
| detroit_flash | 21 | Throttle position sensor circuit high | PID 91 / 3 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401502.html |
| detroit_flash | 22 | Throttle position sensor circuit low | PID 91 / 4 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401602.html |
| detroit_flash | 23 | Fuel temperature sensor circuit high | PID 174 / 3 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401702.html |
| detroit_flash | 24 | Fuel temperature sensor circuit low | PID 174 / 4 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/401802.html |
| detroit_flash | 43 | Coolant level below normal | PID 111 / 1 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402b02.html |
| detroit_flash | 44 | Coolant or engine oil temperature above normal | PID 110 / 0, PID 175 / 0 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402c02.html |
| detroit_flash | 45 | Engine oil pressure below normal | PID 100 / 1 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/402d02.html |
| detroit_flash | 53 | Engine controller nonvolatile memory error | SID 253 / 12, SID 253 / 2 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403502.html |
| detroit_flash | 61 | Injector response too slow | SID 1 / 0, SID 2 / 0, SID 3 / 0, SID 4 / 0, SID 5 / 0, SID 6 / 0 | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403d02.html |

### Allison B500 with WTEC III controls (`allison_wtec_iii`)

B500 only when WTEC III controls are confirmed. Not WTEC II or Allison 4th/5th-generation P-codes; no automatic selection.

Curated two-part selector codes, not all calibrations.

| Namespace | Code | Label / description | J1587 equivalents (code / FMI) | Reference |
| --- | --- | --- | --- | --- |
| allison_wtec | 13-12 | Transmission controller supply voltage low | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 13-13 | Transmission controller supply voltage moderately low | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 13-23 | Transmission controller supply voltage high | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 14-12 | Transmission oil level sensor signal low | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 14-23 | Transmission oil level sensor signal high | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 21-12 | Transmission throttle position signal low | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 21-23 | Transmission throttle position signal high | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 22-14 | Transmission engine speed sensor fault | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 22-15 | Transmission turbine speed sensor fault | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 22-16 | Transmission output speed sensor fault | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 23-12 | Primary transmission selector fault | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 23-13 | Primary transmission selector mode fault | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 23-14 | Secondary transmission selector fault | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 23-15 | Secondary transmission selector mode fault | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 23-16 | Transmission selector display connection fault | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 24-12 | Transmission sump fluid temperature below range | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 24-23 | Transmission sump fluid temperature above range | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 26-00 | Transmission cannot detect throttle data source | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 26-11 | Transmission cannot detect engine coolant data source | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 33-12 | Transmission sump temperature sensor signal low | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |
| allison_wtec | 33-23 | Transmission sump temperature sensor signal high | - | https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf |

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
| detroit_ddec_iii_iv | 128 | 253 | Engine controller nonvolatile memory | https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/403501.html |

## Diagnostic framing and output strings

- J1939 DM1 is PGN 65226 (active); DM2 is PGN 65227 (previously active). Conversion method 0 is decoded. Method 1 is `unsupported_conversion` and has no inferred SPN.
- J1939 decode statuses: `decoded`, `unavailable`, `unsupported_conversion`. All-zero DTC: `No active faults` or `No previously active faults`. All-FF DTC: `Diagnostics unavailable`, never healthy.
- J1587 PID 194: each entry has code, flags/FMI and an optional occurrence byte. Bit 4 selects SID (otherwise PID); bit 5 clear adds 256; bit 6 means inactive; bit 7 includes occurrence count. Low four bits are FMI. Raw bytes and active/inactive status remain in the output.
- J1587 empty diagnostic list: `No faults in this report`, not vehicle-wide health. Otherwise the summary gives active/inactive entry counts. Diagnostic lookup never auto-selects a profile.
- Unknowns: `Unmapped <NAMESPACE> <code>`, `Unidentified controller`; known source labels do not establish hardware identity.

## MQTT mapping

All measurement and diagnostic states are non-retained. Discovery and availability are retained. Each protocol has independent freshness and all discovered sensors expire after 60 seconds. Live BLE reception is not implemented.

| Meaning | Topic pattern |
| --- | --- |
| J1939 raw frame | vehicle/{vehicle}/j1939/{source}/frame |
| J1939 measurement | vehicle/{vehicle}/j1939/{source}/spn/{spn} |
| J1939 diagnostic report | vehicle/{vehicle}/j1939/{source}/faults/{pgn} |
| J1587 normalized raw parameter | vehicle/{vehicle}/j1587/{mid}/report |
| J1587 measurement | vehicle/{vehicle}/j1587/{mid}/pid/{pid} |
| J1587 diagnostic entries | vehicle/{vehicle}/j1587/{mid}/faults/194 |
| Protocol availability | vehicle/{vehicle}/{j1939-or-j1587}/availability |
