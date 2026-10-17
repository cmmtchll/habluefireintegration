"""Export protocol status and GATT structure, never addresses or telemetry."""

from .const import STATUS_RECEIVER_ENABLED


async def async_get_config_entry_diagnostics(hass, entry):
    """Omit serial numbers, VIN, Bluetooth address, and vehicle labels."""
    return {
        "protocol_status": STATUS_RECEIVER_ENABLED,
        "gatt_services": entry.runtime_data.services,
    }
