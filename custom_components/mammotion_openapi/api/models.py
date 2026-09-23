"""Typed models for fields observed in Mammotion Open API responses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .exceptions import MammotionMalformedResponseError


class MowerAction(str, Enum):
    """Officially confirmed Mammotion mower actions."""

    CMD_START = "CMD_START"
    START = "START"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STOP = "STOP"
    RETURN = "RETURN"
    CANCEL_RETURN = "CANCEL_RETURN"


@dataclass(frozen=True, slots=True)
class MowerNetwork:
    """Observed mower network fields."""

    used_network: str | None = None
    wifi_available: bool | None = None
    wifi_rssi: int | None = None
    cellular_available: bool | None = None
    cellular_rssi: int | None = None


@dataclass(frozen=True, slots=True)
class Mower:
    """Observed mower list/detail fields."""

    id: str
    name: str | None = None
    nickname: str | None = None
    model: str | None = None
    icon: str | None = None
    version: str | None = None
    online: bool | None = None
    status: str | None = None
    battery_level: int | None = None
    charge_status: int | None = None
    network: MowerNetwork | None = None


@dataclass(frozen=True, slots=True)
class MowerPlan:
    """Observed mower plan fields."""

    task_id: str | None = None
    task_name: str | None = None


def parse_mower(value: object) -> Mower:
    """Parse one mower response object."""
    data = _mapping(value, "mower")
    mower_id = _required_string(data, "id", "mower")
    network_value = data.get("network")
    network = None if network_value is None else parse_network(network_value)
    return Mower(
        id=mower_id,
        name=_optional_string(data, "name", "mower"),
        nickname=_optional_string(data, "nickname", "mower"),
        model=_optional_string(data, "model", "mower"),
        icon=_optional_string(data, "icon", "mower"),
        version=_optional_string(data, "version", "mower"),
        online=_optional_online(data),
        status=_optional_string(data, "status", "mower"),
        battery_level=_optional_int(data, "batteryLevel", "mower"),
        charge_status=_optional_int(data, "chargeStatus", "mower"),
        network=network,
    )


def parse_network(value: object) -> MowerNetwork:
    """Parse the observed network object."""
    data = _mapping(value, "network")
    return MowerNetwork(
        used_network=_optional_string(data, "usedNetwork", "network"),
        wifi_available=_optional_bool(data, "wifiAvailable", "network"),
        wifi_rssi=_optional_int(data, "wifiRssi", "network"),
        cellular_available=_optional_bool(data, "cellularAvailable", "network"),
        cellular_rssi=_optional_int(data, "cellularRssi", "network"),
    )


def parse_plans(value: object) -> tuple[MowerPlan, ...]:
    """Parse the observed plan list, including an empty list."""
    if not isinstance(value, list):
        raise MammotionMalformedResponseError("Expected plan data to be a list")
    return tuple(_parse_plan(item) for item in value)


def _parse_plan(value: object) -> MowerPlan:
    data = _mapping(value, "plan")
    return MowerPlan(
        task_id=_optional_string(data, "taskId", "plan"),
        task_name=_optional_string(data, "taskName", "plan"),
    )


def _mapping(value: object, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MammotionMalformedResponseError(f"Expected {context} to be an object")
    return value


def _required_string(data: Mapping[str, Any], field: str, context: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise MammotionMalformedResponseError(f"Expected {context}.{field} to be a non-empty string")
    return value


def _optional_string(data: Mapping[str, Any], field: str, context: str) -> str | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise MammotionMalformedResponseError(f"Expected {context}.{field} to be a string or null")
    return value


def _optional_bool(data: Mapping[str, Any], field: str, context: str) -> bool | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise MammotionMalformedResponseError(f"Expected {context}.{field} to be a boolean or null")
    return value


def _optional_online(data: Mapping[str, Any]) -> bool | None:
    """Normalize observed 0/1 online values; also tolerate JSON booleans."""
    value = data.get("online")
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    raise MammotionMalformedResponseError("Expected mower.online to be 0, 1, boolean, or null")


def _optional_int(data: Mapping[str, Any], field: str, context: str) -> int | None:
    value = data.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise MammotionMalformedResponseError(f"Expected {context}.{field} to be an integer or null")
    return value
