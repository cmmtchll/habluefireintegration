# Telemetry and decoding

[Home](../README.md) · [MQTT contract](mqtt.md) · [Generated catalog](code-reference.md)

The integration shares one namespaced dictionary across the live bridge,
offline analyzer, and generated reference. It is curated, incomplete, and
explicit about unknown data. Decoder coverage does not establish that a vehicle
broadcasts or answers requests for each parameter.

## Protocol boundaries

| Input | Contract |
| --- | --- |
| J1939 `Frame` | A complete eight-byte, extended-ID CAN frame with its real arbitration ID |
| Vendor PGN report | Source, PGN/header metadata, and variable-length data; not an original CAN frame |
| Normalized `J1587Report` | MID/PID plus a complete parameter value, excluding PID/count/checksum bytes |
| Raw J1708 datagram | One complete checksummed message with explicit datagram boundaries |
| OBD report | A separate mode/PID namespace; labels do not imply value decoding |

BlueFire notifications must be unwrapped and validated before entering the
telemetry bridge. Never fabricate a CAN ID, pad short data to eight bytes,
associate an unrelated arbitration-ID response, or relabel J1587/OBD as J1939.

### J1939

Engineering values use little-endian raw fields and the catalog's resolution
and offset. PDU1 destination addresses are excluded from PGNs, while raw CAN
JSON preserves the full identifier. Unknown PGNs remain raw without guessed
signals. Null/global source addresses 254/255 do not create transmitter entities.

The numeric decoder accepts raw values through `0xFA`, `0xFAFF`, and
`0xFAFFFFFF` for one-, two-, and four-byte signals. Upper reserved, error, and
not-available values become null. This rule does not apply to arbitrary
enumerations; J1939 gears, including Park, are not decoded.

CAN transport reassembly, CAN FD, and manufacturer-specific measurement
encodings are not implemented. The offline analyzer decodes vendor J1939
measurements only for matching page-zero PGNs with exactly eight data bytes;
short/long/unknown reports remain opaque.

### J1708 / J1587

`MqttBridge.async_process_j1587(J1587Report(...))` accepts complete normalized
values with MID **128–255** and PID **0–1023**, enforcing fixed-width and
supported-value lengths. Vendor `PIDData` parsing requires an explicit pre-3.19
or 3.19+ firmware format. Blank format means it is ignored; the parser does not
guess by trying both layouts.

`parse_j1708_message()` and `MqttBridge.async_process_j1708()` accept one complete
**2–21 byte checksummed datagram**. MID, parameter bytes, and checksum must sum
to zero modulo 256. The parser handles multiple parameters, one-/two-byte
values, variable byte counts, and leading PID page extensions, stripping framing
to produce normalized values.

Malformed datagrams and unsupported special PID 254 framing raise errors.
A corrupt later parameter prevents earlier parameters in that datagram from
publishing; broker delivery itself is not transactional. The caller must supply
datagram boundaries: there is no checksum-scanning resynchronization or serial
idle-time inference.

Larger stationary messages, PID 192 multisection assembly, transmission/
arbitration, and clearing are unsupported. Non-J1587 MIDs below 128 stay opaque
offline and are rejected by the MQTT sink. Active requests are limited to the
[allowlisted J1708 reads](j1708.md#manual-read-actions).

## Measurement coverage

### J1939: 37 numeric SPNs

| PGN | SPNs | Measurements | Units |
| --- | --- | --- | --- |
| 61444 | 190 / 513 | Engine speed / actual torque | rpm / % |
| 61443 | 91 / 92 | Accelerator position / engine load | % |
| 65262 | 110 / 174 / 175 / 176 / 52 | Coolant / fuel / oil / turbo oil / intercooler temperature | °C |
| 65263 | 94 / 98 / 100 / 109 / 111 | Fuel pressure / oil level / oil pressure / coolant pressure / coolant level | kPa / % / kPa / kPa / % |
| 65265 | 84 | Wheel-based vehicle speed | km/h |
| 65266 | 183 | Engine fuel rate | L/h |
| 65253 | 247 | Total engine hours | h |
| 65248 | 245 | Total vehicle distance | km |
| 65271 | 167 / 168 | Charging system / battery potential | V |
| 65276 | 96 | Fuel level | % |
| 65269 | 108 / 171 / 172 | Barometric pressure / ambient temperature / air intake temperature | kPa / °C / °C |
| 65270 | 102 / 105 / 106 / 107 / 173 | Intake manifold pressure / temperature / inlet pressure / filter differential pressure / exhaust temperature | kPa / °C / kPa / kPa / °C |
| 65272 | 124 / 126 / 127 / 177 | Transmission oil level / filter differential pressure / oil pressure / oil temperature | % / kPa / kPa / °C |
| 65257 | 182 / 250 | Trip / total fuel used | L |
| 65244 | 235 / 236 | Total idle hours / idle fuel used | h / L |

Counters use `total_increasing`; other numeric readings use `measurement`.
Transmission decoder support is not an assertion about an Allison model's
broadcast configuration. The [generated catalog](code-reference.md#j1939-decoded-measurements)
contains exact offsets, scales, lengths, and descriptions.

Public implementation references, not normative SAE certification:
[CANboat layouts](https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns),
[MeatPi numeric ranges](https://github.com/meatpiHQ/meatpi-components/blob/d8cd667e4da19813977f3466423ecc93dc84b650/components/j1939/j1939_spn_core.c#L37-L103),
[ISOIdent signal table](https://github.com/florianeidner/isoident/blob/0ab94791c1fb76183ae27fdb242f2ab1b1159913/datasets/signals.CSV#L5284-L5372),
and [counter DBC definitions](https://github.com/JoaoCBFreitas/SNMPVeicular/blob/49a8317c65ac3011ccabc71293e0f44eee1ae942/projeto/SocketCAN/J1939/J1939.dbc#L44-L57).

### J1587: 39 numeric PIDs

| PIDs | Measurements | Output units |
| --- | --- | --- |
| 26 / 68 / 122 | Fan speed / engine torque factor / retarder torque | % |
| 51 | Throttle position | % |
| 74 / 84 / 86 | Maximum road / vehicle / cruise set speed | km/h |
| 91 / 92 / 96 | Accelerator position / engine load / fuel level | % |
| 94 / 100 | Fuel delivery / engine oil pressure | kPa |
| 101 / 102 | Crankcase / intake manifold pressure | kPa |
| 105 / 110 | Intake manifold / coolant temperature | °C |
| 108 / 109 | Barometric / coolant pressure | kPa |
| 111 | Coolant level | % |
| 116 / 117 / 118 | Brake application / primary / secondary air pressure | kPa |
| 120 | Retarder oil temperature | °C |
| 168 | Electrical system voltage | V |
| 171 / 172 / 173 | Ambient air / engine intake air / exhaust temperature | °C |
| 175 / 177 | Engine oil / transmission oil temperature | °C |
| 183 | Fuel rate | L/h |
| 184 / 185 | Instantaneous / average fuel economy | km/L |
| 190 | Engine speed | rpm |
| 235 / 247 | Idle / total engine hours | h |
| 236 / 250 | Idle / total fuel used | L |
| 245 | Total vehicle distance | km |
| 439 | Extended intake manifold pressure | kPa |

These are independent J1587 layouts, not J1939 scales. PID 190 uses **0.25
rpm/bit**, not SPN 190's 0.125. Native Fahrenheit, mph, psi, and US gallons are
converted explicitly. All-ones supported values become null using the observed
BlueFire unavailable convention; J1939 upper reserved ranges are not reused.
Zero and negative converted temperatures remain valid.

PID 101 alone uses a signed one-byte raw value; all-ones still means unavailable,
not negative one. Two-byte temperature PIDs use unsigned quarter-degree
Fahrenheit values, cross-checked against the inspected client. PID **174** fuel
temperature remains raw-only despite documentation of an installed sensor:
its vendor scale has not been established.

Unitless status PIDs **40/70** decode retarder/parking switches, **85** cruise
status with eight switch-bit attributes, and **162/163** two-character selected/
current gear text. They have no numeric state class or unit. Unsupported gear
encoding remains null with raw bytes and decode status.

See the [generated J1587 tables](code-reference.md#j1708j1587-decoded-measurements)
for exact scaling, and the [read guide](j1708.md) for requests and identification.

## Fault interpretation

Faults have codes, descriptions, and failure modes, **not measurement units**.
They are controller reports, not a diagnosis or vehicle safety assessment.

### J1939 DM1 / DM2

The bridge accepts complete eight-byte DM1 (**65226**) and DM2 (**65227**) frames
from valid transmitters. Active and previously active reports have separate
source-specific topics/entities. Attributes retain raw DTC bytes, SPN, FMI,
occurrence count, conversion method, and report-level lamp/flash fields.

The offline analyzer also accepts complete already-reassembled multi-DTC
reports; it does not reassemble CAN transport fragments. Single-frame reports
require `FF FF` filler. Invalid lengths/filler raise explicit errors.

Only SPN conversion method 0 is decoded. Method 1 remains
`unsupported_conversion`, without an inferred SPN. An all-zero DTC means no
reported faults; all-`FF` means unavailable, not healthy. Occurrence count 127
is unavailable. Reserved/unavailable lamp states are preserved, not treated as
lit lamps.

Live fault state is non-retained and normally expires after 60 seconds.
Passive fault reception sends no diagnostic requests or clearing commands.

### J1587 PID 194

Entries preserve MID, PID-versus-SID namespace, expanded codes, four-bit FMI,
active/inactive status, optional occurrence count, and raw bytes. A missing
count is null, not zero. An empty list means **No faults in this report**, not
vehicle-wide health or an accumulated historical fault database.

J1587 FMI 15 remains reserved; it is not J1939's least-severe high threshold.
Detroit interpretation requires the explicitly configured engine profile,
never MID 128 alone. PID 194 can be actively read manually or in the five-PID
poll loop, without clearing faults.

Allison selector-code and other manufacturer-specific on-wire encodings remain
opaque. A reference lookup does not create an on-wire decoder.

## Dictionary and equipment profiles

`signals.py` defines J1939 measurements; `catalog.py` provides curated metadata.
The bridge and offline analyzer use the same namespaced definitions.
The [generated code reference](code-reference.md) is checked for drift;
do not edit its tables by hand.

Namespaces include J1939 PGN/SPN/source, J1587 MID/PID/SID, OBD mode+PID,
Detroit flash codes, Allison main/subcodes, adapter commands, and failure modes.
A number alone is not enough: OBD `01:0C` is neither J1587 PID 12 nor SPN 12.
SID descriptions also require MID and controller profile.

Unknowns retain raw IDs and explicit unmapped labels. Ambiguous aliases are
not promoted to standards. J1587 lookup units marked
`preferred_display_unit_only` do not establish raw encoding; OBD labels do not
decode values. Units do not silently become gauge/absolute pressure.

| Reference area | Scope |
| --- | --- |
| Standard diagnostics | FMI 0–31, known measurement SPNs, selected brake-pressure/lamp labels |
| Controller roles | Conventional engine, transmission, brakes, retarder, instrument, climate, body, cab, tire-pressure, and aftertreatment roles |
| Detroit DDEC III/IV | 66 indexed 6SE497 flash-code sections, verified PID/SID/FMI equivalents, six-cylinder injectors, scoped circuits/data links, explicit conflicts |
| Allison B500/WTEC III | 21 exact main/subcode references for voltage, sensors, selectors, and missing data sources |
| J1587 / OBD | Selected labels and units, with value decoding only where explicitly implemented |

Official equipment labels identify **Series 60, 12.7 L, 500 HP, DDEC IV**.
Prevost PA1163 independently identifies Series 60/DDEC IV and its engine-mounted
fuel-temperature sensor. The coach build sheet specifies **HD4000MH R**,
overriding the generic specification's B500 wording. None establishes
transmission control generation or ECM calibration.

Select **Confirmed engine equipment → Detroit Diesel Series 60 / DDEC IV** in
Reconfigure only when supported by official labels/documentation. It enables
`detroit_ddec_iii_iv` in the live path and names engine MID 128 with
`source_name_basis: configured_official_equipment_labels`. It does not infer
calibration, rename unknown controllers, or use `Mike1`/software text `39.02`
as official identity. Standard J1587 removes the engine-specific interpretation.
The selection survives MAC/name changes without changing entity IDs.

`allison_wtec_iii` remains a reference, not an automatically selected transmission
profile. Do not apply WTEC selector codes to 4th/5th-generation P-codes.
WTEC III `13-13`, for example, is moderately **low** supply voltage; `13-23` is high.

66 indexed Detroit sections do not mean all calibrations/options/later codes.
EGR, gas-engine, ESS, and Optimized Idle references do not establish installed
features. Conflicting crosswalks, notably flash 73/74 and EGR 81–83, are withheld
or limited. Manufacturer-authored references on third-party mirrors are not
official Detroit sites; per-entry provenance and applicability remain in the
catalog. Sources checked in October 2026 do not replace the actual service manual.

Descriptions are independently worded factual summaries. No proprietary resource
tables, vendor binaries, or decompiled implementation are distributed.
Additional sources:
[CSS J1939 diagnostics](https://www.csselectronics.com/pages/j1939-73-dm1-diagnostic-message-dtc),
[FMI definitions](https://j1939hub.com/fmi-decoder/),
[DDEC III/IV references](https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/),
and [Allison WTEC III selector table](https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf).

Dictionary export and lookup commands are in [Development](development.md#export-and-look-up-codes).
