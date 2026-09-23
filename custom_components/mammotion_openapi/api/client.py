"""Async client for the published Mammotion Open API endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import aiohttp

from .auth import MammotionAuth
from .extended_models import (
    DeviceErrorCodePage,
    WorkParameters,
    WorkReportDetail,
    WorkReportPage,
    WorkReportSummary,
    parse_error_code_page,
    parse_work_parameters,
    parse_work_report_detail,
    parse_work_report_page,
    parse_work_report_summary,
)
from .exceptions import (
    MammotionApiError,
    MammotionAuthenticationError,
    MammotionMalformedResponseError,
    MammotionTransportError,
)
from .models import Mower, MowerAction, MowerPlan, parse_mower, parse_plans

API_BASE_URL = "https://api-open.mammotion.com"

# Existing endpoints have been observed returning code 0. The additional
# documented endpoints show code 200 in their OpenAPI response examples.
_DOCUMENTED_READ_SUCCESS_CODES = (0, 200)


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

    async def get_work_parameters(self, device_id: str) -> WorkParameters:
        """Read current work parameters; does not change mower settings."""
        data = await self._async_request(
            "GET", f"/v1/mower/{_device_path(device_id)}/work-params",
            success_codes=_DOCUMENTED_READ_SUCCESS_CODES,
        )
        return parse_work_parameters(data)

    async def search_work_reports(
        self,
        device_id: str,
        *,
        page_number: int = 1,
        page_size: int = 10,
        end_work_time_start: int | None = None,
        end_work_time_end: int | None = None,
        work_type: int | None = None,
        work_result: int | None = None,
    ) -> WorkReportPage:
        """Query a page of historical work reports (POST is read-only)."""
        payload = _work_report_query(
            device_id, page_number, page_size,
            end_work_time_start=end_work_time_start,
            end_work_time_end=end_work_time_end,
            work_type=work_type,
            work_result=work_result,
        )
        data = await self._async_request(
            "POST", "/v1/mower/work-reports/search", json=payload,
            success_codes=_DOCUMENTED_READ_SUCCESS_CODES,
        )
        return parse_work_report_page(data)

    async def get_work_report_summary(
        self,
        device_id: str,
        *,
        end_work_time_start: int | None = None,
        end_work_time_end: int | None = None,
        work_type: int | None = None,
        work_result: int | None = None,
    ) -> WorkReportSummary:
        """Query aggregate historical work statistics (POST is read-only)."""
        payload = _work_report_query(
            device_id, 1, 10,
            end_work_time_start=end_work_time_start,
            end_work_time_end=end_work_time_end,
            work_type=work_type,
            work_result=work_result,
        )
        data = await self._async_request(
            "POST", "/v1/mower/work-reports/summary", json=payload,
            success_codes=_DOCUMENTED_READ_SUCCESS_CODES,
        )
        return parse_work_report_summary(data)

    async def get_work_report(self, device_id: str, work_id: str) -> WorkReportDetail:
        """Read one historical report by its documented work ID."""
        data = await self._async_request(
            "GET",
            f"/v1/mower/{_device_path(device_id)}/work-reports/{_device_path(work_id)}",
            success_codes=_DOCUMENTED_READ_SUCCESS_CODES,
        )
        return parse_work_report_detail(data)

    async def search_error_codes(
        self,
        device_id: str,
        *,
        page_number: int = 1,
        page_size: int = 10,
        start_date: str | None = None,
        end_date: str | None = None,
        error_code: str | None = None,
    ) -> DeviceErrorCodePage:
        """Query recorded fault/error codes; does not clear faults."""
        payload: dict[str, Any] = {
            "deviceId": _require_identifier(device_id, "device_id"),
            "pageNumber": _positive_int(page_number, "page_number"),
            "pageSize": _positive_int(page_size, "page_size"),
        }
        for key, value in (
            ("startDate", start_date), ("endDate", end_date), ("errorCode", error_code)
        ):
            if value is not None:
                if not isinstance(value, str):
                    raise TypeError(f"{key} must be a string")
                payload[key] = value
        data = await self._async_request(
            "POST", "/v1/mower/error-codes/search", json=payload,
            success_codes=_DOCUMENTED_READ_SUCCESS_CODES,
        )
        return parse_error_code_page(data)

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
        success_codes: tuple[int, ...] = (0,),
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
                    method, path, json=json, require_data=require_data,
                    retry_auth=False, success_codes=success_codes,
                )
            raise MammotionAuthenticationError("Mammotion rejected the access token")
        return _unwrap_api_envelope(
            payload, require_data=require_data, success_codes=success_codes
        )


def _device_path(device_id: str) -> str:
    return quote(_require_identifier(device_id, "path identifier"), safe="")


def _require_identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _positive_int(value: int, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _work_report_query(
    device_id: str,
    page_number: int,
    page_size: int,
    **filters: int | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "deviceId": _require_identifier(device_id, "device_id"),
        "pageNumber": _positive_int(page_number, "page_number"),
        "pageSize": _positive_int(page_size, "page_size"),
    }
    for key, field in (
        ("end_work_time_start", "endWorkTimeStart"),
        ("end_work_time_end", "endWorkTimeEnd"),
        ("work_type", "workType"),
        ("work_result", "workResult"),
    ):
        value = filters.get(key)
        if value is not None:
            if type(value) is not int:
                raise TypeError(f"{key} must be an integer")
            payload[field] = value
    return payload


def _unwrap_api_envelope(
    payload: object, *, require_data: bool = True,
    success_codes: tuple[int, ...] = (0,),
) -> object:
    if not isinstance(payload, Mapping):
        raise MammotionMalformedResponseError("Mammotion API response must be an object")
    code = payload.get("code")
    if isinstance(code, bool) or not isinstance(code, int):
        raise MammotionMalformedResponseError("Mammotion API response code must be an integer")
    if code not in success_codes:
        message = payload.get("msg")
        raise MammotionApiError(code, message if isinstance(message, str) else None)
    if require_data and "data" not in payload:
        raise MammotionMalformedResponseError("Successful Mammotion API response is missing data")
    return payload.get("data")
