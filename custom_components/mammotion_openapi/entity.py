"""Shared Home Assistant entity behavior for Mammotion devices."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api.exceptions import MammotionError
from .api.models import Mower, MowerAction
from .const import DOMAIN, RTK_STATION_MODEL
from .coordinator import MammotionDataUpdateCoordinator, MowerSnapshot


def is_known_rtk_station(mower: Mower) -> bool:
    """Recognize the RTK model observed in the account's device list.

    No general Mammotion device-type field is documented. Keep this narrow:
    the RTK remains a device and may have sensors, but has no mower controls.
    """
    return mower.model == RTK_STATION_MODEL


class MammotionCoordinatorEntity(CoordinatorEntity[MammotionDataUpdateCoordinator]):
    """Bind one coordinator record to one HA device and stable entity ID."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: MammotionDataUpdateCoordinator, device_id: str, key: str
    ) -> None:
        super().__init__(coordinator)
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device_id)})

    @property
    def snapshot(self) -> MowerSnapshot | None:
        """Return this device's current coordinator data, if listed."""
        return self.coordinator.data.get(self.device_id)

    @property
    def available(self) -> bool:
        """Entities disappear from service when account polling fails."""
        return super().available and self.snapshot is not None


async def async_send_mower_action(
    coordinator: MammotionDataUpdateCoordinator,
    device_id: str,
    action: MowerAction,
    params: Mapping[str, Any] | None = None,
) -> None:
    """Send a checked command and refresh state without exposing API errors."""
    try:
        await coordinator.client.send_action(device_id, action, params)
    except MammotionError:
        # Server error text is untrusted and could contain sensitive data.
        raise HomeAssistantError("Mammotion rejected the mower command") from None
    await coordinator.async_request_refresh()
