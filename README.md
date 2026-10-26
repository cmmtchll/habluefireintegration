# BlueFire for Home Assistant

**Your vehicle's telemetry, directly in Home Assistant. No Android gateway.**

Connect a BlueFire EZ Bluetooth Low Energy adapter to Home Assistant and publish
decoded engine, transmission, and diagnostic data through MQTT. Keep readings
separate by controller, discover sensors automatically, and inspect the
connection without a separate bridge service.

```text
Vehicle J1939 / J1708
        |
   BlueFire EZ
        | Bluetooth LE
   Home Assistant
        | MQTT discovery + vehicle data
   Sensors, dashboards, and other MQTT consumers
```

> **Experimental integration, not a verified public release.**
> BLE heartbeat reception and part of the firmware 3.23.0 startup sequence have
> been observed on an adapter. Full report setup, vehicle measurements, and
> supported hardware variants still need validation. Most coverage is synthetic.
> Do not use these readings for safety-critical vehicle control or alarms.

## What you get

| Capability | What it means |
| --- | --- |
| Direct BLE connection | Uses Home Assistant's connectable Bluetooth scanners, including compatible proxies; reconnects automatically |
| Vehicle measurements | Decoders for 37 J1939 SPNs and 39 numeric J1587 PIDs, plus switch, cruise, and gear status |
| Read-only diagnostics | J1939 DM1/DM2 and J1587 PID 194 fault reports with source-separated codes and descriptions |
| Optional J1708 startup | Unsecured EZ initialization, passive subscriptions, five one-minute parameter reads, and manual refresh actions |
| Controller identification | Software, vehicle, and component text where reported; last-known identities and cumulative totals remain visible offline |
| MQTT discovery | Stable entity identities, engineering units, protocol connectivity indicators, and freshness handling |
| Connection visibility | Native diagnostic sensors, connection history, GATT inspection, and live notification capture |

Decoder support is **not** a promise that a particular vehicle supplies every
measurement. Bluetooth Classic, original LE variants, and secured-adapter
authentication are not supported.

## Get started

You need **Home Assistant Core 2026.10 or later**, its configured **MQTT**
integration and broker, and **Bluetooth with a connectable scanner or proxy**.

1. Copy `custom_components/bluefire` into your Home Assistant configuration
   directory, so the manifest is at
   `/config/custom_components/bluefire/manifest.json`. Restart Home Assistant.
2. Open **Settings → Devices & services → Add integration → BlueFire**.
   Select the adapter you recognize from the nearby list, or enter its BLE MAC.
3. Choose a unique vehicle MQTT identifier. Setup can be completed offline;
   the receiver starts when the entry loads.
4. For J1708 on an unsecured EZ adapter, explicitly enable **J1708 startup**
   and select its firmware format. Firmware **3.23.0** uses **Extended (3.19+)**.
   Leave startup disabled for receive-only operation.

**[Full installation and configuration guide →](docs/getting-started.md)**

`receiver_enabled` means the receiver is enabled, not that telemetry is flowing.
The native BlueFire device has **Bluetooth connectivity**, **J1708 telemetry
connectivity**, and **J1939 telemetry connectivity** diagnostic binary sensors.
These distinguish an active BLE link from fresh vehicle data without opening
the separate MQTT device.
Measurement entities appear only after supported reports arrive; MQTT telemetry
availability stays offline until valid data is received.

## Documentation

| Guide | Use it for |
| --- | --- |
| [Installation and configuration](docs/getting-started.md) | Prerequisites, MQTT setup, finding the MAC, reconfiguration, upgrades, and removal |
| [J1708 startup and read actions](docs/j1708.md) | Firmware selection, passive subscriptions, polling, manual reads, and identification |
| [Troubleshooting and diagnostics](docs/diagnostics.md) | Missing data, reconnects, diagnostic sensors, inspection, and safe capture sharing |
| [MQTT reference](docs/mqtt.md) | Topics, payloads, discovery, retention, availability, and cleanup |
| [Telemetry and decoding](docs/telemetry.md) | Protocol boundaries, measurements, fault interpretation, and equipment profiles |
| [Code and measurement catalog](docs/code-reference.md) | Generated tables of IDs, scales, units, mappings, and sources |
| [Protocol investigation](docs/protocol-investigation.md) | BLE UUIDs, package observations, startup evidence, and hardware-validation gaps |
| [Development](docs/development.md) | Local checks, offline replay, architecture, and contribution guidance |
| [Quality-scale assessment](QUALITY_SCALE.md) | Current self-assessment and what the checklist does and does not establish |

## Scope and safety

Development is initially focused on a Prevost H3-45 Liberty Coach Elegant Lady
with a **Detroit Series 60 12.7 L, 500 HP, DDEC IV** engine and an
**Allison HD4000MH R** transmission. This is development context, not automatic
vehicle detection or a compatibility certification.

The integration does not clear faults, program controllers, change adapter
security or bus settings, or upgrade firmware. J1708 startup and read actions
send bounded initialization and data-request commands only when opted in.
Diagnostics are **unredacted** and can contain MAC addresses, VINs, serial
numbers, and vehicle data; review them before sharing.

Found a problem? [Open an issue](https://github.com/cmmtchll/habluefireintegration/issues)
with the integration version, adapter model/firmware, and a reviewed diagnostic
file. See [troubleshooting](docs/diagnostics.md) before collecting a capture.
