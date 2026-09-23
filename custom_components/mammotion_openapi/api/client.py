"""Async client for the confirmed Mammotion Open API endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import aiohttp

from .auth import MammotionAuth
from .exceptions import (
    MammotionApiError,
    MammotionAuthenticationError,
    MammotionMalformedResponseError,
    MammotionTransportError,
)
from .models import Mower, MowerAction, MowerPlan, parse_mower, parse_plans

API_BASE_URL = "https://api-open.mammotion.com"


class MammotionApiClient:
    """High-level, non-Home-Assistant-specific Mammotion Open API client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        client_secret: str,
    ) -> None:
        self._session = session
        self._auth = MammotionAuth(session, client_id, client_secret)

    async def get_mowers(self) -> tuple[Mower, ...]:
        """Return all mowers available to the authenticated account."""
        data = await self._async_request("GET", "/v1/mowers")
        if not isinstance(data, list):
            raise MammotionMalformedResponseError("Mower list data must be a list")
        return tuple(parse_mower(item) for item in data)

    async def get_mower(self, device_id: str) -> Mower:
        """Return detail for one mower."""
        data = await self._async_request("GET", f"/v1/mower/{_device_path(device_id)}")
        # The official documentation shows a one-item data list for this
        # endpoint; observed responses may also contain the device object.
        if isinstance(data, list):
            if len(data) != 1:
                raise MammotionMalformedResponseError(
                    "Mower detail data must contain exactly one device"
                )
            data = data[0]
        mower = parse_mower(data)
        if mower.id != device_id:
            raise MammotionMalformedResponseError("Mower detail device ID does not match request")
        return mower

    async def get_plans(self, device_id: str) -> tuple[MowerPlan, ...]:
        """Return plan data for one mower."""
        data = await self._async_request("GET", f"/v1/mower/{_device_path(device_id)}/plan")
        return parse_plans(data)

    async def send_action(
        self,
        device_id: str,
        action: MowerAction,
        params: Mapping[str, Any] | None = None,
    ) -> None:
        """Send an action using the payload confirmed for PAUSE and RESUME."""
        if not isinstance(action, MowerAction):
            raise TypeError("action must be a MowerAction")
        if not isinstance(device_id, str) or not device_id:
            raise ValueError("device_id must be a non-empty string")
        payload: dict[str, Any] = {
            "deviceId": device_id,
            "action": action.value,
            "params": {} if params is None else dict(params),
        }
        await self._async_request("POST", "/v1/mower/action", json=payload, require_data=False)

    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        require_data: bool = True,
        retry_auth: bool = True,
    ) -> object:
        token = await self._auth.async_get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{API_BASE_URL}{path}"
        authorization_failed = False
        try:
            async with self._session.request(method, url, headers=headers, json=json) as response:
                if response.status in (401, 403):
                    authorization_failed = True
                elif response.status < 200 or response.status >= 300:
                    raise MammotionTransportError(f"Mammotion API returned HTTP {response.status}")
                else:
                    try:
                        payload = await response.json(content_type=None)
                    except (aiohttp.ClientError, ValueError, TypeError) as err:
                        raise MammotionMalformedResponseError("Mammotion API returned invalid JSON") from err
        except (MammotionAuthenticationError, MammotionTransportError, MammotionMalformedResponseError):
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise MammotionTransportError("Unable to reach Mammotion Open API") from err

        if authorization_failed:
            self._auth.async_invalidate_token()
            if retry_auth:
                return await self._async_request(
                    method, path, json=json, require_data=require_data, retry_auth=False
                )
            raise MammotionAuthenticationError("Mammotion rejected the access token")
        return _unwrap_api_envelope(payload, require_data=require_data)


def _device_path(device_id: str) -> str:
    if not isinstance(device_id, str) or not device_id:
        raise ValueError("device_id must be a non-empty string")
    return quote(device_id, safe="")


def _unwrap_api_envelope(payload: object, *, require_data: bool = True) -> object:
    if not isinstance(payload, Mapping):
        raise MammotionMalformedResponseError("Mammotion API response must be an object")
    code = payload.get("code")
    if isinstance(code, bool) or not isinstance(code, int):
        raise MammotionMalformedResponseError("Mammotion API response code must be an integer")
    if code != 0:
        message = payload.get("msg")
        raise MammotionApiError(code, message if isinstance(message, str) else None)
    if require_data and "data" not in payload:
        raise MammotionMalformedResponseError("Successful Mammotion API response is missing data")
    return payload.get("data")
