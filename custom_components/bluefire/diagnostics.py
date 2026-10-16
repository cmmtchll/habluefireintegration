"""Export protocol status and GATT structure, never addresses or telemetry."""

from .const import STATUS_PROTOCOL_REQUIRED


async def async_get_config_entry_diagnostics(hass, entry):
    """Omit serial numbers, VIN, Bluetooth address, and vehicle labels."""
    return {
        "protocol_status": STATUS_PROTOCOL_REQUIRED,
        "gatt_services": entry.runtime_data.services,
    }
