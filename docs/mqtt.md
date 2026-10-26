# MQTT reference

[Home](../README.md) · [Setup](getting-started.md) · [Telemetry](telemetry.md)

BlueFire uses Home Assistant's shared MQTT client. There is no universal
OBD/CAN/J1939 MQTT standard: this is an explicit **schema-version-1** contract,
not a drop-in schema for OVMS, Torque, or every CAN gateway. Downstream
applications must map their own schemas rather than relabel SPNs as OBD PIDs.

## Topics

Topics separate the vehicle, protocol, and reporting controller. J1939 source
addresses and J1587 MIDs never share state or entity identities.

### J1939

For vehicle `liberty_h3_45` and engine source address `0`:

| Topic | Content |
| --- | --- |
| `vehicle/liberty_h3_45/j1939/availability` | `online` or `offline` |
| `vehicle/liberty_h3_45/j1939/0/frame` | Complete CAN frame metadata and hex payload |
| `vehicle/liberty_h3_45/j1939/0/report/61444` | Vendor PGN report metadata and bytes, without a fabricated CAN ID |
| `vehicle/liberty_h3_45/j1939/0/spn/190` | Engine-speed measurement in rpm |
| `vehicle/liberty_h3_45/j1939/0/faults/65226` | Active faults, summary, lamps, and raw DTCs |
| `vehicle/liberty_h3_45/j1939/3/faults/65227` | Transmission previously active faults, separate from active faults |
| `homeassistant/sensor/bluefire_liberty_h3_45_0_190/config` | Retained sensor discovery, using the configured discovery prefix |

### J1587

| Topic | Content |
| --- | --- |
| `vehicle/{vehicle}/j1587/availability` | Independent J1587 online/offline state |
| `vehicle/{vehicle}/j1587/{mid}/report` | Raw normalized parameter bytes and dictionary annotation |
| `vehicle/{vehicle}/j1587/{mid}/pid/{pid}` | Decoded measurement, status, or identification |
| `vehicle/{vehicle}/j1587/{mid}/faults/194` | Current active/inactive diagnostic entries and summary |
| `homeassistant/sensor/bluefire_{vehicle}_j1587_{mid}_{pid}/config` | Protocol-specific discovery identity |

Unknown PIDs remain raw-only. Identification uses PIDs 234, 237, and 243;
see [identification behavior](j1708.md#controller-identification).

### Protocol diagnostics

Each MQTT vehicle device has J1939 and J1587 **telemetry connectivity** binary
sensors. They use retained protocol availability: `online` maps to Connected
(`on`), `offline` to Disconnected (`off`). They are read-only status indicators,
not switches, and remain readable while telemetry is offline.

Each protocol also has a **last data seen** diagnostic timestamp sensor at
`vehicle/{vehicle}/{protocol}/last_data`. Its retained JSON contains `timestamp`,
an ISO 8601 observation time. Updates are limited to once per 15 seconds while
receiving; the latest observation is flushed on disconnect or expiry.
Heartbeats, identification replay, and rediscovery do not advance it.

## Payload example

This is a **synthetic schema example**, not received vehicle data:

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
  "catalog_version": 3,
  "timestamp": "2026-01-01T00:00:00+00:00",
  "spn": 190,
  "name": "Engine speed",
  "description": "Engine speed, reported in revolutions per minute (rpm). Reserved, error and unavailable values are reported as null.",
  "value": 1000.0,
  "unit": "rpm"
}
```

Timestamps are UTC ingestion times, not ECU timestamps. Invalid numeric values
become JSON `null`, never zero or `"NA"`; live measurement discovery converts
null to HA's explicit `None`/unknown state instead of preserving an old value.
Valid negative temperatures/torque remain valid. Retained counters and
identification follow the last-known-value exception below.

Raw frame JSON uses the common envelope without measurement fields, plus
`can_id`, synonymous `arbitration_id`, `is_extended_id: true`, `dlc: 8`,
`priority`, and `data` as exactly 16 lowercase hex characters. The full 29-bit
ID retains PDU1 destination bits; the separate PGN is destination-independent.
Null/global addresses 254/255 do not create transmitter entities.

Vendor PGN reports have a separate contract because they do not establish a
complete original CAN identifier. Unknown reports stay raw, not guessed
measurements. See [decoding boundaries](telemetry.md).

## Delivery and freshness

| Data | QoS / retained | Offline and expiry behavior |
| --- | --- | --- |
| Live measurements, faults, raw frames/reports | 0 / no | No live replay; normally 60-second live-sensor expiry |
| Discovery and protocol availability | 1 / yes | Definitions restored; availability withdrawn on disconnect |
| Controller identification | 1 / yes | Last-known text, no expiry or live-availability gate |
| Cumulative distance, hours, fuel, and idle totals | 1 / yes | Last-known `total_increasing` values, no expiry or live-availability gate |
| Protocol last-data timestamps | 1 / yes | Remain visible offline as observation times |

There is no lossless CAN recorder or exactly-once delivery claim. Consumers
must tolerate QoS 1 duplicate delivery. A persistent broker preserves retained
states across broker restarts.

Identification and retained counters expose `value_basis: last_observed` and
`last_observed` timestamps. Unavailable samples remain visible in raw reports
but do not replace valid retained values. Restoring static identity is not a
new observation.

Each protocol becomes online only after valid telemetry. Disconnect, reconnect
initialization, graceful HA shutdown, and unload publish offline immediately.
A watchdog checks every 15 seconds and withdraws availability after 60 seconds
without data, at the next check. Each live sensor expires independently even
if another measurement keeps arriving. J1939 cannot keep J1587 online.

With [J1708 polling](j1708.md#automatic-one-minute-reads) enabled, J1587 protocol
availability and polled live fuel/fault sensors use **180 seconds**. Other live
J1587 and J1939 sensors keep **60 seconds**. Cumulative totals are retained,
not expiring live sensors. An unused protocol remains disconnected.

**Availability is not a safety signal.** HA's shared client cannot provide a
per-device Last Will. After a process crash or blocked event loop, the watchdog
cannot run and retained `online` may be stale. External consumers must enforce
timestamps/timeouts and may also monitor HA's configured birth/will topic.
MQTT `expire_after` is the HA-side live-sensor safeguard.

## Discovery and cleanup

All measurements from one adapter group under one MQTT-owned vehicle device.
The BlueFire integration's native diagnostic device stays separate. Discovery
uses the configured HA prefix and birth topic/payload, not a separate broker
login. Reload BlueFire after changing MQTT discovery/birth options. The
settings lookup is isolated because HA has no public discovery-settings getter.

Definitions are restored across restarts and republished on broker reconnect
and HA's configured birth message. Live readings are not replayed. MAC
corrections preserve topics and unique IDs; readable metadata is additive.

Sensor names put the controller first, such as **Engine: Coolant temperature**
or **Brakes: Supply voltage**. Known roles omit numeric IDs from names; unknown
sources use names such as **Controller 253**. Raw source/MID/PID/SPN/PGN IDs
remain attributes. Conventional roles are not verified controller identities.

Discovery suggests two decimal places for voltage, flow, speed, pressure,
distance, volume, and hours; one for temperature and percentage. Published
precision is unchanged. HA can convert units, and a user's display precision
or customized name takes precedence.

Permanent entry removal sends empty retained discovery payloads, including
definitions known before a restart, and queues retained identity/counter-state
deletion. Prefix changes withdraw the previous prefix's definitions.
Ordinary unload/reload retains discovery but marks telemetry offline.

Ownership and pending cleanup are durable. If MQTT is down, cleanup and offline
availability work are retried on reconnect while HA is running. If HA restarts
with no BlueFire entries, cleanup resumes when BlueFire is next set up.
Deletion requires broker-echo confirmation, not merely a successful publish
call; unconfirmed work remains queued. Do not delete the storage prematurely.

Discovery ownership and pending lifecycle status are separate from live
readings. J1939 diagnostic ownership uses negative PGNs in the existing ledger;
measurement ownership uses positive SPNs. J1587 has a separate `j1587_signals`
ledger field. Valid controller identification has its own local cache; live
readings and broker credentials are not persisted by that ledger.

## Inspect traffic

In MQTT's **Configure → Listen to a topic**, subscribe to
`vehicle/liberty_h3_45/j1939/#` or `vehicle/liberty_h3_45/j1587/#`, replacing the
vehicle ID. Expect retained `offline` before the first valid report, not demo
engine data. Once receiving, inspect `value`, `unit`, raw IDs, and UTC timestamps.
External MQTT clients can consume the same JSON without HA discovery.
