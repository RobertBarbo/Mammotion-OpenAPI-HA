"""Minimal Home Assistant interfaces for offline integration unit tests."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from enum import Enum, IntFlag
from typing import Any


def install_home_assistant_stubs() -> None:
    """Expose just the HA interfaces used by this integration to unit tests."""
    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []  # type: ignore[attr-defined]
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    exceptions = types.ModuleType("homeassistant.exceptions")
    const = types.ModuleType("homeassistant.const")
    components = types.ModuleType("homeassistant.components")
    components.__path__ = []  # type: ignore[attr-defined]
    lawn_mower = types.ModuleType("homeassistant.components.lawn_mower")
    sensor = types.ModuleType("homeassistant.components.sensor")
    binary_sensor = types.ModuleType("homeassistant.components.binary_sensor")
    button = types.ModuleType("homeassistant.components.button")
    text = types.ModuleType("homeassistant.components.text")
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []  # type: ignore[attr-defined]
    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    selector = types.ModuleType("homeassistant.helpers.selector")
    entity = types.ModuleType("homeassistant.helpers.entity")
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    service = types.ModuleType("homeassistant.helpers.service")
    redact = types.ModuleType("homeassistant.helpers.redact")

    class ConfigFlow:
        def __init_subclass__(cls, **_kwargs: Any) -> None:
            return None

        def _async_current_entries(self) -> list[Any]:
            return self._entries

        def _get_reauth_entry(self) -> Any:
            return self._reauth_entry

        def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "form", **kwargs}

        def async_abort(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "abort", **kwargs}

        def async_create_entry(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "create_entry", **kwargs}

        def async_update_reload_and_abort(self, entry: Any, **kwargs: Any) -> dict[str, Any]:
            entry.data.update(kwargs["data_updates"])
            return {"type": "abort", "reason": "reauth_successful"}

    class DataUpdateCoordinator:
        def __class_getitem__(cls, _item: Any) -> type:
            return cls

        def __init__(self, _hass: Any, _logger: Any, **kwargs: Any) -> None:
            self.data: Any = None
            self.config_entry = kwargs["config_entry"]
            self.update_interval = kwargs["update_interval"]
            self._listeners: list[Any] = []

        async def async_config_entry_first_refresh(self) -> None:
            self.data = await self._async_update_data()

        async def async_request_refresh(self) -> None:
            self.data = await self._async_update_data()
            for listener in tuple(self._listeners):
                listener()

        def async_add_listener(self, listener: Any) -> Any:
            self._listeners.append(listener)

            def unsubscribe() -> None:
                self._listeners.remove(listener)

            return unsubscribe

    class ConfigEntryAuthFailed(Exception):
        pass

    class HomeAssistantError(Exception):
        pass

    class UpdateFailed(Exception):
        pass

    class Entity:
        def async_write_ha_state(self) -> None:
            return None

    class CoordinatorEntity(Entity):
        def __class_getitem__(cls, _item: Any) -> type:
            return cls

        def __init__(self, coordinator: Any) -> None:
            self.coordinator = coordinator

        @property
        def available(self) -> bool:
            return True

    class LawnMowerActivity(Enum):
        MOWING = "mowing"
        PAUSED = "paused"
        RETURNING = "returning"
        DOCKED = "docked"
        ERROR = "error"

    class LawnMowerEntityFeature(IntFlag):
        START_MOWING = 1
        PAUSE = 2
        DOCK = 4

    class EntityCategory:
        DIAGNOSTIC = "diagnostic"

    class SensorDeviceClass:
        BATTERY = "battery"
        SIGNAL_STRENGTH = "signal_strength"

    class SensorStateClass:
        MEASUREMENT = "measurement"

    class BinarySensorDeviceClass:
        CONNECTIVITY = "connectivity"

    @dataclass(frozen=True, kw_only=True)
    class EntityDescription:
        key: str
        translation_key: str | None = None
        device_class: str | None = None
        native_unit_of_measurement: str | None = None
        state_class: str | None = None
        entity_category: str | None = None
        entity_registry_enabled_default: bool = True

    class TextSelectorType:
        TEXT = "text"
        PASSWORD = "password"

    class TextSelectorConfig:
        def __init__(self, *, type: str) -> None:
            self.type = type

    class TextSelector:
        def __init__(self, config: TextSelectorConfig) -> None:
            self.config = config

        def __call__(self, value: str) -> str:
            return value

    config_entries.ConfigFlow = ConfigFlow  # type: ignore[attr-defined]
    config_entries.ConfigFlowResult = dict  # type: ignore[attr-defined]
    config_entries.ConfigEntry = object  # type: ignore[attr-defined]
    core.HomeAssistant = object  # type: ignore[attr-defined]
    exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed  # type: ignore[attr-defined]
    exceptions.HomeAssistantError = HomeAssistantError  # type: ignore[attr-defined]
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator  # type: ignore[attr-defined]
    update_coordinator.UpdateFailed = UpdateFailed  # type: ignore[attr-defined]
    update_coordinator.CoordinatorEntity = CoordinatorEntity  # type: ignore[attr-defined]
    aiohttp_client.async_get_clientsession = lambda hass: hass.session  # type: ignore[attr-defined]
    device_registry.async_get = lambda hass: hass.registry  # type: ignore[attr-defined]
    selector.TextSelector = TextSelector  # type: ignore[attr-defined]
    selector.TextSelectorConfig = TextSelectorConfig  # type: ignore[attr-defined]
    selector.TextSelectorType = TextSelectorType  # type: ignore[attr-defined]
    entity.DeviceInfo = dict  # type: ignore[attr-defined]
    entity_platform.AddConfigEntryEntitiesCallback = object  # type: ignore[attr-defined]
    class FakeEntityPlatform:
        def __init__(self) -> None:
            self.registered_services: dict[str, tuple[Any, Any]] = {}

        def async_register_entity_service(self, name: str, schema: Any, method: str) -> None:
            self.registered_services[name] = (schema, method)

    entity_platform.current_platform = FakeEntityPlatform()  # type: ignore[attr-defined]
    entity_platform.async_get_current_platform = (  # type: ignore[attr-defined]
        lambda: entity_platform.current_platform
    )
    def register_platform_entity_service(
        hass: Any, _domain: str, name: str, *,
        entity_domain: str, schema: Any, func: str,
    ) -> None:
        hass.registered_services[name] = (entity_domain, schema, func)

    service.async_register_platform_entity_service = register_platform_entity_service  # type: ignore[attr-defined]
    def async_redact_data(data: Any, keys: set[str]) -> Any:
        if isinstance(data, dict):
            return {
                key: "**REDACTED**" if key in keys else async_redact_data(value, keys)
                for key, value in data.items()
            }
        if isinstance(data, list):
            return [async_redact_data(value, keys) for value in data]
        return data

    redact.async_redact_data = async_redact_data  # type: ignore[attr-defined]
    device_registry.DeviceEntry = object  # type: ignore[attr-defined]
    const.EntityCategory = EntityCategory  # type: ignore[attr-defined]
    const.PERCENTAGE = "%"  # type: ignore[attr-defined]
    const.SIGNAL_STRENGTH_DECIBELS_MILLIWATT = "dBm"  # type: ignore[attr-defined]
    lawn_mower.LawnMowerActivity = LawnMowerActivity  # type: ignore[attr-defined]
    lawn_mower.LawnMowerEntityFeature = LawnMowerEntityFeature  # type: ignore[attr-defined]
    lawn_mower.LawnMowerEntity = Entity  # type: ignore[attr-defined]
    sensor.SensorDeviceClass = SensorDeviceClass  # type: ignore[attr-defined]
    sensor.SensorStateClass = SensorStateClass  # type: ignore[attr-defined]
    sensor.SensorEntityDescription = EntityDescription  # type: ignore[attr-defined]
    sensor.SensorEntity = Entity  # type: ignore[attr-defined]
    binary_sensor.BinarySensorDeviceClass = BinarySensorDeviceClass  # type: ignore[attr-defined]
    binary_sensor.BinarySensorEntityDescription = EntityDescription  # type: ignore[attr-defined]
    binary_sensor.BinarySensorEntity = Entity  # type: ignore[attr-defined]
    button.ButtonEntityDescription = EntityDescription  # type: ignore[attr-defined]
    button.ButtonEntity = Entity  # type: ignore[attr-defined]
    text.TextEntity = Entity  # type: ignore[attr-defined]

    homeassistant.config_entries = config_entries  # type: ignore[attr-defined]
    homeassistant.core = core  # type: ignore[attr-defined]
    homeassistant.exceptions = exceptions  # type: ignore[attr-defined]
    homeassistant.const = const  # type: ignore[attr-defined]
    homeassistant.components = components  # type: ignore[attr-defined]
    homeassistant.helpers = helpers  # type: ignore[attr-defined]
    components.lawn_mower = lawn_mower  # type: ignore[attr-defined]
    components.sensor = sensor  # type: ignore[attr-defined]
    components.binary_sensor = binary_sensor  # type: ignore[attr-defined]
    components.button = button  # type: ignore[attr-defined]
    components.text = text  # type: ignore[attr-defined]
    helpers.aiohttp_client = aiohttp_client  # type: ignore[attr-defined]
    helpers.device_registry = device_registry  # type: ignore[attr-defined]
    helpers.update_coordinator = update_coordinator  # type: ignore[attr-defined]
    helpers.selector = selector  # type: ignore[attr-defined]
    helpers.entity = entity  # type: ignore[attr-defined]
    helpers.entity_platform = entity_platform  # type: ignore[attr-defined]
    helpers.service = service  # type: ignore[attr-defined]
    helpers.redact = redact  # type: ignore[attr-defined]

    for module in (
        homeassistant,
        config_entries,
        core,
        exceptions,
        const,
        components,
        lawn_mower,
        sensor,
        binary_sensor,
        button,
        text,
        helpers,
        update_coordinator,
        aiohttp_client,
        device_registry,
        selector,
        entity,
        entity_platform,
        service,
        redact,
    ):
        sys.modules[module.__name__] = module


class FakeEntry:
    """Config entry with unload callback tracking."""

    def __init__(self, client_id: str = "test-client-id") -> None:
        self.entry_id = "test-entry-id"
        self.data = {"client_id": client_id, "client_secret": "test-client-secret"}
        self.runtime_data: Any = None
        self._unload_callbacks: list[Any] = []

    def async_on_unload(self, callback: Any) -> None:
        self._unload_callbacks.append(callback)

    def process_unload_callbacks(self) -> None:
        """Emulate HA processing async_on_unload after integration unload."""
        for callback in self._unload_callbacks:
            callback()
        self._unload_callbacks.clear()


class FakeRegistry:
    """Records device registry writes."""

    def __init__(self) -> None:
        self.devices: dict[str, dict[str, Any]] = {}

    def async_get_or_create(self, **kwargs: Any) -> None:
        mower_id = next(iter(kwargs["identifiers"]))[1]
        self.devices[mower_id] = kwargs


class FakeHass:
    def __init__(self) -> None:
        self.session = object()
        self.registry = FakeRegistry()
        self.config_entries = FakeConfigEntries()
        self.registered_services: dict[str, tuple[str, Any, str]] = {}


class FakeConfigEntries:
    def __init__(self) -> None:
        self.forwarded: list[tuple[str, ...]] = []
        self.unloaded: list[tuple[str, ...]] = []

    async def async_forward_entry_setups(self, _entry: FakeEntry, platforms: tuple[str, ...]) -> None:
        self.forwarded.append(platforms)

    async def async_unload_platforms(self, _entry: FakeEntry, platforms: tuple[str, ...]) -> bool:
        self.unloaded.append(platforms)
        return True
