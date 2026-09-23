"""Per-mower buttons for confirmed Mammotion Open API commands."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api.models import MowerAction
from .entity import (
    MammotionCoordinatorEntity,
    async_send_mower_action,
    is_known_rtk_station,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MammotionButtonDescription(ButtonEntityDescription):
    """Button metadata and the exact official action to send."""

    action: MowerAction


BUTTONS: tuple[MammotionButtonDescription, ...] = tuple(
    MammotionButtonDescription(
        key=action.value.lower(), translation_key=action.value.lower(), action=action
    )
    for action in MowerAction
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add all command buttons for mowers, never for an RTK station."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    added: set[str] = set()

    def add_new_buttons() -> None:
        entities = []
        for device_id, snapshot in coordinator.data.items():
            if device_id in added:
                continue
            added.add(device_id)
            entities.append(
                MammotionRefreshButton(coordinator, runtime.read_only_coordinator, device_id)
            )
            if is_known_rtk_station(snapshot.mower):
                continue
            entities.extend(
                MammotionActionButton(
                    coordinator, device_id, description,
                    runtime.task_names, runtime.selected_task_names,
                )
                for description in BUTTONS
            )
        if entities:
            async_add_entities(entities)

    add_new_buttons()
    entry.async_on_unload(coordinator.async_add_listener(add_new_buttons))


class MammotionActionButton(MammotionCoordinatorEntity, ButtonEntity):
    """Send one action for one mower when pressed."""

    entity_description: MammotionButtonDescription

    def __init__(
        self, coordinator, device_id: str,
        description: MammotionButtonDescription, task_names: dict[str, str],
        selected_task_names: dict[str, str],
    ) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description
        self._task_names = task_names
        self._selected_task_names = selected_task_names

    @property
    def available(self) -> bool:
        """Do not offer commands to offline or detail-unavailable devices."""
        snapshot = self.snapshot
        return (
            super().available
            and snapshot is not None
            and snapshot.detail_available
            and snapshot.mower.online is not False
            and not is_known_rtk_station(snapshot.mower)
        )

    async def async_press(self) -> None:
        """Send the button's confirmed action, using taskName only for START."""
        if not self.available:
            raise HomeAssistantError("Mower is unavailable for commands")
        params = None
        if self.entity_description.action is MowerAction.START:
            snapshot = self.snapshot
            available_names = {
                plan.task_name for plan in snapshot.plans if plan.task_name
            } if snapshot else set()
            selected = self._selected_task_names.get(self.device_id)
            task_name = (
                selected if selected in available_names
                else self._task_names.get(self.device_id)
            )
            if not task_name or not task_name.strip():
                raise HomeAssistantError("Select or enter a saved task name before starting it")
            params = {"taskName": task_name}
        await async_send_mower_action(
            self.coordinator, self.device_id, self.entity_description.action, params
        )


class MammotionRefreshButton(MammotionCoordinatorEntity, ButtonEntity):
    """Manually request a new official API poll; never send a mower action."""

    _attr_translation_key = "refresh_data"

    def __init__(self, coordinator, read_only_coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "refresh_data")
        self.read_only_coordinator = read_only_coordinator

    @property
    def available(self) -> bool:
        """Keep refresh possible even when the last detail request failed."""
        return self.snapshot is not None

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
        if self.snapshot and not is_known_rtk_station(self.snapshot.mower):
            await self.read_only_coordinator.async_request_refresh()
