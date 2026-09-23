"""Local task-name input used by the named START button."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import MammotionCoordinatorEntity, is_known_rtk_station

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one local task-name input per mower, excluding RTK stations."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    added: set[str] = set()

    def add_new_inputs() -> None:
        entities = []
        for device_id, snapshot in coordinator.data.items():
            if device_id in added or is_known_rtk_station(snapshot.mower):
                continue
            added.add(device_id)
            entities.append(
                MammotionTaskNameText(coordinator, device_id, runtime.task_names)
            )
        if entities:
            async_add_entities(entities)

    add_new_inputs()
    entry.async_on_unload(coordinator.async_add_listener(add_new_inputs))


class MammotionTaskNameText(MammotionCoordinatorEntity, TextEntity):
    """Remember a saved task name locally until the integration reloads."""

    _attr_translation_key = "task_name"
    _attr_native_max = 255

    def __init__(
        self, coordinator, device_id: str, task_names: dict[str, str]
    ) -> None:
        super().__init__(coordinator, device_id, "task_name")
        self._task_names = task_names

    @property
    def native_value(self) -> str:
        """Return local input; no API call is needed to show it."""
        return self._task_names.get(self.device_id, "")

    async def async_set_value(self, value: str) -> None:
        """Store the exact name without sending any mower command."""
        if not isinstance(value, str) or len(value) > self._attr_native_max:
            raise HomeAssistantError("Task name must be text of at most 255 characters")
        if value.strip():
            self._task_names[self.device_id] = value
        else:
            self._task_names.pop(self.device_id, None)
        self.async_write_ha_state()
