"""Availability booleans observed in Mammotion Open API responses."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api.models import Mower
from .entity import MammotionCoordinatorEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MammotionBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor metadata plus an observed-field reader."""

    value_fn: Callable[[Mower], bool | None]


BINARY_SENSORS: tuple[MammotionBinarySensorDescription, ...] = (
    MammotionBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda mower: mower.online,
    ),
    MammotionBinarySensorDescription(
        key="wifi_available",
        translation_key="wifi_available",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda mower: mower.network.wifi_available if mower.network else None,
    ),
    MammotionBinarySensorDescription(
        key="cellular_available",
        translation_key="cellular_available",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda mower: mower.network.cellular_available if mower.network else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add booleans only where the API supplies a value."""
    coordinator = entry.runtime_data.coordinator
    added: set[tuple[str, str]] = set()

    def add_new_binary_sensors() -> None:
        entities = []
        for device_id, snapshot in coordinator.data.items():
            for description in BINARY_SENSORS:
                key = (device_id, description.key)
                if key in added or description.value_fn(snapshot.mower) is None:
                    continue
                added.add(key)
                entities.append(MammotionBinarySensor(coordinator, device_id, description))
        if entities:
            async_add_entities(entities)

    add_new_binary_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_new_binary_sensors))


class MammotionBinarySensor(MammotionCoordinatorEntity, BinarySensorEntity):
    """One boolean field from the latest device data."""

    entity_description: MammotionBinarySensorDescription

    def __init__(
        self, coordinator, device_id: str, description: MammotionBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        snapshot = self.snapshot
        return self.entity_description.value_fn(snapshot.mower) if snapshot else None

    @property
    def available(self) -> bool:
        snapshot = self.snapshot
        if not super().available or snapshot is None or self.is_on is None:
            return False
        if self.entity_description.key == "online":
            return True
        return snapshot.detail_available and snapshot.mower.online is not False
