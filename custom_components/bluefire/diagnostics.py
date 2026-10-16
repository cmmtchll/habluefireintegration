"""Export protocol status and GATT structure, never addresses or telemetry."""

from .const import STATUS_PROTOCOL_REQUIRED


async def async_get_config_entry_diagnostics(hass, entry):
    """Avoid serial numbers, VIN, Bluetooth address, and user vehicle labels."""
    return {
        "protocol_status": STATUS_PROTOCOL_REQUIRED,
        "gatt_services": entry.runtime_data.services,
    }
