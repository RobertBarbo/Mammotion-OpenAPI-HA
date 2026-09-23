"""Local selection of task names returned by the official plan endpoint."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    """Create selectors only when a mower returns named saved plans."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    added: set[str] = set()

    def add_new_selects() -> None:
        entities = []
        for device_id, snapshot in coordinator.data.items():
            if device_id in added or is_known_rtk_station(snapshot.mower):
                continue
            if not any(plan.task_name and plan.task_name.strip() for plan in snapshot.plans):
                continue
            added.add(device_id)
            entities.append(
                MammotionTaskSelect(coordinator, device_id, runtime.selected_task_names)
            )
        if entities:
            async_add_entities(entities)

    add_new_selects()
    entry.async_on_unload(coordinator.async_add_listener(add_new_selects))


class MammotionTaskSelect(MammotionCoordinatorEntity, SelectEntity):
    """Select a saved task locally; the Start button performs the command."""

    _attr_translation_key = "saved_task"

    def __init__(
        self, coordinator, device_id: str, selected_task_names: dict[str, str]
    ) -> None:
        super().__init__(coordinator, device_id, "saved_task")
        self._selected_task_names = selected_task_names

    @property
    def options(self) -> list[str]:
        snapshot = self.snapshot
        if snapshot is None:
            return []
        return list(dict.fromkeys(
            plan.task_name for plan in snapshot.plans
            if plan.task_name and plan.task_name.strip()
        ))

    @property
    def current_option(self) -> str | None:
        selection = self._selected_task_names.get(self.device_id)
        return selection if selection in self.options else None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise HomeAssistantError("Selected task is not available")
        self._selected_task_names[self.device_id] = option
        self.async_write_ha_state()
