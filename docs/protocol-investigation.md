# BlueFire protocol investigation

[Home](../README.md) · [Telemetry contracts](telemetry.md) · [Offline replay](development.md#offline-replay)

These notes preserve the evidence behind the provisional modern EZ receiver.
**Static application observations are not a verified adapter specification.**
Internal development can use documented observations and synthetic fixtures;
full public-release claims require real-adapter traces and hardware validation.

The [vendor product page](https://bluefire-llc.com/adapter) identifies a product
family, not a wire protocol. Record model, hardware revision, firmware, and
BLE-versus-Classic transport when available. Classic is outside this integration.

The [Android API repository](https://github.com/asoca/BlueFire-API-for-Android)
contains a demo and compiled Java SDK; its README directs developers to
`support@bluefire-llc.com`. The readable demo does not document GATT framing,
authentication, subscriptions, or telemetry encoding. Older compatibility limits
must not be assumed to apply to current adapters.

## Package provenance

Packages were inspected locally, not executed. No APK/MSIX, DLL, decompiled
source, authentication material, or actual vehicle capture is distributed.

| Package | Identity basis | SHA-256 |
| --- | --- | --- |
| Android 9.7.5 APK | Supplied filename label, not independently verified vendor provenance | `e838af5f52adc3503b81814e562486d8f8f4b14ce56330206870ef04256c395e` |
| Android 11.2.3 APK | Manifest: `com.bluefire_llc.apps`, version name `11.2.3`, code `122` | `bcf59700abbbacd0e0faf10819c87acc83d69cf4dd56a9556417def9d85fd6aa` |
| Windows `Apps_12.5.6.0_x64.msix` | Manifest: `BlueFireLLC.BlueFireApps`, `12.5.6.0`, x64 | `0ab3ccfceee263fb8d8924d11733aa89cbcfe6bc95f9527b1d40067cf9f4e696` |

Manifest identities are not independent signature verification. Managed types
were examined with **ILSpy 9.1.0.7988**. Android 9.7.5's relevant logic is in an
LZ4-compressed `BlueFire` assembly in the Xamarin assembly store, not merely the
Java/Dalvik layer.

Android 11.2.3 stores `Apps.dll` in a version-2 assembly store inside the
`payload` ELF section of `libassemblies.arm64-v8a.blob.so`; the app image is
LZ4-compressed. Windows supplies `Apps.dll` directly. No application code or
installer scripts were run. Extracted assemblies/decompiled material were
removed after comparison and are not dependencies.

## Receive framing and reports

Method names identify evidence without reproducing vendor implementation.

| Area | Android 9.7.5 observation | Evidence |
| --- | --- | --- |
| Receive envelope | Two big-endian length bytes, their XOR, a nonempty message body, and checksum | `CommBase.GetDataLength`, `CheckPackets` |
| Receive checksum | Complement of the body's 8-bit end-around-carry sum; excludes the three header bytes | `CommBase.CalcChecksum` |
| Client direction | Two-byte length with checksum also covering length bytes; original BLE adds a packet selector | `CommData.SendData`, `CommBaseBLE.SendData` |
| Dispatch | 151 PGNData, 154 PIDData, 174 OBDData, 255 heartbeat | `PIDCommands`, `CommData.CheckPid` |
| PGN report | Source byte, big-endian 16-bit PGN, priority, data-page byte, length, variable data | `CommData.AddPGNData`, `Helper.BytesToUInt16` |
| Byte order | Vendor envelope fields big-endian; standard CAN signals little-endian | `Helper.BytesToUInt16`, `CANToInt16`, `ProcessPGN` |
| J1587 split | Pre-3.19: big-endian 16-bit PID; 3.19+: up to three `FF` page extensions and PID byte | `CommData.AddPIDData` |
| Variants | Original BLE separates adapter/client services; EZ is serial-like; Classic is separate | `CommBaseBLE.SetGuids`, `CommBLE.GetServices` |
| Fragments | Serial/Classic preserve trailing messages; original BLE discards the completing notification's tail | `CommBase.CheckPackets` |
| Lifecycle | Version/time, compatibility, authentication, bus availability, filters, and heartbeat are distinct | `StartAuthentication`, `CheckPid`, `FinishAuthentication` |

A PGN report has no explicit full arbitration ID, can contain transport-protocol
data, and leaves PDU1/destination/data-page interpretation needing captures.
The app handles BAM/RTS separately. Preserve metadata without inventing IDs,
padding short data, decoding transport fragments, or associating an interleaved
arbitration-ID response without correlation evidence. The integration therefore
uses a distinct report contract rather than fabricated raw-frame fields.

## GATT services and characteristics

These are candidate UUIDs from static inspection, not hardware certification.

| Variant / role | UUID |
| --- | --- |
| Original adapter service | `b65d50ef-db0a-4f24-9e32-189bf1d5f6d5` |
| Original J1939 notify | `c5a7757d-04e7-410a-aa0f-2614427fb1f6` |
| Original J1708 notify | `b972d4e5-238c-43a3-8dab-c3265268b978` |
| Original client service | `1d7f10c5-a793-43d5-82b2-464a74e795be` |
| Original client packet 1 | `4526e59b-a6e6-40ea-a842-972883e7fb3c` |
| Original client packet 2 | `de106755-294c-4b02-8103-06be37461300` |
| Original client packet 3 | `17e7a79a-9bcc-4f15-9508-c84cc9179101` |
| Modern EZ service | `65333333-a115-11e2-9e9a-0800200ca100` |
| Modern EZ receive | `65333333-a115-11e2-9e9a-0800200ca102` |
| Modern EZ client write | `65333333-a115-11e2-9e9a-0800200ca101` |

The live receiver implements only modern EZ. Compare these with
`bluefire.inspect_adapter`; names and manufacturer ID `FFFF` alone are not
identity checks. Both EZ characteristics can carry incoming notifications and
feed one ordered receive stream. A characteristic named "send" does not make
its callback data client writes.

## Cross-version findings

| Area | Android 11.2.3 / Windows 12.5.6 evidence | Consequence |
| --- | --- | --- |
| Envelope | `GetDataLength`/`CalcChecksum` agree between newer builds, ignoring whitespace, and retain earlier framing | No speculative new receive framing/checksum |
| Reports | `PIDCommands`, `AddPGNData`, `AddPIDData`, `AddOBDData` retain commands/layouts; newer PID handlers omit the old legacy branch | Separate report types; explicitly select firmware format |
| Services | `SetGuids` uses only EZ; `IsValidAdapter` rejects exact name `BlueFire LE` | Do not infer original LE support |
| Notifications | `GetCharacteristicData` accepts receive and send callbacks into one queue | Preserve callback order and direction |
| Stream tails | `CheckPackets` preserves bytes after a complete message | Modern replay uses stream mode |
| Startup | `CheckPid` begins version exchange on heartbeat, branches on 3.x/4.x; authentication 169 added, command 177 becomes `GetBuildDate` | Do not transplant 9.7.5 startup or give control bodies version-independent meanings |
| Recovery | `CheckPacketErrors`/`CheckAnotherPGN` looks for `0F 0F 97` near a PGN candidate | App heuristic, not a proven synchronization marker |
| Empty PGNs | Windows rejects zero length; Android lacks the equivalent explicit check | Preserve opaque data offline; do not manufacture signals |
| Missing values | `Helper.IsHexFF` and many `ProcessPGN` branches skip assignment | Do not copy stale display-value behavior or weaken reserved-value handling |
| Recording | `QueuePacketData`, `RecordData`, `PlayRecording` use one incoming queue hex chunk per `Adapter.txt` line | Local replay can consume it without executing the vendor app |

Agreement strengthens static evidence, not hardware compatibility. The
**264-byte** strict-analysis ceiling is a safety policy informed by
`MaxReceiveLength`, not a measured universal firmware maximum.
Control/arbitration-ID messages remain opaque.

The original comparison added no outgoing commands. The later
[opt-in startup path](j1708.md) implements a bounded subset without credentials,
pairing, or adapter-setting changes.

## Heartbeat-only startup investigation

A user-supplied EZ diagnostic on **2026-10-25** established a working BLE
connection with expected EZ characteristics. Its 20-second capture contained
**38 checksum-valid heartbeats**, no PGN/PID/OBD reports; the live receiver also
counted only heartbeats. This validates heartbeat framing on that adapter, not
authentication, bus availability, or measurement decoding. J1708 presence was
user-confirmed, not inferred from heartbeat bytes.

Targeted Windows 12.5.6 reinspection identified the missing exchanges:

| Stage | Observed behavior | Evidence |
| --- | --- | --- |
| BLE transport | Subscribe to both EZ characteristics; client writes to `ca101` | `StartNotifications`, `GetCharacteristicData`, `WaitForWrittenData` |
| First heartbeat | Command 255 starts version negotiation once per connection | `CommData.CheckPid` |
| Firmware 3.x | Command 0 `GetVersion`, platform/build-date queries, command 9 `AppVersion`, positive compatibility required | `GetAdapterVersion3`, `SendVersions3`, `SendAppVersion3` |
| Firmware 4.x | Different command-9 payload with app major/minor/patch and platform | `SendVersions4`, `SendAppVersion4` |
| Authentication | Commands 130/171 for 3.x, 169 for 4.x; responses gate initialization | `CheckAuthentication`, `CheckPid` |
| Connected setup | Read firmware-specific variables/bus settings, synchronize command 8 `AppIsConnected` | `RetrieveData`, `SendGetVariables3`, `SendGetVariables4` |
| J1708 subscriptions | Command 155 `AddPID` sets MID/PID, on-request mode, retrieval mode, interval; incoming command is 154 | `AddPID`, `AddPIDData`, `PIDCommands` |
| Report flow | Command 153 stops reports during setup and restarts them afterward | `HomeBase.ConnectData`, `DataConnected`, `StartSendingData` |

The receiver at capture time only subscribed and parsed incoming data. Opt-in
startup now implements the exchanges; a standalone passive capture still does
not exercise them. Diagnostic downloads instead observe an existing live session.

### Implementation boundaries

Modern EZ **client framing differs from receive framing**: two big-endian
body-length bytes, body, complemented end-around-carry checksum covering length
and body. No receive-header XOR byte or original-LE selector. Writes use `ca101`,
not the writable receive characteristic.

Unsecured authentication need not prompt for a password. With no configured
username/password or binding, inspected 3.x sends zero-length authentication
data and 4.x sends three zero-length fields. Secured adapters use encrypted
data instead; unsecured fields are not an authentication bypass or proof that
a secured adapter will accept them. Never reset security or fall back on rejection.

Version-bearing device names select the app's 4.x path; unversioned `BlueFire EZ`
takes 3.x. That is an app selection rule, not firmware proof. The integration's
`j1587_extended` setting independently selects incoming PID parsing.

`AddPID` uses a big-endian 16-bit PID even when incoming reports use page
extensions. Monitoring and on-request retrieval differ: the latter can request
vehicle-bus data. Notification status does not replace subscriptions/report flow.
Read ignore/availability state before attributing missing data to a bus or ECU.

Do not replay vendor initialization wholesale: it can change settings to match
its UI. Preserve variables and bus flags; reject compatibility/authentication
errors; use bounded deadlines; rebuild subscriptions on reconnect; never issue
fault-clear, reset, firmware-flash, or arbitrary vehicle-transmit commands.

The vendor guide describes heartbeat checks, but Android 11.2.3's outgoing
command-255 timer is in Classic `CommBaseBT2`, not EZ BLE. Windows 12.5.6 has no
matching outgoing EZ timer. The experimental command-7 probe uses an existing
status query; preventing physical dropouts remains unverified.

## Current hardware evidence and release gate

A later live diagnostic confirms firmware **3.23.0**, accepted compatibility and
unsecured authentication, adapter-variable reads, and an initial **false J1708
availability** response. Vendor behavior does not treat that false response as
a connection failure; passive setup must not be blocked by it.

Full report setup and actual measurements remain unverified. The next hardware
gate is a firmware/security-confirmed bidirectional startup trace through valid
version, compatibility/authentication, and a scoped subscription such as engine
MID 128 / PID 190, followed by actual PIDData. Normal unsecured fields are used;
no vendor code, keys, or captured security payloads are included.

Before a full public release, validate supported variants, framing, signal
values, missing-data behavior, reporting cadence, cancellation/reconnect, and
MQTT freshness against real adapter traces and hardware. Tests currently contain
no real adapter recordings. Internal implementation and synthetic tests need
not wait for release validation, but must keep this boundary explicit.
