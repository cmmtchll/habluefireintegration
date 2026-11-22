"""Enable or disable this adapter's BLE connection without unloading it."""

import asyncio

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_BLUETOOTH_ENABLED
from .sensor import _device_info

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    """Add the persistent per-adapter connection switch."""
    async_add_entities([BluetoothSwitch(entry)])


class BluetoothSwitch(SwitchEntity):
    """Keep manual connection intent separate from live connectivity."""

    _attr_has_entity_name = True
    _attr_translation_key = "bluetooth_enabled"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False

    def __init__(self, entry):
        self._entry = entry
        self._runtime = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_bluetooth_enabled"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool:
        return self._runtime.bluetooth_enabled

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._runtime.health.add_listener(self.async_write_ha_state)
        )

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set_enabled(False)

    async def _async_set_enabled(self, enabled: bool) -> None:
        runtime = self._runtime
        if runtime.inspecting:
            raise ServiceValidationError(
                "Another BlueFire action is already running"
            )
        if enabled == runtime.bluetooth_enabled:
            return
        runtime.inspecting = True
        try:
            if not enabled:
                try:
                    await runtime.receiver.async_pause()
                except asyncio.CancelledError:
                    runtime.receiver.async_resume()
                    raise
                except HomeAssistantError as err:
                    runtime.receiver.async_resume()
                    runtime.health.error("connection_errors", str(err))
                    raise
            runtime.bluetooth_enabled = enabled
            self.hass.config_entries.async_update_entry(
                self._entry,
                options={
                    **self._entry.options, CONF_BLUETOOTH_ENABLED: enabled,
                },
            )
            if enabled:
                runtime.receiver.async_resume()
            else:
                try:
                    await runtime.bridge.async_disconnected()
                except HomeAssistantError as err:
                    runtime.health.error("mqtt_errors", str(err))
                    raise
        finally:
            runtime.inspecting = False
            runtime.health.notify()
