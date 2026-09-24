"""Lawn mower entities backed only by the official Mammotion Open API."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api.models import MowerAction
from .const import DOMAIN
from .entity import (
    MammotionCoordinatorEntity,
    async_send_mower_action,
    is_known_rtk_station,
)

PARALLEL_UPDATES = 0

_STATUS_TO_ACTIVITY_MEMBER = {
    "Mowing": "MOWING",
    "Working": "MOWING",
    "Returning": "RETURNING",
    "Abnormal": "ERROR",
}


def _available_activity(member: str) -> LawnMowerActivity | None:
    """Avoid using an activity absent from an older Home Assistant version."""
    return getattr(LawnMowerActivity, member, None)

# Extra entity actions expose every confirmed Open API command, including
# commands not represented by HA's lawn_mower controls on older releases.
_MOWER_SERVICES: tuple[tuple[str, dict, str], ...] = (
    ("cmd_start", {}, "async_cmd_start"),
    (
        "start_task",
        {vol.Required("task_name"): vol.All(str, vol.Length(min=1))},
        "async_start_task",
    ),
    ("pause", {}, "async_pause"),
    ("resume", {}, "async_resume"),
    ("stop", {}, "async_stop"),
    ("return_to_dock", {}, "async_dock"),
    ("cancel_return", {}, "async_cancel_return"),
)


def async_register_mower_services(hass: HomeAssistant) -> None:
    """Register entity actions with the API available in HA 2025.10+."""
    from homeassistant.helpers import service

    register = getattr(service, "async_register_platform_entity_service", None)
    if register is None:
        return
    for service_name, schema, method in _MOWER_SERVICES:
        register(
            hass,
            DOMAIN,
            service_name,
            entity_domain="lawn_mower",
            schema=schema,
            func=method,
        )


def _register_legacy_mower_services() -> None:
    """Keep entity actions usable on HA releases predating the service helper."""
    from homeassistant.helpers import service

    if hasattr(service, "async_register_platform_entity_service"):
        return
    from homeassistant.helpers.entity_platform import async_get_current_platform

    platform = async_get_current_platform()
    for service_name, schema, method in _MOWER_SERVICES:
        platform.async_register_entity_service(service_name, schema, method)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one lawn mower entity for each device not known to be an RTK station."""
    _register_legacy_mower_services()
    coordinator = entry.runtime_data.coordinator
    added: set[str] = set()

    def add_new_mowers() -> None:
        entities = []
        for device_id, snapshot in coordinator.data.items():
            if device_id in added or is_known_rtk_station(snapshot.mower):
                continue
            added.add(device_id)
            entities.append(MammotionLawnMower(coordinator, device_id))
        if entities:
            async_add_entities(entities)

    add_new_mowers()
    entry.async_on_unload(coordinator.async_add_listener(add_new_mowers))


class MammotionLawnMower(MammotionCoordinatorEntity, LawnMowerEntity):
    """A mower with the three controls exposed by HA's lawn_mower platform."""

    _attr_name = None
    _attr_supported_features = (
        LawnMowerEntityFeature.START_MOWING
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.DOCK
    )

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "mower")
        # HA introduced the native STOP feature in 2026.10. Older releases
        # still have the custom stop action registered above.
        self._attr_supported_features |= getattr(LawnMowerEntityFeature, "STOP", 0)

    @property
    def available(self) -> bool:
        """Do not offer commands for offline or detail-unavailable mowers."""
        snapshot = self.snapshot
        return (
            super().available
            and snapshot is not None
            and snapshot.detail_available
            and snapshot.mower.online is not False
            and not is_known_rtk_station(snapshot.mower)
        )

    @property
    def activity(self) -> LawnMowerActivity | None:
        """Map observed statuses without requiring newer HA activity members."""
        snapshot = self.snapshot
        if snapshot is None:
            return None
        status = snapshot.mower.status
        charge_status = snapshot.mower.charge_status
        if status in ("TaskPaused", "Paused"):
            if charge_status in (1, 2):
                return _available_activity("DOCKED")
            if charge_status in (0, None):
                return _available_activity("PAUSED")
            # Unknown charge codes do not establish whether it is docked.
            return None
        if status == "Standby":
            if charge_status in (1, 2):
                return _available_activity("DOCKED")
            if charge_status == 0:
                return _available_activity("IDLE")
            # Unknown or missing charge status does not establish activity.
            return None
        member = _STATUS_TO_ACTIVITY_MEMBER.get(status)
        return _available_activity(member) if member is not None else None

    async def async_start_mowing(self) -> None:
        """Resume a paused task; otherwise request the mower's default start."""
        if self.snapshot and self.snapshot.mower.status in ("TaskPaused", "Paused"):
            await self.async_resume()
        else:
            await self.async_cmd_start()

    async def async_cmd_start(self) -> None:
        """Send CMD_START without inventing a task name."""
        await self._async_send_action(MowerAction.CMD_START)

    async def async_start_task(self, task_name: str) -> None:
        """Start a named task using the documented taskName parameter."""
        if not isinstance(task_name, str) or not task_name.strip():
            raise HomeAssistantError("A non-empty task name is required")
        await self._async_send_action(MowerAction.START, {"taskName": task_name})

    async def async_pause(self) -> None:
        """Pause the current task."""
        await self._async_send_action(MowerAction.PAUSE)

    async def async_resume(self) -> None:
        """Resume a paused task."""
        await self._async_send_action(MowerAction.RESUME)

    async def async_stop(self) -> None:
        """Stop the current task without sending the mower to its dock."""
        await self._async_send_action(MowerAction.STOP)

    async def async_dock(self) -> None:
        """Send the mower back to its dock."""
        await self._async_send_action(MowerAction.RETURN)

    async def async_cancel_return(self) -> None:
        """Cancel the mower's return to its dock."""
        await self._async_send_action(MowerAction.CANCEL_RETURN)

    async def _async_send_action(
        self, action: MowerAction, params: dict[str, str] | None = None
    ) -> None:
        if not self.available:
            raise HomeAssistantError("Mower is unavailable for commands")
        await async_send_mower_action(self.coordinator, self.device_id, action, params)
