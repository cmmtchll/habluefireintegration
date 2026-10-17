"""Configure a discovered adapter or prepare one before it is available."""

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from .const import (
    CONF_J1587_EXTENDED,
    CONF_VEHICLE_ID,
    DEFAULT_VEHICLE_ID,
    DOMAIN,
)
from .telemetry import valid_vehicle_id
from .validation import normalize_address


class BlueFireConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create a preparation-only entry without speculative BLE probes."""

    VERSION = 1

    def __init__(self):
        """Keep discovered choices local to this flow."""
        self._devices = {}
        self._defaults = {}

    async def async_step_user(self, user_input=None):
        """Offer nearby-device selection and offline manual entry."""
        return self.async_show_menu(
            step_id="user", menu_options=["discovered", "manual"]
        )

    async def async_step_discovered(self, user_input=None):
        """List connectable devices without claiming verified compatibility."""
        errors = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address in self._devices:
                self._defaults = {
                    CONF_ADDRESS: address,
                    CONF_NAME: self._devices[address],
                }
                return await self.async_step_manual()
            errors[CONF_ADDRESS] = "invalid_selection"

        configured = self._async_current_ids()
        choices = {}
        for info in bluetooth.async_discovered_service_info(
            self.hass, connectable=True
        ):
            try:
                address = normalize_address(info.address)
            except ValueError:
                continue
            if address not in configured:
                name = info.name or "Unnamed BLE device"
                self._devices[address] = name
                choices[address] = f"{name} ({address})"
        if not choices:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="discovered",
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): vol.In(choices),
            }),
            errors=errors,
        )

    async def async_step_manual(self, user_input=None):
        """Validate identity without requiring a powered adapter."""
        errors = {}
        if user_input is not None:
            data, errors = self._validate_input(user_input)
            if not errors:
                await self.async_set_unique_id(data[CONF_ADDRESS])
                self._abort_if_unique_id_configured()
                if any(
                    entry.data[CONF_VEHICLE_ID] == data[CONF_VEHICLE_ID]
                    for entry in self._async_current_entries()
                ):
                    errors[CONF_VEHICLE_ID] = "vehicle_id_in_use"
                else:
                    return self.async_create_entry(
                        title=data[CONF_NAME], data=data
                    )
        return self._show_settings(
            "manual", user_input or self._defaults, errors
        )

    async def async_step_reconfigure(self, user_input=None):
        """Correct the MAC/name while preserving MQTT vehicle identity."""
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            data, errors = self._validate_input({
                **user_input,
                CONF_VEHICLE_ID: entry.data[CONF_VEHICLE_ID],
            })
            if not errors:
                if data[CONF_ADDRESS] != entry.unique_id:
                    await self.async_set_unique_id(data[CONF_ADDRESS])
                    self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=data[CONF_ADDRESS],
                    title=data[CONF_NAME],
                    data_updates=data,
                )
        return self._show_settings(
            "reconfigure", user_input or entry.data, errors
        )

    @staticmethod
    def _validate_input(user_input):
        """Normalize saved configuration and attach field-specific errors."""
        data = {
            key: user_input[key].strip()
            for key in (CONF_NAME, CONF_ADDRESS, CONF_VEHICLE_ID)
        }
        errors = {}
        try:
            data[CONF_ADDRESS] = normalize_address(data[CONF_ADDRESS])
        except ValueError:
            errors[CONF_ADDRESS] = "invalid_address"
        if not data[CONF_NAME]:
            errors[CONF_NAME] = "invalid_name"
        if not valid_vehicle_id(data[CONF_VEHICLE_ID]):
            errors[CONF_VEHICLE_ID] = "invalid_vehicle_id"
        if CONF_J1587_EXTENDED in user_input:
            value = user_input[CONF_J1587_EXTENDED]
            if type(value) is not bool:
                errors[CONF_J1587_EXTENDED] = "invalid_j1587_format"
            else:
                data[CONF_J1587_EXTENDED] = value
        return data, errors

    def _show_settings(self, step_id, defaults, errors):
        """Render schemas with submitted values preserved on errors."""
        schema = {
            vol.Required(
                CONF_NAME, default=defaults.get(CONF_NAME, "BlueFire")
            ): str,
            vol.Required(
                CONF_ADDRESS, default=defaults.get(CONF_ADDRESS, "")
            ): str,
        }
        if step_id == "manual":
            schema[vol.Required(
                CONF_VEHICLE_ID,
                default=defaults.get(CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID),
            )] = str
        if CONF_J1587_EXTENDED in defaults:
            schema[vol.Optional(
                CONF_J1587_EXTENDED,
                default=defaults[CONF_J1587_EXTENDED],
            )] = vol.In({
                "Legacy (before 3.19)": False,
                "Extended (3.19+)": True,
            })
        else:
            schema[vol.Optional(CONF_J1587_EXTENDED)] = vol.In({
                "Legacy (before 3.19)": False,
                "Extended (3.19+)": True,
            })
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(schema),
            errors=errors,
        )
