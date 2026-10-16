# BlueFire for Home Assistant

Preparation for a **direct BLE → Home Assistant → MQTT** integration, initially
focused on a 2003 Detroit Diesel / Prevost H3-45 Liberty Coach Elegant Lady.
No Android gateway is required or planned.

> **Status: groundwork, not a working BlueFire receiver.** You can configure the
> integration offline and inspect a powered adapter's BLE service metadata.
> Continuous BLE reception, BlueFire authentication/framing, and reconnection of
> a live telemetry stream are **not implemented**. No vehicle readings are
> fabricated, and connecting to BLE alone never marks telemetry online.

## What is ready

- UI setup with nearby-device selection or offline manual MAC entry, duplicate
  prevention, and reconfiguration without changing entity/MQTT identity.
- Diagnostic `Protocol status` sensor showing `protocol_required`.
- Explicit, read-only BLE GATT inspection via Home Assistant's connectable
  Bluetooth scanners, including compatible proxies.
- Transport-independent decoding of 37 byte-aligned J1939 SPNs, including
  reserved/error/not-available handling, engineering units, and source addresses.
- MQTT publishing/discovery code, source-separated readings, raw frame output,
  retained availability, freshness watchdog, durable discovery ownership,
  broker reconnect/birth handling, and non-retained live state.
- Hardware-free unittest tests, real configuration-schema validation, and
  repeatable PEP 8 checks.

The MQTT publisher is deliberately **not connected to BLE notifications yet**.
BlueFire notification payloads are not assumed to be raw CAN frames.

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
   visible, or **Enter a MAC address manually (works offline)** otherwise.
   The nearby list includes all connectable BLE devices, not verified BlueFire
   matches. Select only the adapter you recognize; confirm or correct its MAC
   and name on the following form. Setup never connects to or probes a device.
4. Enter a vehicle MQTT identifier. `liberty_h3_45` is the default identifier,
   not a vehicle-detection rule. The identifier must be unique and use 1–64
   lowercase letters, digits, underscores or hyphens, starting with a letter
   or digit. Blank adapter names and duplicate MACs/topics are rejected.
5. Configuration does not require the adapter nearby. Expect **Protocol required**,
   an offline MQTT availability message, and **no engine MQTT sensors yet**.

No broker credentials are stored by this integration; it uses HA's MQTT client.
There are no adapter passwords or PGN transmit/reset controls.

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
4. Add BlueFire as described above. The integration prepares its stable MQTT
   vehicle namespace, but no measurements or MQTT-discovered engine device will
   appear until the native receiver is completed and valid frames arrive.
5. When live reception is available, all measurements from one adapter are
   grouped under one MQTT-owned device with stable identifiers. The BlueFire
   integration's diagnostic device remains separate; do not manually create
   duplicate MQTT YAML sensors or assume HA merges devices across config entries.
   MAC corrections do not change MQTT topics or unique IDs.

In the MQTT integration's **Configure → Listen to a topic** tool, listen to
`vehicle/liberty_h3_45/j1939/#` (replace the vehicle ID). Expect retained `offline`
in preparation mode, not sample engine data. Once receiving, inspect numeric
`value`, explicit `unit`, PGN, SPN, source address and UTC timestamp. An external
MQTT client can subscribe to the same topics; it does not need Home Assistant
discovery to understand the JSON.

On permanent BlueFire entry removal, retained discovery definitions are cleared
with empty retained payloads, including those known before a restart. Ordinary
unload/reload keeps discovery, but marks the stream offline. Removal while the
broker is down is recorded in HA storage and retried on reconnect while HA is
running. If HA restarts with no BlueFire entries left, pending cleanup resumes
the next time BlueFire is set up. Do not delete that storage before cleanup.
Discovery-prefix changes similarly withdraw the previous prefix's definitions.
Only source/SPN ownership is persisted—never live readings or broker credentials.

### Find and specify the Bluetooth MAC address

Use the **BlueFire peripheral's** BLE address, not your HA computer, phone,
ESPHome proxy, Wi-Fi adapter or vehicle VIN. With the adapter powered, use the
nearby-device list above or the Bluetooth advertisement monitor in HA's Bluetooth
integration to match the adapter's name and address. Names alone are not proof
of device identity. The selection list excludes already configured addresses.
There are no automatic discovery matchers until BlueFire identifiers are verified.

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
subscribe to notifications, authenticate, or send adapter commands. Offline
adapters fail with an actionable error instead of repeated background attempts.

The integration's downloadable diagnostics include the last successful inventory
and protocol status, but omit the Bluetooth address, vehicle label, VIN, and raw
telemetry. A GATT inventory helps identify the adapter; it does **not** establish
the wire protocol. Do not publish captures containing vehicle identity or location.

## MQTT contract

There is no universal OBD/CAN/J1939 MQTT topic standard. This project uses an
explicit, versioned J1939 contract rather than pretending SPNs are OBD-II PIDs.
Future J1708/J1587 support needs a separate decoder/protocol label; it must not
silently masquerade as J1939.

For a vehicle identifier `liberty_h3_45` and engine source address `0`:

| Topic | Content |
| --- | --- |
| `vehicle/liberty_h3_45/j1939/availability` | `offline` or `online` |
| `vehicle/liberty_h3_45/j1939/0/frame` | CAN arbitration ID, extended-frame flag, DLC, PGN, priority, source address and hex payload |
| `vehicle/liberty_h3_45/j1939/0/spn/190` | Engine-speed measurement in rpm |
| `homeassistant/sensor/bluefire_liberty_h3_45_0_190/config` | Retained HA MQTT sensor discovery |

Example **synthetic** measurement illustrating the schema, not received data:

```json
{
  "schema_version": 1,
  "protocol": "j1939",
  "vehicle_id": "liberty_h3_45",
  "pgn": 61444,
  "source_address": 0,
  "timestamp": "2026-01-01T00:00:00+00:00",
  "spn": 190,
  "value": 1000.0,
  "unit": "rpm"
}
```

Timestamps are UTC ingestion time, not ECU timestamps. Numerical invalid values
become JSON `null`, never zero or `"NA"`; MQTT discovery converts null to HA's
explicit `None`/unknown state rather than preserving an old value. Valid negative
temperatures/torque are preserved. Unknown PGNs pass through as raw frames without
guessed signals.
PDU1 destination addresses are excluded from PGNs. Transport-protocol multi-packet
messages, DM1 faults, manufacturer-specific signals, and CAN FD are not decoded.

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

The topic/payload contract remains version 1 and existing entity IDs are
preserved. The additional raw-frame fields are additive, not renamed fields.

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

To complete reception, obtain the applicable protocol and usage permissions, then:

1. Implement the verified connection/authentication/subscription sequence using
   Home Assistant's Bluetooth APIs; do not guess UUIDs from characteristic names.
2. Reassemble and validate BlueFire messages, extracting complete J1939 CAN
   frames before calling `MqttBridge.async_process_frame(Frame(can_id, data))`.
3. Manage BLE cancellation and bounded reconnect/backoff; notify the MQTT bridge
   of transport loss. The MQTT ownership ledger and freshness watchdog are
   already prepared, but the future receiver must integrate its own lifecycle
   and verify an appropriate reporting cadence for each signal.
4. Verify signal values and missing-data behavior against the vendor app and
   recorded fixtures from the actual adapter. On-change delivery needs a verified
   refresh policy; do not replay stale values merely to defeat sensor expiry.

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
python -m pycodestyle "$PWD/custom_components" "$PWD/tests"
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
