# Development

[Home](../README.md) · [Telemetry](telemetry.md) · [Protocol evidence](protocol-investigation.md) · [Quality scale](../QUALITY_SCALE.md)

The integration is provisional. Synthetic tests establish internal behavior,
not vendor compatibility, a commissioned vehicle installation, or a verified
full Home Assistant runtime.

## Local checks

From the repository root, using **Python 3.12+** for isolated checks:

```powershell
python -m pip install -r .\requirements-dev.txt
python -m unittest discover -s .\tests -v
python -m pycodestyle .\custom_components .\tests .\scripts
python .\scripts\quality_scale_audit.py
```

PEP 8 uses the default **79-character limit**, with no ignored violations.
To format before checking:

```powershell
python -m autopep8 --in-place --recursive .\custom_components .\tests
```

To reproduce CI coverage gates:

```powershell
python -m coverage run --source=custom_components/bluefire -m unittest discover -s .\tests -v
python -m coverage report --include="custom_components/bluefire/config_flow.py" --fail-under=100
python -m coverage report --fail-under=96
```

PR validation also runs the quality-scale audit, pycodestyle, HACS, and hassfest.
The [quality-scale assessment](../QUALITY_SCALE.md) explains the checklist; a
successful audit is not a quality-tier award.

Tests use synthetic complete CAN frames and injected MQTT/BLE/HA boundary mocks;
they do not contact a broker or adapter. Config-flow tests use real Voluptuous
schemas with mocked flow-manager helpers. Development dependencies are pinned
separately and add no integration runtime packages. Running the integration
requires HA's supported Python version, not merely the local test minimum.

## Export and look up codes

The shared dictionary drives the bridge, analyzer, and generated
[code reference](code-reference.md). Edit definitions, not generated tables.
A regression check rejects drift.

```powershell
python .\scripts\catalog_bluefire.py --export
python .\scripts\catalog_bluefire.py --markdown --output .\docs\code-reference.md
python .\scripts\catalog_bluefire.py --namespace spn --code 190
python .\scripts\catalog_bluefire.py --namespace pid --code 91 --fmi 3 --source 128 --profile detroit_ddec_iii_iv
python .\scripts\catalog_bluefire.py --namespace sid --code 1 --fmi 0 --source 128 --profile detroit_ddec_iii_iv
python .\scripts\catalog_bluefire.py --namespace allison_wtec --code 13-12 --profile allison_wtec_iii
```

Exports retain coverage, profile applicability, and per-record provenance.
See [dictionary boundaries](telemetry.md#dictionary-and-equipment-profiles).

## Offline replay

`protocol.py` is an independent receive-only parser without HA, BLE, or MQTT I/O.
Both live reception and offline analysis use its protocol primitives. Offline
analysis is strict; live stream recovery is a separate policy described in
[diagnostics](diagnostics.md#stream-recovery-and-liveness).

For vendor replay, create an ASCII file containing **adapter-to-client
notification values only**, one hex chunk per line. Preserve direction, ordering,
characteristic metadata in the original, and connection/session boundaries.
Do not feed full HCI/btsnoop files, client writes, or unrelated BLE traffic.

```powershell
python .\scripts\analyze_bluefire.py .\capture.hex --transport stream
python .\scripts\analyze_bluefire.py .\capture.hex --transport padded --j1587-format extended
python .\scripts\analyze_bluefire.py .\Adapter.txt --transport stream --j1587-format extended
```

`stream` accepts arbitrary unpadded chunks. `padded` treats each line as a legacy
notification, permits fragmentation, and drops only zero padding after completion.
Select transport from evidence, not the name alone. Select J1587 firmware format
explicitly rather than inferring it by trying parsers.

Newer vendor `Adapter.txt` files already use the hex-line format and preserve
one shared receive queue for both EZ characteristics. Do not reorder them or
split into independent characteristic streams. For other raw captures, establish
grouping before merging/separating; the analyzer cannot infer it.
These recordings lack timestamps and characteristic IDs, so they cannot prove
cadence, provenance, or session boundaries. Recording/export UI availability is
not guaranteed across app builds. Keep originals private: they may include
handshake/security data.

Synthetic vendor packet for **1000 rpm**, not an adapter capture:

```text
00 0f 0f 97 00 f0 04 06 00 08 ff ff 7d 40 1f ff ff ff 88
```

For raw J1708, use one complete checksummed datagram per line instead:

```powershell
python .\scripts\analyze_bluefire.py .\j1708.hex --transport j1708
```

Synthetic J1708 engine-speed datagram for **1000 rpm**:

```text
80 be a0 0f 13
```

`--j1587-format` applies only to vendor stream/padded PIDData, not raw J1708.
Invalid hex, checksums, widths, and diagnostic entries produce line-numbered
errors. Output is local JSONL with explicit report kinds and
`hardware_verified: false`; it never publishes MQTT or marks telemetry online.
Only supported values are decoded; OBD/unsupported values stay raw.

Any parse/file error returns nonzero. Discard earlier output from that run
rather than treating partial results as a wholly valid capture.
Files/output can contain vehicle identity/location data; do not share or commit
them unredacted.

### Strict parser limits

`ReceiveDecoder` supports split headers/payloads, concatenated stream packets,
and explicit padded-notification mode. It rejects invalid XOR/checksum,
inexact inner lengths, and over-limit packets with `ProtocolError`, clearing
pending data. It does not scan arbitrary payload bytes for a new header:
no verified synchronization marker exists, and checksum is not authentication.

Strict analysis allows **264 total bytes / 260 body bytes**; pending storage
never exceeds 264 bytes even for large concatenated input. The ceiling comes
from an observed app constant, not a universal firmware guarantee. Nonzero
legacy padding, coalesced legacy packets, and larger formats need investigation.
Use one decoder per framed stream/session, `reset()` on disconnect, and
`finish()` at capture end to detect truncation.

Regressions cover every two-chunk split, byte-at-a-time input, deterministic
random fragmentation/coalescing, length boundaries, checksum carry/bit
corruption, truncation/reset, padding ambiguity, inner-length mismatches,
explicit firmware formats, unknown/control messages, and frame/report separation.
Other cases cover modern stream tails, header-like bytes inside opaque data,
interleaved controls, recording whitespace, incomplete signals, and
valid-to-invalid MQTT values without borrowing stale or other-source readings.

## Architecture and related projects

Keep BLE callbacks, reconnect timers, and MQTT publication asynchronous and
HA-managed. Avoid blocking I/O or sleep loops in callbacks, and cancel tasks/
subscriptions on unload. Decoding and publishing stay transport-independent.
No cron scheduler or separate container is required for timing.

An **app** (formerly add-on) or independent service would be a different
architecture: appropriate for surviving HA restarts, an independent MQTT client
and Last Will, incompatible native libraries, process isolation, or HA-independent
logging/consumers. Supervisor apps target HA OS; standalone containers serve
other hosts. Such a bridge needs its own Bluetooth/proxy access and cannot assume
HA APIs. Avoid two receivers competing for one adapter. Packaging does not solve
unverified protocol assumptions.

[HAVRV](https://github.com/cmmtchll/HAVRV) is the architectural reference for
config-entry setup, grouping, and diagnostics. It organizes existing HA entities,
not Bluetooth transport. Once reception is validated, discovered MQTT sensors can
map into its chassis/power systems. There is no runtime dependency or duplication
of HAVRV profiles/dashboards.

References:
[MQTT discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery),
[MQTT sensor expiry](https://www.home-assistant.io/integrations/sensor.mqtt/),
[Bluetooth APIs](https://developers.home-assistant.io/docs/core/bluetooth/api/),
and [HA architecture](https://developers.home-assistant.io/docs/architecture_index/).
