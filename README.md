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

- Offline config flow with unique Bluetooth addresses and vehicle identifiers.
- Diagnostic `Protocol status` sensor showing `protocol_required`.
- Explicit, read-only BLE GATT inspection via Home Assistant's connectable
  Bluetooth scanners, including compatible proxies.
- Transport-independent decoding of 14 byte-aligned J1939 SPNs, including
  reserved/error/not-available handling, engineering units, and source addresses.
- MQTT publishing/discovery code, source-separated readings, raw frame output,
  availability, broker reconnect handling, and non-retained live state.
- Hardware-free tests using Python's standard library.

The MQTT publisher is deliberately **not connected to BLE notifications yet**.
BlueFire notification payloads are not assumed to be raw CAN frames.

## Install and prepare

Use Home Assistant Core **2026.10 or later**, with its MQTT integration configured
for your broker and its Bluetooth integration configured for connectable BLE.
This foundation has hardware-free tests, not a verified full Home Assistant or
vehicle commissioning run.

1. Copy the repository's `custom_components/bluefire` directory into your
   Home Assistant configuration's `custom_components` directory and restart HA.
2. In **Settings → Devices & services → Add integration**, select **BlueFire**.
3. Enter the adapter's Bluetooth MAC address, an adapter name, and a vehicle MQTT
   identifier. `liberty_h3_45` is the default identifier, not a vehicle-detection
   rule. The identifier must be unique and use 1–64 lowercase letters, digits,
   underscores or hyphens, starting with a letter or digit.
4. Configuration does not require the adapter nearby. Expect **Protocol required**,
   an offline MQTT availability message, and **no engine MQTT sensors yet**.

No broker credentials are stored by this integration; it uses HA's MQTT client.
There are no adapter passwords or PGN transmit/reset controls.

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
| `vehicle/liberty_h3_45/j1939/0/frame` | Full CAN identifier, PGN, priority, source address, eight data bytes in hex |
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
explicit `None`/unknown state rather than preserving an old value. Valid negative temperatures/torque are
preserved. Unknown PGNs are passed through as raw frames without guessed signals.
PDU1 destination addresses are excluded from PGNs. Transport-protocol multi-packet
messages, DM1 faults, manufacturer-specific signals, and CAN FD are not decoded.

Live state/raw frames use QoS 0 and are not retained. Discovery is retained.
Retained availability stays `offline`; transient `online` messages are sent only
on frames, so a new subscriber cannot revive an old retained online state.
Individual sensors expire after 60 seconds without an update; online adapter
availability is not proof that every measurement is current. MQTT reconnect
resets availability and replays definitions known during that runtime, not cached
measurements. No lossless recording, cross-restart discovery registry, or live
stream watchdog is claimed at this stage.

### Prepared signals

| PGN | SPN | Measurement | Unit |
| --- | --- | --- | --- |
| 61444 | 190 / 513 | Engine speed / actual torque | rpm / % |
| 61443 | 91 / 92 | Accelerator position / engine load | % |
| 65262 | 110 / 175 | Coolant / engine oil temperature | °C |
| 65263 | 100 / 109 / 111 | Oil pressure / coolant pressure / coolant level | kPa / kPa / % |
| 65265 | 84 | Wheel-based vehicle speed | km/h |
| 65266 | 183 | Engine fuel rate | L/h |
| 65253 | 247 | Total engine hours | h |
| 65248 | 245 | Total vehicle distance | km |
| 65271 | 168 | Battery potential | V |

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
3. Manage cancellation, bounded reconnect/backoff, disconnect availability,
   per-signal freshness and a live-stream watchdog. Persist discovery identifiers
   for clean entry removal and cross-restart re-advertisement.
4. Verify signal values and missing-data behavior against the vendor app and
   recorded fixtures from the actual adapter. On-change delivery needs a verified
   refresh policy; do not replay stale values merely to defeat sensor expiry.

## HAVRV relationship

[HAVRV](https://github.com/cmmtchll/HAVRV) is the architectural reference for
config-entry-based setup, device grouping and diagnostics. It organizes existing
HA entities; it is not a Bluetooth driver. Once the receiver is completed, map
the discovered MQTT sensors into HAVRV's chassis/power systems. There is no
runtime dependency on HAVRV or duplication of its RV profile/dashboard code.

## Development checks

From the repository root, run:

```sh
python -m unittest discover -s "$PWD/tests" -v
```

Tests use synthetic complete CAN frames and injected MQTT/BLE/HA boundary mocks;
they do not publish to a broker or contact a device. They cannot establish
BlueFire compatibility. No external test dependencies are required.
