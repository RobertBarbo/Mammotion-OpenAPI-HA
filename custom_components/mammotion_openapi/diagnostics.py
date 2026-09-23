"""Privacy-conscious diagnostics for the Mammotion OpenAPI integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, DOMAIN
from .coordinator import MowerSnapshot
from .entity import is_known_rtk_station

_REDACTED_KEYS = {
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    "access_token",
    "refresh_token",
    "authorization",
    "Authorization",
}


def _device_summary(snapshot: MowerSnapshot) -> dict[str, Any]:
    """Return only observed, non-identifying troubleshooting fields."""
    mower = snapshot.mower
    network = mower.network
    return {
        "kind": "rtk_station" if is_known_rtk_station(mower) else "mower",
        "detail_available": snapshot.detail_available,
        "model": mower.model,
        "version": mower.version,
        "online": mower.online,
        "status": mower.status,
        "battery_level": mower.battery_level,
        "charge_status": mower.charge_status,
        "network": None if network is None else {
            "used_network": network.used_network,
            "wifi_available": network.wifi_available,
            "wifi_rssi": network.wifi_rssi,
            "cellular_available": network.cellular_available,
            "cellular_rssi": network.cellular_rssi,
        },
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return account diagnostics without IDs, names, or token material."""
    coordinator = entry.runtime_data.coordinator
    snapshots = tuple((coordinator.data or {}).values())
    # Allowlist credential keys before redacting; future entry fields, including
    # any token-like values, cannot accidentally enter the export.
    credentials = {
        key: entry.data[key]
        for key in (CONF_CLIENT_ID, CONF_CLIENT_SECRET)
        if key in entry.data
    }
    return {
        "domain": DOMAIN,
        "credentials": async_redact_data(credentials, _REDACTED_KEYS),
        "coordinator": {
            "last_update_success": getattr(coordinator, "last_update_success", None),
            "device_count": len(snapshots),
        },
        "devices": [_device_summary(snapshot) for snapshot in snapshots],
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for one HA device without exporting its identifier."""
    snapshots = entry.runtime_data.coordinator.data or {}
    for domain, device_id in device.identifiers:
        if domain == DOMAIN and (snapshot := snapshots.get(device_id)) is not None:
            return {"domain": DOMAIN, "device": _device_summary(snapshot)}
    return {"domain": DOMAIN, "device_found": False}
