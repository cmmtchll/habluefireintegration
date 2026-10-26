# Installation and configuration

[Home](../README.md) · [J1708 startup](j1708.md) · [Troubleshooting](diagnostics.md)

BlueFire is an experimental custom integration. Setup does not prove adapter
compatibility, and full vehicle telemetry remains hardware-unverified. See the
[protocol evidence](protocol-investigation.md) for the current validation boundary.

## Prerequisites

| Requirement | Details |
| --- | --- |
| Home Assistant | Core 2026.10 or later |
| MQTT | A broker and Home Assistant's MQTT integration configured for it |
| Bluetooth | Home Assistant's Bluetooth integration with a connectable BLE scanner, including a compatible proxy |
| Adapter | A BlueFire EZ BLE adapter; secured adapters, Bluetooth Classic, and original LE variants are unsupported |
| Vehicle connection | Verify the actual diagnostic connector, bus wiring, ECM, and J1939/J1708 availability |

No Android gateway, separate BlueFire service, or YAML sensor configuration is
required. Installing BlueFire does not install an MQTT broker.

## 1. Prepare MQTT and Bluetooth

Configure **Settings → Devices & services → MQTT** with your broker. The
Mosquitto broker app on HA OS is one option. Configure authentication and TLS
there, not in BlueFire; do not expose an unauthenticated broker to the internet.

Leave MQTT discovery enabled for automatic vehicle entities. BlueFire uses HA's
shared MQTT client, discovery prefix, and configured birth topic/payload,
including a disabled birth message. It stores no broker credentials and opens
no second MQTT connection. Reload BlueFire after changing these MQTT options.

Check that Home Assistant can use a **connectable** Bluetooth scanner or proxy.
Power the adapter and stop competing applications that might hold its connection.

## 2. Install the integration

Copy the repository's `custom_components/bluefire` directory into your Home
Assistant configuration directory:

```text
/config/
  custom_components/
    bluefire/
      manifest.json
      ...
```

On HA OS the manifest must be at
`/config/custom_components/bluefire/manifest.json`, **not**
`/config/custom_components/habluefireintegration/custom_components/...`.

Restart Home Assistant after installing or upgrading the files.

## 3. Add BlueFire

Open **Settings → Devices & services → Add integration → BlueFire**.

Choose **Choose a nearby Bluetooth device** or **Enter a MAC address manually**.
The nearby list contains unconfigured, connectable BLE devices, not verified
BlueFire matches. Select only the adapter you recognize, then confirm its name
and address. There are no automatic compatible-device discovery matchers yet.

| Setting | Meaning |
| --- | --- |
| Adapter name | A non-blank display name |
| Bluetooth MAC address | The BlueFire peripheral's address, not the host, phone, Wi-Fi adapter, proxy, or VIN |
| Vehicle MQTT identifier | A unique topic identity: 1–64 lowercase letters, digits, underscores, or hyphens, starting with a letter or digit |
| J1587 adapter firmware format | Select the actual adapter firmware format; blank means vendor J1587 PIDData is ignored |
| Enable J1708 startup (unsecured EZ adapters) | Explicitly opts into initialization, passive subscriptions, and bounded active reads; disabled by default |
| Confirmed engine equipment | Select Series 60 / DDEC IV only when official equipment labels or documentation establish it |

`liberty_h3_45` is the default MQTT identifier, not a vehicle-detection rule.
Duplicate MAC addresses and vehicle identifiers are rejected.

Setup itself does not connect and can be completed while the adapter is offline.
When the entry loads, the receiver connects with bounded reconnect backoff.
Expect diagnostic status `receiver_enabled`; it is not a connection or
measurement-success indicator. MQTT availability remains offline until valid
telemetry arrives. A Bluetooth connection or heartbeat alone is insufficient.

For an unsecured J1708 EZ adapter, follow the
[startup guide](j1708.md#enable-startup). Selecting a firmware format alone
does not enable adapter writes.

## Find the adapter's MAC

Use the nearby list or the advertisement monitor in Home Assistant's Bluetooth
integration to match the powered adapter's name and address. A name alone is
not proof of identity.

Manual entry accepts `AA:BB:CC:DD:EE:01`, `AA-BB-CC-DD-EE-01`, or
`AABBCCDDEE01`, ignoring case and surrounding spaces. It stores the normalized
colon-separated form. The example is not a usable placeholder: enter your real
adapter's address. All-zero, broadcast, partial, and mixed-separator addresses
are rejected.

If you cannot identify it, wait rather than entering a random MAC. If the nearby
list is empty, use manual setup only when you know the address, and check scanner
connectability, power, range, and competing BLE apps.

## Find your entities

BlueFire creates two distinct device surfaces:

| Device | Where | Contents |
| --- | --- | --- |
| BlueFire integration device | BlueFire | Native connection/receive-health diagnostics and reported controller-identification text |
| MQTT-owned vehicle device | MQTT | Discovered measurements, faults, controller identification, connectivity, and last-data timestamps |

Do not manually duplicate these with MQTT YAML sensors or expect Home Assistant
to merge devices across config entries.

Sensors appear only for supported data actually reported by a controller.
Names put the controller first, for example **Engine: Coolant temperature**.
Unknown sources remain distinguishable as **Controller 253**, not guessed ECU
types. Address-derived roles are conventional hints; raw IDs remain attributes.

The two MQTT telemetry-connectivity binary sensors are created before
measurements arrive. An unused protocol stays disconnected. Static identities
and cumulative counters may remain visible as last-known information offline;
they do not establish current connectivity. See [MQTT semantics](mqtt.md).

## Reconfigure and upgrade

Choose **Reconfigure** from the BlueFire entry's menu in **Settings →
Devices & services**. You can correct the MAC/name, select the firmware format,
toggle J1708 startup, or choose the confirmed engine equipment. Saving reloads
the entry.

MAC/name corrections preserve diagnostic identities and the MQTT vehicle
identifier, including migration of earlier MAC-based diagnostic IDs. The vehicle
identifier cannot be changed through reconfiguration; remove and recreate the
entry if you intentionally need a different MQTT identity.

After upgrading files, restart Home Assistant. Reloading the updated integration
republishes discovery names/precision and creates newly supported diagnostic
entities without changing existing unique IDs or history. User-customized names
and display precision remain under Home Assistant's control.

## Remove the integration

Delete the entry from **Settings → Devices & services → BlueFire**.
Permanent removal clears owned retained discovery definitions and queues deletion
of retained identity/counter state. Ordinary unload/reload keeps discovery and
marks live telemetry offline.

If the broker is unavailable, cleanup is recorded in HA storage and retried on
broker reconnect while HA is running. If HA restarts with no BlueFire entries,
pending cleanup resumes the next time BlueFire is set up. **Do not delete that
storage before cleanup completes.** Unconfirmed deletions remain queued until
broker-echo confirmation. See [cleanup details](mqtt.md#discovery-and-cleanup).
