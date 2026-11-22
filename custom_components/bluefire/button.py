"""Expose fixed BlueFire actions directly on the adapter device."""

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, J1708_READ_ACTIONS
from .sensor import _device_info

PARALLEL_UPDATES = 0
BUTTON_ACTIONS = (
    *J1708_READ_ACTIONS,
    "inspect_adapter",
    "capture_notifications",
    "reconnect_bluetooth",
    "cleanup_preview",
    "cleanup_mqtt",
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Add one button for each action with fixed device-local arguments."""
    async_add_entities([
        BlueFireActionButton(entry, action) for action in BUTTON_ACTIONS
    ])


class BlueFireActionButton(ButtonEntity):
    """Reuse service validation, exclusivity and error reporting."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, entry, action):
        self._entry = entry
        self._action = action
        self._cleanup = action in ("cleanup_preview", "cleanup_mqtt")
        self._result = None
        self._attr_translation_key = action
        self._attr_unique_id = f"{entry.entry_id}_{action}"
        self._attr_device_info = _device_info(entry)

    @property
    def available(self) -> bool:
        return self._cleanup or self._entry.runtime_data.bluetooth_enabled

    @property
    def extra_state_attributes(self):
        return {"result": self._result} if self._cleanup else None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._entry.runtime_data.health.add_listener(
                self.async_write_ha_state
            )
        )

    async def async_press(self) -> None:
        data = {"entry_id": self._entry.entry_id}
        service = self._action
        if self._cleanup:
            service = "cleanup_mqtt"
            data["dry_run"] = self._action == "cleanup_preview"
            self._result = None
            self.async_write_ha_state()
        result = await self.hass.services.async_call(
            DOMAIN, service, data, blocking=True, return_response=True,
        )
        if self._cleanup:
            self._result = result
            self.async_write_ha_state()
