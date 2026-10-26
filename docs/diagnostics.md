# Troubleshooting and diagnostics

[Home](../README.md) · [Setup](getting-started.md) · [J1708 startup](j1708.md)

> **Diagnostics are unredacted.** Downloads and captures can contain Bluetooth
> MACs, vehicle identifiers, VINs, serial numbers, and location-related data.
> Review them before sharing; do not commit raw captures.

## Start with the symptom

| Symptom | Check |
| --- | --- |
| No nearby devices | Adapter power/range, a connectable HA scanner/proxy, and competing BLE apps; use manual setup only if you know the real adapter MAC |
| Setup waits for MQTT | Configure HA's MQTT integration and broker first; BlueFire retries when HA's MQTT client becomes available |
| `receiver_enabled`, but no measurements | This is an enabled-state indicator, not success; inspect receiver/startup state and protocol last-data timestamps |
| Connected, only heartbeats | Heartbeats prove transport reception, not bus data; check firmware format and whether unsecured J1708 startup is intentionally enabled |
| Startup `ready`, but telemetry offline | `ready` only confirms report setup; the ECU must actually send a valid supported report |
| Initial J1708 availability is false | This is logged but does not block passive setup; it is not itself a disconnect condition |
| Only some sensors appear | Decoder support does not imply ECU broadcast support; use a supported manual J1708 read where appropriate |
| Values disappear or show disconnected | Inspect per-protocol freshness, per-sensor expiry, last-data timestamps, and receiver history; other traffic cannot keep a missing measurement fresh |
| Totals/text remain visible offline | Expected for retained last-known counters and identification; inspect `last_observed` |
| Repeated reconnects | Check connection history, startup deadlines/rejections, receive-stream errors, scanner visibility, and competing connections |
| Entities missing after upgrade | Restart after replacing files; reload the updated entry to republish discovery and add new diagnostic entities |

No response to a read is not proof of an absent sensor, and no fault response is
not a clean bill of health. See [read semantics](j1708.md#responses-and-errors)
and [MQTT freshness](mqtt.md#delivery-and-freshness).

## Download diagnostics

Open **Settings → Devices & services → BlueFire → ⋮ → Download diagnostics**.
The download observes the existing EZ subscriptions for up to **20 seconds**
without pausing the receiver, disconnecting, reauthenticating, or sending
extra BLE commands. Startup, polling, probes, and normal publishing continue.

| Section | What to inspect |
| --- | --- |
| Config entry | Data/options, MAC, vehicle ID, integration version, and protocol status |
| MQTT / bridge | Connection/discovery settings, durable ownership record, online state, frame age, known signals, and topics for both protocols |
| Bluetooth | Scanner/connectable counts, visibility, last advertisement, name, RSSI, TX power, source scanner/proxy, service UUIDs, manufacturer/service data |
| `health_before_capture` / `health` | Receive/error counters, RSSI history, recent errors, and capture summary |
| `startup_before_capture` | Stage, firmware, expected command, initial J1708 availability, subscriptions, session error, and keepalive counters |
| `receiver_before_capture` / `receiver` | Live state, retry delay, notification time, recent events, and connection history |
| Capture and analysis | Notification bytes, framing/parse errors, report tallies, sample decoded records, rates, gaps, and length histogram |

No subscribed session means the raw capture is `skipped`; it does not open a
new connection. If another inspection/capture owns BLE, the file still includes
other state and explains the skip. A capture ends early on session disconnect
(`connection_lost`) rather than combining fragments from different connections.

Notifications include offset time, characteristic UUID/handle, length, and hex
payload. The capture is bounded to **5,000 notifications**, with
`dropped_notifications` reporting overflow.

Analysis compares stream and padded-notification framing per characteristic.
It includes packet counts, errors, decode rate, command/PGN/J1587/OBD tallies,
known-PGN labels, firmware formats that parse, samples, timing, and lengths.
`selected_framing` identifies the mode explaining the data with fewer errors.
This diagnostic comparison does not choose or change the live firmware format.

A capture can start/end mid-packet. Its independent analysis can report boundary
errors without adding them to live receiver health. Observation does not count
traffic twice, publish extra MQTT data, or change telemetry availability.

## Read connection history

Receiver snapshots include the latest **20 connection events** with UTC
timestamps and failure reasons. Connection establishment has a **30-second**
deadline; timeouts are explicit and use normal reconnect backoff.

`connection_history` is an in-memory ring of the last **10 attempts**, including
the current one. Each record contains attempt/start/connected/ready/end times,
disconnect reason, and scheduled retry delay.

At disconnect it freezes startup/keepalive state, last write command/time
**without the write payload**, per-attempt traffic counters, last data and
notification times, Bluetooth advertisement/RSSI/source, queue depth/overflow,
and pending decoder bytes. Context is saved before BLE cleanup, even when a
capture ends during disconnect.

It also retains the last **10 receive notifications**, capped at **512 bytes
each** with truncation flags. Startup/authentication notifications are excluded;
telemetry can still contain vehicle data. History survives automatic reconnects,
but resets on entry unload/reload or HA restart and is not written to disk.

### Stream recovery and liveness

Isolated framing/checksum errors are logged/counted without immediate disconnect.
The live decoder discards corrupt bytes and requires **two adjacent complete
packets with valid length headers and payload checksums** before resuming a
damaged stream. It preserves intact packets across notification boundaries and
buffers at most **528 bytes**.

Ten framing errors within ten seconds **without recovered packets** trigger
reconnect. Recovering checksum-valid packets resets that error budget; all
framing errors remain counted and logged. This avoids restarting a working
session just because its recoverable errors accumulate. **30 seconds without
any checksum-valid packet** still triggers reconnect, even if malformed
notifications continue.
Startup keeps its per-exchange deadlines and accepts only checksum-verified
responses matching the expected command. Explicit authentication/subscription
rejection, queue overflow, and actual BLE loss remain fail-closed.

Checksum-valid J1587 reports are also validated before publication or telemetry
health updates. Invalid MIDs, value widths, or truncated PID 194 entries are
logged and counted as parse errors. Only the bad report is discarded; valid neighbors
continue, and a malformed fault report is never converted into an empty list.

`receive_stream` shows recovery state/count, recent framing errors, silence
deadline, and checksum-valid packet age. `keepalive` records command-7 requests,
responses, timeouts, consecutive misses, and threshold. See the
[liveness policy](j1708.md#adapter-liveness) before interpreting a missed probe.
Offline analysis remains strict; it does not hide corruption through live
resynchronization.

## Inspect the adapter's GATT inventory

Stop other apps using the adapter. In **Developer tools → Actions**, run
`bluefire.inspect_adapter` and select the BlueFire config entry.

This exclusively owns BLE: it pauses/releases the live session, connects,
enumerates services and characteristic UUIDs/properties, disconnects, and resumes
the receiver. It does **not** read characteristic values, subscribe, authenticate,
or send adapter commands. Compare the inventory with the
[candidate UUIDs](protocol-investigation.md#gatt-services-and-characteristics);
a matching name alone does not establish compatibility.

## Take a standalone notification capture

Run `bluefire.capture_notifications` with a **5–60 second** `duration`.
Unlike a diagnostics download, this action pauses the receiver and opens a
separate passive connection, subscribing to every notify/indicate characteristic.
The response adds subscription failures, MTU, connection time, GATT inventory,
and Bluetooth state before/after.

It does not authenticate or send BlueFire commands, so it may see little or no
telemetry. It releases BLE and resumes normal reception afterward. Use a normal
diagnostic download when you need to observe the authenticated live session
without interrupting it.

## Native diagnostic sensors

These belong to the BlueFire integration device, not the MQTT vehicle device.
Counters are in-memory `total_increasing` values and reset on HA restart.

| Entity | Meaning |
| --- | --- |
| Protocol status | `receiver_enabled` indicates the receiver is enabled |
| Bluetooth connectivity | Connected while the live BLE notification subscriptions are active |
| J1708 telemetry connectivity | Fresh valid J1587 reports over J1708 and an active BLE session; not just startup `ready` or heartbeats |
| J1939 telemetry connectivity | Fresh J1939 data and an active BLE session; J1708 traffic cannot keep it connected |
| Last data seen | Last received BLE notification time, not necessarily valid telemetry |
| Last advertisement | Last passive advertisement; attributes show presence and scanner/proxy |
| Signal strength | Latest RSSI in dBm, unknown if HA reports unavailable; min/max/mean/spread attributes |
| Decode success rate | Decoded packets divided by packets plus framing/parse errors |
| BLE notifications / BLE bytes received | Notification/byte totals; byte sensor disabled by default |
| Decoded packets | Valid framed packets, split into heartbeat and PGN/J1587/OBD reports |
| Framing errors / Parse errors | Invalid framing/checksum/padding or malformed report bodies, with recent messages |
| Unrecognized messages | Unknown commands plus PGNs absent from the catalog |
| Connection errors | Failed live connections, inspections, or captures |
| MQTT messages published / MQTT publish errors | Publisher totals; published-count sensor disabled by default |
| Diagnostic captures | Count and last-capture summary |
| Last error | Most recent error class and message |

RSSI and advertisement information come from HA's passive tracking, without
connecting. Other counters update during reception/capture. Native controller
identification sensors are described in the [J1708 guide](j1708.md#controller-identification).
Connectivity binary sensors poll every 15 seconds and read local receive state,
not MQTT retained messages. Protocol freshness is 60 seconds, or 180 seconds
for J1708 with polling enabled. Native connectivity remains independent of
MQTT publish failures. For obsolete MQTT entities, use the
[manual cleanup preview](mqtt.md#remove-old-entities-without-removing-the-adapter).

## Report a problem

Include the integration version, HA version, adapter model/hardware revision,
firmware, BLE-versus-Classic transport, and the symptom. Attach only reviewed
diagnostics or a sanitized trace, preserving direction, characteristic, order,
and session boundaries where relevant. Never share credentials or raw security
payloads. Use the [issue tracker](https://github.com/cmmtchll/habluefireintegration/issues).
