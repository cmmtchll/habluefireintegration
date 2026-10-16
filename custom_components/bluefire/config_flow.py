"""Configure an adapter before it is physically available."""

import re

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from .const import CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID, DOMAIN
from .telemetry import valid_vehicle_id


class BlueFireConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create a preparation-only entry; do not probe unverified BLE services."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            vehicle_id = user_input[CONF_VEHICLE_ID].strip()
            if not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", address):
                errors[CONF_ADDRESS] = "invalid_address"
            if not valid_vehicle_id(vehicle_id):
                errors[CONF_VEHICLE_ID] = "invalid_vehicle_id"
            if not errors:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                if any(
                    entry.data[CONF_VEHICLE_ID] == vehicle_id
                    for entry in self._async_current_entries()
                ):
                    errors[CONF_VEHICLE_ID] = "vehicle_id_in_use"
                else:
                    return self.async_create_entry(
                        title=user_input[CONF_NAME],
                        data={**user_input, CONF_ADDRESS: address, CONF_VEHICLE_ID: vehicle_id},
                    )
        defaults = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "BlueFire")): str,
                vol.Required(CONF_ADDRESS, default=defaults.get(CONF_ADDRESS, "")): str,
                vol.Required(
                    CONF_VEHICLE_ID,
                    default=defaults.get(CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID),
                ): str,
            }),
            errors=errors,
        )
