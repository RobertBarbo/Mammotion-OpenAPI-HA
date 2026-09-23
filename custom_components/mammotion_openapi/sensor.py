"""Sensors for observed Mammotion Open API mower detail fields."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api.models import Mower
from .const import DOMAIN
from .entity import MammotionCoordinatorEntity
from .read_only_coordinator import MammotionReadOnlyCoordinator, ReadOnlySnapshot

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MammotionSensorDescription(SensorEntityDescription):
    """Sensor metadata plus an observed-field reader."""

    value_fn: Callable[[Mower], int | str | None]


SENSORS: tuple[MammotionSensorDescription, ...] = (
    MammotionSensorDescription(
        key="battery_level",
        translation_key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda mower: mower.battery_level,
    ),
    MammotionSensorDescription(
        key="status",
        translation_key="status",
        value_fn=lambda mower: mower.status,
    ),
    MammotionSensorDescription(
        key="charge_status",
        translation_key="charge_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda mower: mower.charge_status,
    ),
    MammotionSensorDescription(
        key="used_network",
        translation_key="used_network",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda mower: _network_name(mower.network.used_network) if mower.network else None,
    ),
    MammotionSensorDescription(
        key="wifi_rssi",
        translation_key="wifi_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda mower: mower.network.wifi_rssi if mower.network else None,
    ),
    MammotionSensorDescription(
        key="cellular_rssi",
        translation_key="cellular_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda mower: mower.network.cellular_rssi if mower.network else None,
    ),
)


def _network_name(code: str | None) -> str | None:
    """Translate only codes documented by Mammotion; leave others visible."""
    return {"1": "Wi-Fi", "2": "Cellular"}.get(code, code)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add sensors only for fields actually returned by each device."""
    coordinator = entry.runtime_data.coordinator
    added: set[tuple[str, str]] = set()

    def add_new_sensors() -> None:
        entities = []
        for device_id, snapshot in coordinator.data.items():
            update_key = (device_id, "last_detail_update")
            if update_key not in added:
                added.add(update_key)
                entities.append(MammotionLastDetailUpdateSensor(coordinator, device_id))
            for description in SENSORS:
                key = (device_id, description.key)
                if key in added or description.value_fn(snapshot.mower) is None:
                    continue
                added.add(key)
                entities.append(MammotionSensor(coordinator, device_id, description))
        if entities:
            async_add_entities(entities)

    add_new_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_new_sensors))

    read_only_coordinator = entry.runtime_data.read_only_coordinator
    read_added: set[tuple[str, str]] = set()

    def add_read_only_sensors() -> None:
        entities = []
        for device_id in read_only_coordinator.data:
            for description in READ_ONLY_SENSORS:
                key = (device_id, description.key)
                if key in read_added:
                    continue
                read_added.add(key)
                entities.append(
                    MammotionReadOnlySensor(read_only_coordinator, device_id, description)
                )
        if entities:
            async_add_entities(entities)

    add_read_only_sensors()
    entry.async_on_unload(read_only_coordinator.async_add_listener(add_read_only_sensors))


class MammotionSensor(MammotionCoordinatorEntity, SensorEntity):
    """One raw field from the latest confirmed device detail."""

    entity_description: MammotionSensorDescription

    def __init__(
        self, coordinator, device_id: str, description: MammotionSensorDescription
    ) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | str | None:
        snapshot = self.snapshot
        return self.entity_description.value_fn(snapshot.mower) if snapshot else None

    @property
    def available(self) -> bool:
        snapshot = self.snapshot
        return (
            super().available
            and snapshot is not None
            and snapshot.detail_available
            and snapshot.mower.online is not False
            and self.native_value is not None
        )


class MammotionLastDetailUpdateSensor(MammotionCoordinatorEntity, SensorEntity):
    """Timestamp of the latest successful detail fetch for this device."""

    _attr_translation_key = "last_detail_update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "last_detail_update")

    @property
    def native_value(self) -> datetime | None:
        snapshot = self.snapshot
        return snapshot.last_detail_update if snapshot else None

    @property
    def available(self) -> bool:
        # A failed detail request must not erase the last successful time.
        return self.snapshot is not None and self.native_value is not None


@dataclass(frozen=True, kw_only=True)
class MammotionReadOnlySensorDescription(SensorEntityDescription):
    value_fn: Callable[[ReadOnlySnapshot], int | float | datetime | None]


READ_ONLY_SENSORS: tuple[MammotionReadOnlySensorDescription, ...] = (
    MammotionReadOnlySensorDescription(
        key="work_count", translation_key="work_count",
        value_fn=lambda data: data.report_summary.work_count if data.report_summary else None,
    ),
    MammotionReadOnlySensorDescription(
        key="total_work_area", translation_key="total_work_area",
        native_unit_of_measurement="m²", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.report_summary.total_work_area if data.report_summary else None,
    ),
    MammotionReadOnlySensorDescription(
        key="estimated_time_saved", translation_key="estimated_time_saved",
        native_unit_of_measurement="min", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.report_summary.save_time if data.report_summary else None,
    ),
    MammotionReadOnlySensorDescription(
        key="estimated_carbon_reduction", translation_key="estimated_carbon_reduction",
        native_unit_of_measurement="g", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.report_summary.carbon_reduction if data.report_summary else None,
    ),
    MammotionReadOnlySensorDescription(
        key="knife_height_code", translation_key="knife_height_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.work_parameters.knife_height if data.work_parameters else None,
    ),
    MammotionReadOnlySensorDescription(
        key="work_speed_code", translation_key="work_speed_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.work_parameters.speed if data.work_parameters else None,
    ),
    MammotionReadOnlySensorDescription(
        key="recorded_error_count", translation_key="recorded_error_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.error_codes.total if data.error_codes else None,
    ),
    MammotionReadOnlySensorDescription(
        key="first_returned_report_energy", translation_key="first_returned_report_energy",
        native_unit_of_measurement="Wh", entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.report_detail.energy_consume if data.report_detail else None,
    ),
    MammotionReadOnlySensorDescription(
        key="last_read_only_update", translation_key="last_read_only_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.last_successful_update,
    ),
)


class MammotionReadOnlySensor(CoordinatorEntity[MammotionReadOnlyCoordinator], SensorEntity):
    """Optional documented data, never used to decide mower availability."""

    _attr_has_entity_name = True
    entity_description: MammotionReadOnlySensorDescription

    def __init__(
        self, coordinator: MammotionReadOnlyCoordinator, device_id: str,
        description: MammotionReadOnlySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.device_id = device_id
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device_id)})

    @property
    def native_value(self) -> int | float | datetime | None:
        data = self.coordinator.data.get(self.device_id)
        return self.entity_description.value_fn(data) if data else None

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None
