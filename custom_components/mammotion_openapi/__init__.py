"""Home Assistant bootstrap for Mammotion OpenAPI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .api.client import MammotionApiClient
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, DOMAIN, PLATFORMS

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .coordinator import MammotionDataUpdateCoordinator


@dataclass(slots=True)
class MammotionRuntimeData:
    """Objects owned by one Home Assistant config entry."""

    client: MammotionApiClient
    coordinator: MammotionDataUpdateCoordinator
    # Local, non-persistent input for the START taskName parameter per mower.
    task_names: dict[str, str] = field(default_factory=dict)
    # A selected API plan is separate so a stale choice cannot override text.
    selected_task_names: dict[str, str] = field(default_factory=dict)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register mower actions once, even before a config entry is loaded."""
    from .lawn_mower import async_register_mower_services

    async_register_mower_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one credential set and register its discovered devices."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .coordinator import MammotionDataUpdateCoordinator

    client = MammotionApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
    )
    coordinator = MammotionDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = MammotionRuntimeData(client=client, coordinator=coordinator)
    _register_devices(hass, entry, coordinator)
    entry.async_on_unload(
        coordinator.async_add_listener(lambda: _register_devices(hass, entry, coordinator))
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entity platforms; HA then runs entry unload callbacks."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _register_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: MammotionDataUpdateCoordinator,
) -> None:
    """Register every device currently returned by the mower endpoint."""
    from homeassistant.helpers import device_registry as dr

    registry = dr.async_get(hass)
    for mower_id, snapshot in coordinator.data.items():
        mower = snapshot.mower
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, mower_id)},
            name=mower.nickname or mower.name or f"Mammotion device {mower_id}",
            manufacturer="Mammotion",
            model=mower.model,
            sw_version=mower.version,
        )
