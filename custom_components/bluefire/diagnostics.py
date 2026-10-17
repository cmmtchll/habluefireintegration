"""User-requested unredacted diagnostics including a short raw BLE capture.

The file may contain adapter identity and vehicle data; review it before
sharing.
"""

from dataclasses import asdict
from datetime import datetime, timezone

from .const import (
    CAPTURE_SECONDS,
    DOMAIN,
    STATUS_RECEIVER_ENABLED,
)


async def async_get_config_entry_diagnostics(hass, entry):
    """Dump entry, runtime, MQTT and Bluetooth state, then capture."""
    from homeassistant.components import mqtt
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.loader import async_get_integration

    from .bluetooth import async_capture_report, bluetooth_state
    from .mqtt import mqtt_settings

    runtime = entry.runtime_data
    address = entry.data.get("address")
    integration = await async_get_integration(hass, DOMAIN)
    ledger = hass.data.get(DOMAIN)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "integration_version": str(integration.version),
        "protocol_status": STATUS_RECEIVER_ENABLED,
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "unique_id": entry.unique_id,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "mqtt": {
            "connected": mqtt.is_connected(hass),
            "settings": asdict(mqtt_settings(hass)),
            "ledger": (
                ledger.diagnostics(entry.entry_id)
                if ledger is not None else None
            ),
        },
        "bridge": runtime.bridge.diagnostics(),
        "gatt_services": runtime.services,
        "bluetooth": bluetooth_state(hass, address) if address else None,
        "health_before_capture": runtime.health.as_dict(),
    }
    if not address:
        result["capture"] = {"status": "skipped", "reason": "No address"}
    elif runtime.inspecting:
        result["capture"] = {
            "status": "skipped",
            "reason": "Another inspection or capture is running",
        }
    else:
        runtime.inspecting = True
        try:
            if runtime.receiver is not None:
                await runtime.receiver.async_pause()
            result["capture"] = await async_capture_report(
                hass, address, runtime.health, CAPTURE_SECONDS
            )
        except HomeAssistantError as err:
            result["capture"] = {"status": "failed", "error": str(err)}
        finally:
            if runtime.receiver is not None:
                runtime.receiver.async_resume()
            runtime.inspecting = False
    result["health"] = runtime.health.as_dict()
    return result
