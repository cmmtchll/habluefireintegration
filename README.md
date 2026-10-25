# BlueFire for Home Assistant

Preparation for a **direct BLE → Home Assistant → MQTT** integration, initially
focused on a 2003-era **500 HP Detroit Diesel**, **Allison B500** transmission
and Prevost H3-45 Liberty Coach Elegant Lady.
No Android gateway is required or planned.

> **Status: provisional internal receiver enabled; hardware not verified.** A
> loaded entry connects to the documented modern EZ GATT service, subscribes to
> its receive characteristics, decodes receive packets and routes reports into
> MQTT. PGN reports use a separate report contract and never invent CAN IDs.
> Opt-in J1708 startup negotiates firmware compatibility, uses the unsecured
> authentication path, subscribes to passive PID reports and enables reporting.
> Secured adapters are unsupported. Do not treat this as a public release or
> a validated adapter integration.
>
> Internal receiver development is not blocked on verified traces or actual
> hardware testing: use the documented static observations and synthetic
> fixtures, and keep unvalidated behavior explicit. Validate against real
> adapter traces and hardware before declaring a full public release.

## What is ready

- UI setup with nearby-device selection or manual MAC entry, duplicate
  prevention, and reconfiguration without changing entity/MQTT identity.
- Diagnostic `Protocol status` sensor showing `receiver_enabled`, plus
  receive-health diagnostic sensors (last data/advertisement, signal strength,
  notification, packet, error and unrecognized-message tallies).
- Downloadable diagnostics with full entry/MQTT/Bluetooth state and a 20-second
  raw BLE notification capture with framing, parse and timing analysis.
- Explicit, read-only BLE GATT inspection via Home Assistant's connectable
  Bluetooth scanners, including compatible proxies.
- Provisional receive-only BLE subscriptions for the documented EZ service,
  bounded reconnect/backoff, receive framing validation, and MQTT report routing.
- Explicit opt-in unsecured EZ J1708 startup with response deadlines,
  compatibility/authentication checks, passive PID subscriptions and report
  flow control. Firmware 3.23.0 is the primary synthetic startup fixture.
- Transport-independent decoding of 37 byte-aligned J1939 SPNs, including
  reserved/error/not-available handling, engineering units, and source addresses.
- Shared, exportable namespaced dictionary for measurement labels, units,
  controller roles and fault descriptions, including scoped Detroit DDEC III/IV
  and Allison B500/WTEC III reference subsets.
- Read-only single-frame J1939 DM1/DM2 fault interpretation and MQTT diagnostic
  discovery. Offline analysis also accepts already-reassembled diagnostic reports.
- J1708/J1587 decoding of 31 numeric PIDs and PID 194 diagnostic entries,
  with a checksummed-datagram parser and separate MQTT/MID/PID discovery.
- Hardware-unverified offline receive framing and PGN/J1587/OBD report analysis
  based on local inspection of Android 9.7.5/11.2.3 and Windows 12.5.6 packages;
  the offline analyzer performs no adapter writes.
- MQTT publishing/discovery code, source-separated readings, raw frame output,
  retained availability, freshness watchdog, durable discovery ownership,
  broker reconnect/birth handling, and non-retained live state.
- Hardware-free unittest tests, real configuration-schema validation, and
  repeatable PEP 8 checks plus a Home Assistant quality-scale checklist audit.

The live receiver is connected to BLE notifications. BlueFire notification
payloads are not assumed to be raw CAN frames. Unsecured J1708 startup is
implemented separately from incoming telemetry parsing and remains opt-in.
The [known codes and mappings reference](docs/code-reference.md) lists the
supported IDs, strings, descriptions, units, controller profiles and sources.

## Install and prepare

Use Home Assistant Core **2026.10 or later**, with its MQTT integration configured
for your broker and its Bluetooth integration configured for connectable BLE.
This foundation has hardware-free tests, not a verified full Home Assistant or
vehicle commissioning run.

1. Copy the repository's `custom_components/bluefire` directory into your
   Home Assistant configuration directory. The resulting manifest path should
   be `/config/custom_components/bluefire/manifest.json` on HA OS, **not**
   `/config/custom_components/habluefireintegration/custom_components/...`.
   Restart Home Assistant after installing or upgrading the files.
2. In **Settings → Devices & services → Add integration**, select **BlueFire**.
3. Choose **Choose a nearby Bluetooth device** when the adapter is powered and
visible, or enter its MAC address manually.
   The nearby list includes all connectable BLE devices, not verified BlueFire
   matches. Select only the adapter you recognize; confirm or correct its MAC
   and name on the following form. Setup itself does not connect; the receiver
   starts when the config entry loads and retries with bounded backoff.
4. Enter a vehicle MQTT identifier. `liberty_h3_45` is the default identifier,
   not a vehicle-detection rule. The identifier must be unique and use 1–64
   lowercase letters, digits, underscores or hyphens, starting with a letter
   or digit. Blank adapter names and duplicate MACs/topics are rejected.
5. The adapter can be configured while offline. Expect the diagnostic status
   **receiver_enabled**. The live receiver attempts a connection with bounded
   backoff; MQTT availability stays offline until valid report data arrives.
   J1708 startup remains disabled unless explicitly enabled below.

No broker credentials are stored by this integration; it uses HA's MQTT client.
There are no adapter passwords or PGN transmit/reset controls.

### Enable J1708 startup

For an existing entry, use **Settings → Devices & services → BlueFire →
Reconfigure**. Select **Extended (3.19+)** for adapter firmware **3.23.0** and
enable **Enable J1708 startup (unsecured EZ adapters)**. Save to reload the entry.
The same option is available during initial setup. Existing entries remain
receive-only until this option is enabled; the firmware-format setting by
itself does not enable writes.

Startup waits for a heartbeat, negotiates client compatibility, checks both
unsecured authentication responses on firmware 3.x, reads adapter variables
and J1708 availability, signals application connection, installs passive
subscriptions and starts reports. It monitors all 31 supported numeric PIDs
plus diagnostic PID 194 across reported MIDs at a 1000 ms interval. Vendor
subscription MID 0 means any MID; actual report identities remain unchanged.
Subscriptions use monitoring, not on-request vehicle-bus retrieval. A PID that
the ECU does not broadcast may therefore remain absent.

There are 32 passive PID subscriptions in total, all using wildcard MID 0.
Compared with the original 16 subscriptions, the expanded set adds throttle
position, fuel/crankcase/intake/barometric/coolant pressures, coolant level,
three brake pressures, retarder temperature, ambient/intake/exhaust temperatures,
engine oil temperature and transmission oil temperature. Sensors are discovered
only when a controller actually reports a supported PID. No new MID selection
or active vehicle requests are needed; controllers keep distinct MID identities.
The expanded filter set still requires hardware confirmation, including adapter
filter capacity. An explicit subscription rejection remains a startup error.

Client packets are at most 20 bytes and use write-with-response on EZ `ca101`.
The compatibility tuple `12.5.6` describes the inspected wire compatibility
profile, not this integration's version; platform 0 is unspecified. Unversioned
EZ advertisements take the firmware 3.x version-query path. A version-bearing
4.x advertisement uses its separate startup layout. Firmware-format mismatches,
malformed/rejected responses, explicitly disabled J1708 or missing replies fail
explicitly, with a 10-second deadline per exchange and normal reconnect backoff.
The initial J1708 availability response is diagnostic status, not a prerequisite
for report setup: a false response is logged and preserved in diagnostics while
authenticated passive initialization continues, matching the vendor client.
Telemetry received before startup succeeds is discarded. Subscriptions and
authentication state are rebuilt for every new connection, including after
diagnostic inspection.

Download diagnostics and inspect **`startup_before_capture`** for the stage,
firmware, expected response command, initial J1708 availability, subscription
count and last startup error. `ready` means the report-start exchange completed,
not that the coach is sending measurements. MQTT availability still requires valid
telemetry. Diagnostic captures themselves remain passive and temporarily
replace the live connection, so use the pre-capture startup/health state when
investigating the active session.

No security settings, bus-ignore flags, sleep/LED variables or adapter firmware
are changed. Secured adapters are rejected without retrying with alternate
credentials or resetting security. **Firmware 4.2.3 is not installed by this
integration**; no firmware update is needed to exercise the 3.23.0 path.
A firmware 3.23.0 diagnostic confirms version negotiation, compatibility,
authentication and adapter-variable reads, followed by a false initial J1708
availability response. Full report setup and measurements still require
verification on the adapter; synthetic coverage is not a claim of hardware
compatibility.

### Link to MQTT

1. Install or choose an MQTT broker, for example the Mosquitto broker app on
   HA OS. The broker is infrastructure; it does not replace this integration.
2. Configure **Settings → Devices & services → MQTT** with that broker. Configure
   authentication and, when appropriate, TLS there, not in BlueFire. Avoid
   exposing an unauthenticated broker to the internet.
3. Leave HA MQTT discovery enabled to have measurement entities created
   automatically. BlueFire reads the configured MQTT discovery prefix and
   birth topic/payload, including a disabled birth message; it does not invent a
   second broker login or MQTT connection. Reload BlueFire after changing those
   MQTT options. This settings lookup is isolated because HA provides no public
   discovery-settings getter.
4. Add BlueFire as described above. The integration starts the provisional EZ
   receiver. Measurement entities appear only for recognized, complete reports;
   raw PGN reports remain distinct from CAN frames.
5. When live reception is available, all measurements from one adapter are
   grouped under one MQTT-owned device with stable identifiers. The BlueFire
   integration's diagnostic device remains separate; do not manually create
   duplicate MQTT YAML sensors or assume HA merges devices across config entries.
   MAC corrections do not change MQTT topics or unique IDs.

Sensor names put the reporting controller first, for example **Engine: Coolant
temperature** or **Brakes: Supply voltage**. Known controllers do not include
numeric IDs in their names; unknown sources use **Controller 253** (for example)
so separate readings remain distinguishable without guessing the controller's
role. Controller roles are conventional hints, not verified ECU identities.
MID/PID or source-address/SPN/PGN details remain in the entity attributes.

MQTT discovery suggests two decimal places for voltage, fuel flow, speed,
pressure, distance, volume and hours, and one for temperatures and percentages.
This affects display only: published values keep their decoded precision and
Home Assistant can still convert units. A user-selected **Display precision**
overrides this suggestion. Reload BlueFire after upgrading to republish names
and precision for existing entities without changing unique IDs or history.
User-customized entity names remain under Home Assistant's control.

In the MQTT integration's **Configure → Listen to a topic** tool, listen to
`vehicle/liberty_h3_45/j1939/#` (replace the vehicle ID). Expect retained `offline`
until the first valid report, not sample engine data. Once receiving, inspect numeric
`value`, explicit `unit`, PGN, SPN, source address and UTC timestamp. An external
MQTT client can subscribe to the same topics; it does not need Home Assistant
discovery to understand the JSON.

On permanent BlueFire entry removal, retained discovery definitions are cleared
with empty retained payloads, including those known before a restart. Ordinary
unload/reload keeps discovery, but marks the stream offline. Removal while the
broker is down is recorded in HA storage and retried on reconnect while HA is
running. If HA restarts with no BlueFire entries left, pending cleanup resumes
the next time BlueFire is set up. Do not delete that storage before cleanup.
If an entry unloads while MQTT is disconnected, its offline availability is also
stored and published when the broker reconnects.
Discovery-prefix changes similarly withdraw the previous prefix's definitions.
Cleanup requires broker-echo confirmation of the deletion messages, not just a
successful return from HA's publish call; unconfirmed work remains queued.
Only discovery ownership and pending lifecycle status are persisted—never live
readings or broker credentials. Diagnostic ownership uses negative PGNs in the
existing ledger; measurement ownership remains the original positive SPN.

### Find and specify the Bluetooth MAC address

Use the **BlueFire peripheral's** BLE address, not your HA computer, phone,
ESPHome proxy, Wi-Fi adapter or vehicle VIN. With the adapter powered, use the
nearby-device list above or the Bluetooth advertisement monitor in HA's Bluetooth
integration to match the adapter's name and address. Names alone are not proof
of device identity. The selection list excludes already configured addresses.
There are no automatic discovery matchers yet. The UUID candidates documented
below may be used for internal implementation; validate them against an actual
adapter before declaring a full public release.

Manual entry accepts `AA:BB:CC:DD:EE:01`, `AA-BB-CC-DD-EE-01` or `AABBCCDDEE01`
(case-insensitive, surrounding spaces ignored) and stores
`AA:BB:CC:DD:EE:01`. Do not enter this example unless it is your real device.
All-zero/broadcast addresses, partial MACs and mixed separators are rejected.
If you do not know the MAC yet, wait until you can identify it; no placeholder
or random address will make the adapter discoverable.

To correct an offline entry later, select **Reconfigure** from that BlueFire
entry's menu in **Settings → Devices & services**. Change the MAC or name;
HA reloads the entry automatically. Diagnostic device/entity IDs remain stable,
including migration of the earlier MAC-based IDs. The vehicle MQTT identifier
stays unchanged to avoid orphaning topics and discovered entities. Remove and
recreate the entry if you intentionally need a different MQTT vehicle identity.
YAML setup is not supported.

If no nearby devices are shown, choose manual setup, check HA's Bluetooth
scanner/proxy is connectable, power the adapter, and stop competing BLE apps.
If MQTT is not configured, configure its broker first; BlueFire setup will retry
once HA's MQTT client becomes available. Installing BlueFire does not create a
broker or establish hardware compatibility.

### When you can power the adapter

Stop other applications using the adapter. In **Developer tools → Actions**, run
`bluefire.inspect_adapter`, selecting the BlueFire config entry. The response
contains service UUIDs and characteristic UUIDs/properties. This only connects,
enumerates metadata, and disconnects; it does not read characteristic values,
subscribe to notifications, authenticate, or send adapter commands. If the
receiver is connected, it pauses and releases the adapter for this inspection,
then resumes.

### Diagnostics and raw capture

Downloading diagnostics (**Settings → Devices & services → BlueFire → ⋮ →
Download diagnostics**) is a deliberate user action, so the file is **not
redacted**. It takes about 20 seconds plus connection time and contains:

- Config entry data/options (including the Bluetooth MAC and vehicle ID),
  integration version and protocol status.
- MQTT connection state, discovery settings, the persisted discovery ledger
  record and the live bridge state (online flag, frame age, known signals and
  discovery topics for J1939 and J1587).
- Home Assistant's Bluetooth view: scanner counts, whether the address is seen
  by any/connectable scanners, and the last advertisement (name, RSSI, TX
  power, source scanner/proxy, age, service UUIDs, manufacturer and service
  data) before and after the capture.
- Receive-health counters and RSSI history (`health_before_capture` and
  `health`), recent error messages and the last capture summary.
- A **raw notification capture**: the integration connects, subscribes to every
  notify/indicate characteristic for 20 seconds, then unsubscribes and
  disconnects. Every notification is listed with its time offset,
  characteristic UUID/handle, length and hex payload (bounded to 5,000
  notifications; `dropped_notifications` reports overflow). Subscription
  failures, MTU, connection time and the full GATT inventory with handles are
  included.
- Capture analysis per characteristic in both stream and padded-notification
  framing: packet counts, framing/parse error messages, decode success rate,
  command/PGN/J1587/OBD tallies (with names and whether each PGN is known),
  J1587 firmware formats that parse, sample decoded records, notification
  rate, mean interval, longest gap and length histogram. `selected_framing`
  names the mode that explains the data with fewer errors.

Enabling notifications writes only the standard client characteristic
configuration descriptors. No characteristic values are read, no
authentication or BlueFire commands are sent and nothing is published to MQTT.
Adapters that need an authentication handshake may therefore send little or no
data; an empty capture is itself useful evidence. The live receive task pauses
and releases the BLE connection during capture, then resumes without marking
the MQTT stream offline. If another inspection or
capture is running, or the adapter is not visible, the file reports the capture
as `skipped`/`failed` and still includes all other state. Stop other apps using
the adapter first. Review the file before sharing it: it can contain the MAC,
VIN or location-related vehicle data.

For a capture without the rest of the dump, or a different length, run the
`bluefire.capture_notifications` action with a 5–60 second `duration`; it
returns the same capture structure as an action response.

### Diagnostic sensors

The BlueFire device has these diagnostic entities. Counters are in memory, use
`total_increasing` and reset when Home Assistant restarts.

| Entity | Meaning |
| --- | --- |
| Last data seen | Time BLE notification data was last received |
| Last advertisement | Time HA last saw a passive advertisement; attributes show presence and scanner/proxy |
| Signal strength | Latest advertisement RSSI in dBm (unknown when HA reports the adapter unavailable); attributes include min/max/mean/spread |
| Decode success rate | Decoded packets as a percentage of packets plus framing/parse errors |
| BLE notifications / BLE bytes received | Notification and byte tallies (bytes disabled by default) |
| Decoded packets | Valid framed packets; attributes split heartbeats and PGN/J1587/OBD reports |
| Framing errors / Parse errors | Invalid length/checksum/padding and malformed report bodies, with recent messages |
| Unrecognized messages | Unknown adapter commands plus PGNs absent from the catalog |
| Connection errors | Failed live receiver connections, inspections or captures |
| MQTT messages published / MQTT publish errors | Publisher tallies (published disabled by default) |
| Diagnostic captures | Number of captures; attributes summarize the last one |
| Last error | Most recent error class and message |

Signal strength and last advertisement come from Home Assistant's passive
Bluetooth advertisement tracking; this never connects to the adapter. Counters
otherwise update during live reception and captures.

## MQTT contract

There is no universal OBD/CAN/J1939 MQTT topic standard. This project uses an
explicit, versioned J1939 contract rather than pretending SPNs are OBD-II PIDs.
J1708/J1587 uses its own decoder and `j1587` protocol namespace; it never
masquerades as J1939 or constructs a CAN arbitration ID.

For a vehicle identifier `liberty_h3_45` and engine source address `0`:

| Topic | Content |
| --- | --- |
| `vehicle/liberty_h3_45/j1939/availability` | `offline` or `online` |
| `vehicle/liberty_h3_45/j1939/0/frame` | CAN arbitration ID, extended-frame flag, DLC, PGN, priority, source address and hex payload |
| `vehicle/liberty_h3_45/j1939/0/report/61444` | Vendor PGN report metadata and bytes, without a fabricated CAN identifier |
| `vehicle/liberty_h3_45/j1939/0/spn/190` | Engine-speed measurement in rpm |
| `vehicle/liberty_h3_45/j1939/0/faults/65226` | Active faults, readable summary, lamp states and raw DTCs |
| `vehicle/liberty_h3_45/j1939/3/faults/65227` | Transmission's previously active faults, separate from active faults |
| `homeassistant/sensor/bluefire_liberty_h3_45_0_190/config` | Retained HA MQTT sensor discovery |

Example **synthetic** measurement illustrating the schema, not received data:

```json
{
  "schema_version": 1,
  "protocol": "j1939",
  "vehicle_id": "liberty_h3_45",
  "pgn": 61444,
  "source_address": 0,
  "source_name": "Engine",
  "source_name_basis": "conventional_address_not_verified_identity",
  "pgn_name": "Electronic engine controller 1",
  "catalog_version": 2,
  "timestamp": "2026-01-01T00:00:00+00:00",
  "spn": 190,
  "name": "Engine speed",
  "description": "Engine speed, reported in revolutions per minute (rpm). Reserved, error and unavailable values are reported as null.",
  "value": 1000.0,
  "unit": "rpm"
}
```

Timestamps are UTC ingestion time, not ECU timestamps. Numerical invalid values
become JSON `null`, never zero or `"NA"`; MQTT discovery converts null to HA's
explicit `None`/unknown state rather than preserving an old value. Valid negative
temperatures/torque are preserved. Unknown PGNs pass through as raw frames without
guessed signals.
PDU1 destination addresses are excluded from PGNs. CAN transport-protocol
reassembly, manufacturer-specific measurement encodings and CAN FD are not
implemented. DM1/DM2 decoding requires a complete diagnostic payload; transport
fragments are never interpreted as individual faults.

### Interoperability and delivery semantics

This follows the common CAN-to-MQTT gateway split: raw frames for CAN consumers,
normalized engineering measurements for dashboards, retained discovery for HA,
and a separate device-availability topic. It is **not** a drop-in schema for
every CAN gateway, OVMS, Torque, or OBD-II application; those applications have
their own topic/payload contracts. J1939 SPNs are not interchangeable with
OBD-II Mode/PID values. A downstream adapter must map any application-specific
schema explicitly rather than relabeling an SPN as a PID.

Raw frame JSON includes the common envelope shown above (without measurement
fields) plus `can_id`, its synonymous `arbitration_id`, `is_extended_id: true`,
`dlc: 8`, `priority`, and `data` as exactly 16 lowercase hexadecimal characters.
The full 29-bit identifier is preserved, including PDU1 destination bits; the
separate `pgn` is destination-independent. Topics partition by vehicle, protocol,
and transmitting ECU source address, so two ECUs reporting an SPN cannot collide.
Null/global source addresses 254/255 do not create transmitter entities.

- Live state/raw frames: **QoS 0, non-retained**. No obsolete values are replayed
  into a fresh session. There is no lossless CAN recorder or exactly-once claim.
- Discovery and availability: **QoS 1, retained**. New subscribers see current
  advertised availability. Consumers must tolerate duplicate delivery.
- Availability transitions to `online` only after receiving a complete valid
  frame. Disconnect, reconnect initialization, graceful HA shutdown and unloading
  publish `offline`. Definitions are restored across restarts and republished
  on broker reconnect and the configured HA MQTT birth message.
- A watchdog checks every 15 seconds and withdraws device availability after
  60 seconds without a frame (at the next check). Each MQTT sensor independently
  expires 60 seconds after its last update, even if another SPN keeps arriving.
  Device availability alone does not establish measurement freshness.
- The integration uses HA's shared MQTT client and **cannot set a per-device
  Last Will** on that connection. The watchdog cannot run after a process crash
  or blocked HA event loop; retained `online` may then be stale. External
  consumers must enforce measurement timestamps/timeouts and may additionally
  monitor HA's configured MQTT birth/will topic. MQTT sensors' `expire_after`
  provides the HA-side safeguard. Never interpret availability as a safety signal.

The topic/payload contract remains version 1 and existing measurement entity IDs
and topics are preserved. Readable fields are additive, not renamed fields.
Discovery names now include the conventional controller role and its address,
for example **Engine speed - Engine (0)** and
**Transmission oil temperature - Transmission (3)**. HA users can rename them.
Measurement descriptions and raw identifiers are also available as attributes.

### Human-readable code and fault dictionary

The full [known code/ID/mapping reference](docs/code-reference.md) is kept
separately from this README and generated from the same definitions as the code.
A regression check rejects documentation drift when definitions change.

`custom_components/bluefire/signals.py` is the shared source for all 37 prepared
measurements, scales, offsets, units and HA measurement classes.
`catalog.py` holds the curated code/reference database; the MQTT bridge and
offline analyzer use the same metadata. Symbols such as `rpm`, `L/h`, `kPa` and
`°C` stay machine-readable, while descriptions spell out their measurement units.
Labels do not change the wire units or convert pressure to gauge/absolute by
guessing. Counters retain `total_increasing` and their original scales.

The dictionary separates **J1939 PGN/SPN/source**, **J1587 MID/PID/SID**,
**OBD mode+PID**, **Detroit flash codes**, **Allison main/subcodes**, adapter
commands and failure modes. SID descriptions require both MID and controller
profile. OBD `01:0C` is not J1587 PID 12 or J1939 SPN 12. Address-derived names
are conventional role hints, not validated identities from an ECU address claim.
An unidentified controller or unmapped code remains explicitly unidentified,
with its raw ID intact; there is no invented description or value.
Ambiguous application aliases are not promoted to standard mappings.
J1587 lookup units are explicitly marked `preferred_display_unit_only`, not
claims about raw byte encodings. For example, a preferred coolant display unit
of Celsius does not make a J1587 Fahrenheit-based payload Celsius. J1587/OBD
lookup labels alone do not decode values. J1587 replay records now contain
converted engineering values for the supported subset below; unsupported PIDs
and all OBD replay records retain `value_decoded: false`.

Current reference coverage is deliberately **curated, not a complete service
manual**:

| Area | Included |
| --- | --- |
| Measurements | All 37 prepared SPNs, matching PGN labels, units and descriptions |
| Other controllers | Conventional engine, transmission, brakes, retarder, instrument, climate, body, cab, tire-pressure and aftertreatment roles |
| Standard diagnostics | FMI 0–31, including reserved entries; known measurement SPNs and selected brake-pressure/lamp labels |
| Detroit DDEC III/IV | 13 flash-code references, verified PID/FMI equivalents, six-cylinder injector reference SIDs 1–6 and memory SID 253 scoped to engine MID 128 |
| Allison B500/WTEC III | 21 exact main/subcode references covering supply voltage, level/temperature/throttle sensors, speed sensors, selectors and missing data sources |
| J1587 / OBD | Selected parameter labels and units; no reuse of J1939 decoding rules |
| J1587 decoding | 31 independently defined numeric PIDs plus PID 194 active/inactive diagnostic entries; separate four-bit FMI definitions |

The recorded vehicle details are **2003-era, 500 HP Detroit Diesel and Allison
B500**. They do **not** establish the engine model, ECM generation, transmission
controller generation or calibration. `detroit_ddec_iii_iv` and
`allison_wtec_iii` are explicit reference profiles, not automatic settings.
Do not select them solely from the year or horsepower, and do not apply WTEC
selector codes to 4th/5th-generation Allison P-codes. Injector numbering and
cylinder/bank applicability must be checked against the actual engine manual;
the catalog does not infer an engine model. For example, WTEC III
`13-13` means moderately **low** controller supply voltage; `13-23` is high.

Export the dictionary as JSON, or look up codes without an adapter:

```powershell
python .\scripts\catalog_bluefire.py --export
python .\scripts\catalog_bluefire.py --markdown --output .\docs\code-reference.md
python .\scripts\catalog_bluefire.py --namespace spn --code 190
python .\scripts\catalog_bluefire.py --namespace pid --code 91 --fmi 3 --source 128 --profile detroit_ddec_iii_iv
python .\scripts\catalog_bluefire.py --namespace sid --code 1 --fmi 0 --source 128 --profile detroit_ddec_iii_iv
python .\scripts\catalog_bluefire.py --namespace allison_wtec --code 13-12 --profile allison_wtec_iii
```

The export includes coverage, profile applicability and per-record provenance.
Descriptions are independent factual summaries; proprietary application resource
tables, binaries and decompiled implementation are not distributed.
Sources include the locally inspected application namespaces,
[CANboat's measurement definitions](https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns),
[CSS Electronics' J1939 diagnostics explanation](https://www.csselectronics.com/pages/j1939-73-dm1-diagnostic-message-dtc),
[FMI definitions](https://j1939hub.com/fmi-decoder/),
[DDEC III/IV troubleshooting references](https://www.detroitmanuals.info/ddec-singleecm-troubleshooting/)
(individual sections are linked in each manufacturer entry), and the
[Allison WTEC III selector reference, diagnostic table](https://assets.wellertruck.com/reference-materials/troubleshooting-manuals/wteclllshiftselectormanual.pdf).
Public reference contents were checked in October 2026; they do not replace the
service manual for the actual controller and calibration.

### Fault reporting boundaries

The prepared MQTT bridge accepts complete, eight-byte J1939 DM1 (65226) and DM2
(65227) frames from any valid transmitting address. Fault summaries and HA
diagnostic entities are source-separated, for example **Active faults -
Brakes (11)**. Faults have descriptions and failure modes, **not measurement
units**. Detailed attributes retain raw DTC bytes, SPN, FMI, occurrence count,
conversion method and separately decoded report-level lamp/flash fields.
Discovery ownership is saved before publishing, restored after restart, and
removed on deletion or discovery-prefix change, just like measurements.

The offline analyzer additionally handles complete, already-reassembled
multi-DTC PGN reports, but it does **not** perform CAN transport reassembly.
Single-frame diagnostics require `FF FF` filler bytes; malformed lengths/filler
raise explicit errors. Only SPN conversion method 0 is decoded. Legacy method 1
is marked `unsupported_conversion`, with no inferred SPN. An all-zero DTC means
no reported faults; an all-`FF` DTC means unavailable, **not healthy**.
Occurrence count 127 is unavailable, not a count. Reserved/unavailable lamp
states are preserved rather than treated as lit lamps.

Active and previously active reports have separate topics/entities. State is
non-retained, expires after 60 seconds, and is never replayed on reconnect.
These are controller reports, not a diagnosis or a vehicle safety signal.
J1587 PID 194 entries are decoded as described below; Allison selector-code and
other manufacturer-specific on-wire encodings remain opaque. The reference
lookup does not invent translations or automatically select controller profiles.
No fault clearing or diagnostic requests are transmitted.
Live BLE reception is provisional and uses only the documented modern EZ
service. Original BLE UUID variants and secured-adapter authentication
are not implemented.

### SAE J1708 / J1587 support

**J1708 is the data link; J1587 defines the MID/PID application data.** Support
is read-only and transport-independent. `MqttBridge.async_process_j1587(J1587Report(...))`
accepts a complete, normalized parameter value. Its data excludes the PID,
variable-parameter byte-count prefix and J1708 checksum. MID must be 128–255,
PID 0–1023, with exact fixed-width and supported-value lengths.
The live BlueFire `PIDData` parser requires an explicit pre-3.19 or 3.19+
adapter firmware selection; app version is not a firmware-format selector.
When no format is configured, J1587 `PIDData` is ignored. Do not guess whether
a byte-count prefix is present.

`parse_j1708_message()` and `MqttBridge.async_process_j1708()` instead accept
**one complete checksummed J1708 datagram**, bounded to 2–21 bytes.
The checksum includes MID, parameter bytes and the trailing checksum byte;
their sum modulo 256 must equal zero. The parser handles multiple parameters,
one-/two-byte values, variable-parameter counts and leading PID page extensions.
It strips the byte-count/checksum fields to produce normalized reports.
Malformed datagrams and unsupported special PID 254 framing raise explicit
errors; a corrupt later parameter cannot publish earlier parameters from the
same datagram. Broker delivery itself is not transactional.

Datagram boundaries must be supplied by the driver/capture. There is no
checksum-scanning resynchronization or serial idle-time inference, and no
support for larger stationary messages, PID 192 multisection assembly,
transmission/arbitration, diagnostic requests or clearing. Non-J1587 J1708
MIDs below 128 remain opaque in offline analysis; the MQTT telemetry sink
rejects them rather than inventing PID meanings.

| Numeric PID | Decoded value | Output unit |
| --- | --- | --- |
| 51 | Throttle position | % |
| 84 | Vehicle speed | km/h |
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
| 190 | Engine speed | rpm |
| 235 / 247 | Idle / total engine hours | h |
| 236 / 250 | Idle / total fuel used | L |
| 245 | Total vehicle distance | km |

J1587 uses its own scales, little-endian value lengths and native units:
for example PID 190 uses **0.25 rpm/bit**, not J1939 SPN 190's 0.125.
Fahrenheit, mph, psi and US gallons are converted explicitly into the table's
units. All-ones supported values become `null` using the observed BlueFire
unavailable convention. J1939's upper reserved raw ranges are **not** reused.
Zero values and converted negative temperatures remain valid. PID 101 uses a
signed one-byte raw value; all-ones still means unavailable, not negative one.
The two-byte temperature PIDs use unsigned 0.25-degree Fahrenheit values before
conversion, independently cross-checked against the inspected BlueFire client.
Labels for other PIDs (including text gears and fuel temperature PID 174) do not
imply a verified value decoder.
The [code reference](docs/code-reference.md) records every implemented scale.

PID 194 diagnostic entries preserve MID, PID versus SID namespace, expanded
codes, four-bit FMI, active/inactive status, optional occurrence count and raw
bytes. A missing optional occurrence count is `null`, not zero. An empty list
means **No faults in this report**, not a vehicle-wide all-clear. These are
entries in the current parameter report, not an accumulated historical fault
database. J1587 FMI 15 remains reserved; it is not J1939's least-severe high
threshold. Detroit mappings require an explicit reference profile for lookup;
the live publication path does not infer one from MID 128.

| Topic | Content |
| --- | --- |
| `vehicle/{vehicle}/j1587/availability` | Independent J1587 online/offline status |
| `vehicle/{vehicle}/j1587/{mid}/report` | Raw normalized parameter bytes and dictionary annotation |
| `vehicle/{vehicle}/j1587/{mid}/pid/{pid}` | Human-readable measurement and explicit unit |
| `vehicle/{vehicle}/j1587/{mid}/faults/194` | Current active/inactive diagnostic entries and readable summary |
| `homeassistant/sensor/bluefire_{vehicle}_j1587_{mid}_{pid}/config` | Retained HA discovery with stable, protocol-specific identity |

J1939 and J1587 share the adapter device but never state/entity identities.
For example, **Engine speed - Engine (128)** is a J1587 sensor, distinct from
J1939's **Engine speed - Engine (0)**. Unknown PIDs are raw-only.
States are non-retained QoS 0, discovery/availability retained QoS 1.
J1587 has an independent 60-second freshness watchdog, plus per-entity expiry;
J1939 traffic cannot keep J1587 online. Disconnect/shutdown/reconnect invalidates
both protocols; rediscovery never replays readings. MID/PID ownership is stored
in a separate `j1587_signals` ledger field, preserving old J1939 records and
cleaning up both protocols after prefix changes or entry removal.

Offline raw J1708 replay uses a different framing mode, one complete datagram
per line including checksum, not BlueFire chunks:

```powershell
python .\scripts\analyze_bluefire.py .\j1708.hex --transport j1708
```

Synthetic raw J1708 engine-speed datagram for **1000 rpm**:

```text
80 be a0 0f 13
```

The `--j1587-format` option applies only to vendor `stream`/`padded` PIDData,
not raw `j1708` mode. Invalid hex, checksum, width and diagnostic entries fail
with line-numbered errors. Keep raw vehicle captures private.

### Prepared signals

| PGN | SPN | Measurement | Unit |
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

Counters use MQTT `total_increasing`; other readings use `measurement`.
Numeric raw ranges include `0xFA`, `0xFAFF` and `0xFAFFFFFF` for 1/2/4-byte
signals respectively. Upper reserved/error/not-available encodings produce
`null`. This rule applies only to the catalog's numeric signals, not arbitrary
J1939 enumerations; gears (including the special Park encoding) are not decoded.
Transmission pressures and temperatures are not assertions about a particular
Allison transmission's broadcast configuration.

The added signal positions/scales were cross-checked against these public
implementation references (not normative SAE or vehicle certification):

- [MeatPi's numeric J1939 definitions and valid ranges](https://github.com/meatpiHQ/meatpi-components/blob/d8cd667e4da19813977f3466423ecc93dc84b650/components/j1939/j1939_spn_core.c#L37-L103).
- [CANboat's J1939 field layouts and SPN identities](https://github.com/canboat/canboat/tree/3de4c8463383e33e74f71232f4b4315ee4600f7c/database/j1939/pgns),
  specifically PGNs 65244, 65257, 65262, 65263, 65270, 65272 and 65276.
- [ISOIdent's signal table](https://github.com/florianeidner/isoident/blob/0ab94791c1fb76183ae27fdb242f2ab1b1159913/datasets/signals.CSV#L5284-L5372)
  for ambient conditions, transmission fluid and charging potential.
- [Public counter DBC definitions](https://github.com/JoaoCBFreitas/SNMPVeicular/blob/49a8317c65ac3011ccabc71293e0f44eee1ae942/projeto/SocketCAN/J1939/J1939.dbc#L44-L57)
  for idle/fuel counters and their engineering maxima.

This is a decoder catalog, **not a promise that this coach supplies every signal**.
Verify the ECM, diagnostic connector, bus wiring and J1939/J1708 availability on
the actual coach. Do not infer ignition state from adapter power or CAN activity.
Do not use these readings for safety-critical vehicle control or alarms.

## Remaining native BLE work

The [adapter product page](https://bluefire-llc.com/adapter) identifies the vendor
product family, not a verified BLE wire specification. Record the actual adapter
model, hardware revision, firmware and BLE-versus-Classic transport when available.
Bluetooth Classic adapters are outside this integration's BLE scope.

The supplied [BlueFire Android API reference](https://github.com/asoca/BlueFire-API-for-Android)
contains a demo and compiled Java SDK. Its README directs developers to
`support@bluefire-llc.com` for documentation. It does not expose the BLE framing,
GATT UUIDs, authentication, subscription commands or raw telemetry encoding in
the readable demo. Its older compatibility limits must not be applied blindly to
current adapters. No vendor binaries or translated proprietary implementation
are bundled here.

### Findings from Android 9.7.5

The locally supplied APK was inspected as a ZIP, its Xamarin assembly store
identified, and the relevant managed types examined with ILSpy 9.1.0.7988.
The application logic is in the LZ4-compressed `BlueFire` assembly, not just
the Android Java/Dalvik layer. No APK, DLL, decompiled source, authentication
material, or actual vehicle captures are included in this repository.
APK SHA-256:
`e838af5f52adc3503b81814e562486d8f8f4b14ce56330206870ef04256c395e`.
The version is the supplied filename's label, not independent vendor provenance.

These are **static observations of this app build, not a verified adapter
specification**. Method names below identify the evidence without reproducing
the app's implementation:

| Area | Observation | Evidence in the managed assembly |
| --- | --- | --- |
| Receive framing | Two big-endian length bytes, their XOR byte, a nonempty message body, and one checksum byte | `CommBase.GetDataLength`, `CheckPackets` |
| Receive checksum | Complement of the body's 8-bit end-around-carry sum; excludes the three header bytes | `CommBase.CalcChecksum` |
| Direction matters | Client writes instead use a two-byte length and a checksum that also includes those length bytes, plus a legacy BLE packet selector | `CommData.SendData`, `CommBaseBLE.SendData` |
| Report dispatch | Command 151 is PGNData, 154 is PIDData, 174 is OBDData; 255 is heartbeat | `PIDCommands`, `CommData.CheckPid` |
| PGN report | Source byte, big-endian 16-bit PGN field, priority byte, data-page byte, data-length byte, then variable-length data | `CommData.AddPGNData`, `Helper.BytesToUInt16` |
| Byte order | Vendor envelope fields are big-endian; standard CAN signal values remain little-endian | `Helper.BytesToUInt16`, `CANToInt16`, `CommData.ProcessPGN` |
| J1587 firmware split | Before firmware 3.19: big-endian 16-bit PID; 3.19+: up to three `FF` page extensions followed by a PID byte | `CommData.AddPIDData` |
| Transport variants | Original BLE uses separate adapter/client characteristics; EZ uses a serial-like service; Bluetooth Classic is another path | `CommBaseBLE.SetGuids`, `CommBLE.GetServices` |
| Fragment handling | Receive chunks are accumulated; serial/Classic paths preserve trailing messages, while original BLE discards the completing notification's tail | `CommBase.CheckPackets` |
| Connection lifecycle | Version/time exchange, compatibility, authentication, bus availability, filters and heartbeat are separate concerns | `CommData.StartAuthentication`, `CheckPid`, `FinishAuthentication` |

The original BLE UUID candidates observed in `CommBaseBLE` are:

| Role | UUID |
| --- | --- |
| Adapter service | `b65d50ef-db0a-4f24-9e32-189bf1d5f6d5` |
| J1939 notification characteristic | `c5a7757d-04e7-410a-aa0f-2614427fb1f6` |
| J1708 notification characteristic | `b972d4e5-238c-43a3-8dab-c3265268b978` |
| Client service | `1d7f10c5-a793-43d5-82b2-464a74e795be` |
| Client packet 1 / 2 / 3 | `4526e59b-a6e6-40ea-a842-972883e7fb3c` / `de106755-294c-4b02-8103-06be37461300` / `17e7a79a-9bcc-4f15-9508-c84cc9179101` |
| EZ service | `65333333-a115-11e2-9e9a-0800200ca100` |
| EZ receive / client write | `65333333-a115-11e2-9e9a-0800200ca102` / `65333333-a115-11e2-9e9a-0800200ca101` |

Compare these candidate UUIDs with the explicit `bluefire.inspect_adapter`
inventory when available. They may guide internal listener development, but are
not proof of hardware compatibility. Device names and manufacturer ID `FFFF`
alone are not reliable identity checks. Keep reception limited to telemetry;
do not send vehicle-control or diagnostic commands.

**Important contract boundary:** a PGN report is not necessarily an original
eight-byte CAN frame. It has no explicit full arbitration ID, can contain
transport-protocol data, and its PDU1/destination and data-page interpretation
need captures. The app also handles BAM/RTS separately. The offline parser
preserves these metadata bytes without inventing a CAN ID, padding short data,
decoding transport packets, or relabeling J1587/OBD as J1939. It does not associate
the app's separate arbitration-ID response with reports without correlation
evidence. A future live driver must either prove that association or introduce
a separately versioned PGN-report contract; it cannot silently fabricate the
raw-frame fields of the existing MQTT contract.

### Cross-version findings: Android 11.2.3 and Windows 12.5.6

Both newer packages were inspected locally without executing the applications
or their installer scripts. Android's binary manifest identifies
`com.bluefire_llc.apps`, version name `11.2.3`, version code `122`. The Windows
MSIX manifest identifies `BlueFireLLC.BlueFireApps`, version `12.5.6.0`, x64.
These are package-declared identities, not independent signature verification.

| Package | SHA-256 |
| --- | --- |
| Android 11.2.3 APK | `bcf59700abbbacd0e0faf10819c87acc83d69cf4dd56a9556417def9d85fd6aa` |
| Windows `Apps_12.5.6.0_x64.msix` | `0ab3ccfceee263fb8d8924d11733aa89cbcfe6bc95f9527b1d40067cf9f4e696` |

Android 11.2.3 stores `Apps.dll` in a version-2 assembly store inside the
`payload` ELF section of `libassemblies.arm64-v8a.blob.so`; its app image is
LZ4-compressed. The Windows MSIX contains `Apps.dll` directly. The targeted
managed types were examined using the same ILSpy version as above; no native
application code was run. Extracted assemblies and decompiled material were
removed after the comparison and are not dependencies of the integration.

| Area | Evidence in the newer builds | Consequence for this project |
| --- | --- | --- |
| Receive envelope | `CommBase.GetDataLength` and `CalcChecksum` match between the two newer builds, ignoring whitespace, and retain the earlier observed format | No speculative new framing variant or checksum is needed |
| Telemetry reports | `PIDCommands`, `CommData.AddPGNData`, `AddPIDData`, `AddOBDData` retain commands 151/154/174 and their field layouts; both newer PIDData handlers use extensions without the older legacy-format branch | Keep report types separate and select the actual firmware format explicitly; app version is not adapter firmware |
| BLE service family | Android `CommBaseBLE.SetGuids` and Windows `CommBase.SetGuids` use only the EZ service/receive/send UUIDs listed above; both `IsValidAdapter` paths explicitly reject the exact name `BlueFire LE` | Original LE support cannot be inferred from the newer apps; keep older UUID findings separate from modern EZ findings |
| Notification routing | Both `CommBLE.GetCharacteristicData` paths accept notifications from receive **and send** characteristics and feed one packet queue | A characteristic named "send" does not make its incoming notifications client writes; preserve direction and callback order |
| Stream handling | Both `CommBase.CheckPackets` implementations preserve bytes after each complete message | Modern captures use stream mode, not legacy padding/discard assumptions |
| Startup/control evolution | `CommData.CheckPid` starts version exchange on the first heartbeat and branches between firmware 3.x and 4.x; `PIDCommands` adds authentication command 169 and calls command 177 `GetBuildDate` instead of the earlier `GetFirmware` | Do not transplant the 9.7.5 startup sequence or assign version-independent meaning to opaque control bodies |
| Recovery policy | Both `CheckPacketErrors` call `CheckAnotherPGN`, which looks for `0F 0F 97` around a candidate PGN packet | This is an app heuristic, not a proven synchronization marker; our parser still raises and clears fragments instead of scanning payloads |
| Empty PGN data | Windows `AddPGNData` rejects zero length; the Android handler has no equivalent explicit zero-length check | Preserve empty reports as opaque analysis data, but never manufacture signal values from them |
| Numeric missing data | `Helper.IsHexFF` checks all-`FF` fields, and many `ProcessPGN` branches skip assignment when missing | Do not emulate stale-value retention or weaken our catalog's reserved/error handling to match the display app |
| Raw recording | `CommBase.QueuePacketData`, `RecordData`, `PlayRecording` use `Adapter.txt`: one hex-encoded incoming queue chunk per line | Existing local replay can consume that recording format without running the vendor app or converting it to invented CAN frames |

The format agreement strengthens the static evidence, **not** the claim of
hardware compatibility. The 264-byte analysis ceiling remains a safety policy,
not a measured firmware maximum. The initial comparison added no outgoing
commands. The opt-in unsecured J1708 startup implementation described above
now uses a bounded subset of the observed exchanges, without credentials,
pairing or adapter-setting changes.
The control and arbitration-ID messages remain opaque; interleaving an
arbitration-ID response with PGN reports does not establish a reliable mapping.

Additional synthetic regressions cover modern stream tails across notification
fragments, PGN-header-like bytes inside opaque messages, fail-closed handling of
corruption before plausible packets, newer control messages interleaved with
telemetry, `Adapter.txt` line endings/spacing, and valid-to-invalid MQTT values
without retaining an old value or borrowing another source's reading.
There are still no real adapter recordings in the tests.

### Heartbeat-only EZ startup investigation

A user-supplied EZ diagnostic capture on 2026-10-25 established a working BLE
connection and the expected EZ service/characteristics. Its 20-second capture
contained 38 checksum-valid heartbeat packets, with no PGN, PID or OBD reports.
The live receiver also counted only heartbeats before the capture. This
validates heartbeat receive framing on that adapter, not authentication,
vehicle-bus availability or telemetry decoding. The coach's J1708 bus is
user-confirmed; it cannot be identified from these heartbeat packets alone.

Targeted static reinspection of the previously supplied Windows 12.5.6 package
(same SHA-256 as above) identifies the missing application-level exchanges:

| Stage | Observed behavior | Evidence |
| --- | --- | --- |
| BLE transport | Subscribe to both EZ receive and send characteristics; write client packets to the send characteristic ending `ca101` | `CommBLE.StartNotifications`, `GetCharacteristicData`, `WaitForWrittenData` |
| First heartbeat | Command 255 starts version negotiation once per connection, rather than being ignored indefinitely | `CommData.CheckPid` |
| Firmware 3.x negotiation | Request command 0 (`GetVersion`), inspect the response, send platform/build-date queries and command 9 (`AppVersion`), then require a positive compatibility response | `GetAdapterVersion3`, `SendVersions3`, `SendAppVersion3` |
| Firmware 4.x negotiation | Start with a different command 9 payload containing application major/minor/patch and platform; do not reuse the 3.x layout | `SendVersions4`, `SendAppVersion4` |
| Authentication | 3.x sends commands 130 and 171; 4.x sends command 169. Authentication responses gate subsequent initialization | `CheckAuthentication`, `CheckPid` |
| Connected initialization | Read firmware-specific adapter variables and bus settings, then synchronize command 8 (`AppIsConnected`) | `RetrieveData`, `SendGetVariables3`, `SendGetVariables4` |
| J1708 subscriptions | Command 155 (`AddPID`) selects MID, PID, on-request behavior, retrieval mode and interval; the incoming measurement command is 154 (`PIDData`) | `AddPID`, `AddPIDData`, `PIDCommands` |
| Report flow control | Page data setup can stop reports with command 153, install subscriptions, then explicitly restart reports with that command | `HomeBase.ConnectData`, `DataConnected`, `CommData.StartSendingData` |

At the time of this capture, the receiver implemented only the first stage's
subscriptions and incoming parsing. The opt-in startup implementation now
provides the missing exchanges. Repeating a passive diagnostic capture still
does not exercise startup; inspect the pre-capture live startup state instead.

Important implementation boundaries:

- **Client framing differs from receive framing.** The inspected modern EZ
  writer uses two big-endian body-length bytes, the body, and a complemented
  end-around-carry checksum covering both length bytes and the body. It does
  not add the receive header's length-XOR byte or an original-LE packet
  selector. Writes go to `ca101`, not the writable receive characteristic.
- **Authentication is not necessarily a password prompt.** With no configured
  username/password or device/adapter binding, the inspected 3.x path sends
  zero-length authentication data and the 4.x path sends three zero-length
  fields. Secured adapters use encrypted data instead. Empty fields are a
  normal unsecured-client path, not proof that a secured adapter will accept
  them. Never reset security or fall back after rejection.
- **Firmware selection is separate from PID report format.** The app uses
  version-bearing device names to select its 4.x path; an unversioned
  `BlueFire EZ` name takes its 3.x path. That is evidence of the app's
  selection rule, not proof of this adapter's firmware. The integration's
  `j1587_extended` setting only selects how incoming PID reports are parsed.
- **Subscriptions and bus enablement are distinct.** `AddPID` contains a
  big-endian 16-bit PID even when incoming PID reports use page extensions.
  It also distinguishes monitoring from on-request retrieval, which can
  cause vehicle-bus requests. Read the J1708 ignore/availability state before
  deciding whether a missing measurement means a bus, filter or ECU issue.
  The notification-status setting is not a substitute for PID subscriptions
  and report flow control.
- **Do not replay the whole vendor initialization routine.** It can change
  adapter variables, bus-ignore flags and other settings to match its UI.
  A telemetry implementation should preserve existing settings, reject
  incompatible/authentication failures explicitly, use bounded response
  waits, rebuild session subscriptions on reconnect and never send fault-clear,
  reset, firmware-flash or arbitrary vehicle-transmit commands.

The next hardware gate is a firmware/security-confirmed, bidirectional startup
trace from the implemented sequence, first obtaining a valid version response,
then compatibility/authentication responses, and finally a narrowly scoped
J1708 subscription such as engine MID 128 / engine-speed PID 190. Do not claim
telemetry readiness until actual PIDData reports arrive. The passive capture
does not contain the adapter firmware, authentication result or J1708
availability response. A later live diagnostic confirms firmware 3.23.0,
accepted compatibility/authentication and an initial false J1708 availability
response. The vendor client queries that status without treating it as a
connection failure; passive report setup must not be blocked by it. The
implementation sends only the normal unsecured authentication fields and
never includes vendor code, keys or captured security payloads.

### Offline replay and resilience checks

`custom_components/bluefire/protocol.py` is an independent, receive-only
behavioral parser with no Home Assistant, BLE or MQTT I/O. Both the live
receiver and offline analyzer use it. `ReceiveDecoder` supports split headers/payloads,
concatenated stream messages, and explicit zero-padded notification mode.
It rejects invalid header XORs, checksum failures, inexact inner lengths and
over-limit packets with `ProtocolError`, clearing pending data on failure.
It deliberately does not scan arbitrary bytes for a plausible new header:
there is no verified synchronization marker, and the checksum is not
cryptographic authentication.

The analysis limit is **264 total bytes / 260 body bytes**, informed by the
app's `MaxReceiveLength` constant, not a proven universal firmware limit.
Pending storage never exceeds 264 bytes, even with large concatenated input.
Original BLE tail bytes are accepted only when zero; nonzero padding,
coalesced legacy packets and larger firmware formats require investigation,
not silent acceptance. Use one decoder per independently framed stream/session;
call `reset()` on disconnect and `finish()` at capture end to reject truncation.
J1587's firmware format must be selected explicitly, never inferred by trying
both parsers. Control/heartbeat messages cannot establish vehicle availability.

For local analysis, create an ASCII file containing **adapter-to-client
notification values only**, one hex chunk per line. Keep directions and
connection sessions separate, and retain characteristic metadata in the
original capture. Do not feed a full HCI/btsnoop file, client writes, or unrelated
BLE traffic directly. Select the framing mode from the observed transport, not
the device name alone:

```powershell
python .\scripts\analyze_bluefire.py .\capture.hex --transport stream
python .\scripts\analyze_bluefire.py .\capture.hex --transport padded --j1587-format extended
```

If you obtain an `Adapter.txt` recording from either newer app, its raw hex-line
format already fits the analyzer:

```powershell
python .\scripts\analyze_bluefire.py .\Adapter.txt --transport stream --j1587-format extended
```

Preserve the file's chunk order: those apps record a single receive queue
shared by both EZ characteristics, not separate independent per-characteristic
files. For other raw captures, establish the correct stream grouping before
merging or separating characteristic values; this tool cannot infer it.
The recording has no timestamps or characteristic identifiers, so it cannot
prove reporting cadence, notification provenance, or session boundaries.
It may also contain handshake/security-related data; keep the original private.
This is a format observation, not a guarantee that recording/export controls
are exposed by every app build.

`stream` accepts arbitrary unpadded chunks; `padded` treats each input line as a
legacy notification, allowing fragments across lines but dropping only zero
padding after a completed packet. The script emits local JSONL records with
explicit report kinds and `hardware_verified: false`. J1939 measurements are
shown only for matching page-zero PGNs with exactly eight data bytes; unknown,
short or long PGN data stays opaque. Supported J1587 PIDs and diagnostics use
their own value decoder; malformed supported values raise errors rather than
producing zero. It never publishes MQTT or marks telemetry
online. Any parse/file error returns nonzero; discard earlier output from that
run rather than treating a partial capture as wholly valid. Files and output
can contain vehicle identity or location; do not commit or share them unredacted.

Example **synthetic**, not an adapter capture, representing 1000 rpm:

```text
00 0f 0f 97 00 f0 04 06 00 08 ff ff 7d 40 1f ff ff ff 88
```

Regression coverage includes every two-chunk split, byte-at-a-time delivery,
deterministic randomized fragmentation/coalescing, receive-length boundaries,
checksum carry/bit corruption, truncation, session reset, padding ambiguity,
inner length mismatches, explicit J1587 formats, unknown/control commands and
the MQTT frame/report boundary. Signal decoding now rejects incomplete data
instead of letting an empty/partial slice become a plausible zero/low value.
These vectors establish internal behavior, not vendor/hardware compatibility.

The internal receiver now follows the documented modern EZ connection and
notification observations without verified adapter traces or actual-hardware
testing. Keep assumptions visible and treat hardware validation as a gate before
declaring a full public release:

1. The receiver subscribes to the modern EZ receive and client-write notification
   characteristics; both are routed through one ordered stream decoder. It sends
   no adapter writes unless J1708 startup is explicitly enabled. The unsecured
   startup exchange and passive monitoring commands are implemented separately
   with response deadlines and fail-closed error handling.
2. Receive framing and report routing are exercised with synthetic fixtures.
   PGN reports do not establish original CAN identifiers: never guess one to call
   `MqttBridge.async_process_frame(Frame(can_id, data))`. Where the report format
   does not provide a complete CAN frame, preserve it as a distinct report
   contract rather than fabricating frame fields.
3. BLE cancellation, bounded reconnect/backoff, MQTT offline handling, and a
   provisional report freshness policy are integrated. Do not replay stale
   values merely to defeat sensor expiry.
4. Before a full public release, validate the supported adapter variants,
   protocol assumptions, signal values, missing-data behavior and reporting
   cadence against real adapter traces and hardware. Internal implementation and
   synthetic testing do not require those release checks to be completed first.

## HAVRV relationship

[HAVRV](https://github.com/cmmtchll/HAVRV) is the architectural reference for
config-entry-based setup, device grouping and diagnostics. It organizes existing
HA entities; it is not a Bluetooth driver. Once the receiver is completed, map
the discovered MQTT sensors into HAVRV's chassis/power systems. There is no
runtime dependency on HAVRV or duplication of its RV profile/dashboard code.

## Integration or app?

**Keep this as an integration for direct Home Assistant use.** BLE notification
callbacks, reconnect timers and MQTT publishing are asynchronous work that fits
HA's event loop. Use HA-managed tasks and timer helpers, avoid blocking I/O or
`while`/sleep polling in callbacks, and cancel/unsubscribe on entry unload.
Nothing here requires a cron scheduler or a separate container for timing.
The J1939 decoder/publisher remains transport-independent and testable.

An **app** (formerly add-on) is a separate service/container. Choose that path if
you need collection to survive HA Core restarts, an independent MQTT connection
and Last Will, native/vendor libraries incompatible with HA, process isolation,
or HA-independent logging/consumers. A Supervisor-managed app targets HA OS;
a standalone service/container is the equivalent for other hosts. A separate
bridge may need its own Bluetooth access/proxy support; it cannot assume HA's
Bluetooth APIs are available outside HA.

For a genuinely HA-independent, MQTT-first vehicle gateway, that independent
service would be a sensible architecture—not “better scheduling” by itself.
Avoid running two receivers against the same adapter. Neither packaging choice
solves the still-missing verified BlueFire BLE protocol.

References: [HA MQTT discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery),
[MQTT sensor expiry](https://www.home-assistant.io/integrations/sensor.mqtt/),
[Bluetooth APIs](https://developers.home-assistant.io/docs/core/bluetooth/api/),
and [HA architecture](https://developers.home-assistant.io/docs/architecture_index/).

## Development checks

From the repository root, run:

```sh
python -m pip install -r "$PWD/requirements-dev.txt"
python -m unittest discover -s "$PWD/tests" -v
python -m pycodestyle "$PWD/custom_components" "$PWD/tests" "$PWD/scripts"
python "$PWD/scripts/quality_scale_audit.py"
```

Use Python 3.12+ for these isolated checks; running the integration requires
HA's supported Python version. PEP 8 uses the default **79-character limit**
with no ignored violations. To apply formatting before checking:

```sh
python -m autopep8 --in-place --recursive "$PWD/custom_components" "$PWD/tests"
```

Tests use synthetic complete CAN frames and injected MQTT/BLE/HA boundary mocks;
they do not publish to a broker or contact a device. They cannot establish
BlueFire compatibility or replace testing in a running HA instance. Config-flow
tests use HA's real schema library, Voluptuous, while mocking flow-manager
helpers; it is supplied by HA in production. Development dependencies are pinned
separately and do not add packages to the integration's runtime requirements.
Pull requests also run the test suite and quality-scale audit, PEP 8 checks,
HACS validation, and Home Assistant's hassfest validation. See
[`QUALITY_SCALE.md`](QUALITY_SCALE.md) for the checklist's meaning and current
limitations; an audit is not a quality-tier certification.
