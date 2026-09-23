"""Tests for the standalone Mammotion Open API client."""

from __future__ import annotations

import unittest
from typing import Any

from custom_components.mammotion_openapi.api.client import API_BASE_URL, MammotionApiClient
from custom_components.mammotion_openapi.api.exceptions import (
    MammotionApiError,
    MammotionAuthenticationError,
    MammotionMalformedResponseError,
    MammotionTransportError,
)
from custom_components.mammotion_openapi.api.models import MowerAction


class _Response:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._payload = payload

    async def json(self, **_kwargs: object) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _RequestContext:
    def __init__(self, response: _Response) -> None:
        self._response = response

    async def __aenter__(self) -> _Response:
        return self._response

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeSession:
    def __init__(self, token_responses: list[_Response], api_responses: list[_Response]) -> None:
        self.token_responses = token_responses
        self.api_responses = api_responses
        self.posts: list[tuple[str, dict[str, str]]] = []
        self.requests: list[dict[str, Any]] = []

    def post(self, url: str, *, data: dict[str, str]) -> _RequestContext:
        self.posts.append((url, data))
        return _RequestContext(self.token_responses.pop(0))

    def request(self, method: str, url: str, **kwargs: Any) -> _RequestContext:
        self.requests.append({"method": method, "url": url, **kwargs})
        return _RequestContext(self.api_responses.pop(0))


def _token() -> _Response:
    return _Response(200, {
        "code": 0, "msg": "Request success",
        "data": {"access_token": "test-access-token", "expires_in": 3600},
    })


class MammotionApiClientTest(unittest.IsolatedAsyncioTestCase):
    def _client(self, *responses: _Response) -> tuple[MammotionApiClient, FakeSession]:
        session = FakeSession([_token()], list(responses))
        return MammotionApiClient(session, "test-client-id", "test-client-secret"), session  # type: ignore[arg-type]

    async def test_gets_multiple_mowers(self) -> None:
        client, _session = self._client(_Response(200, {"code": 0, "msg": "Request success", "data": [
            {"id": "mower-a", "name": "Garden Mower", "online": 1},
            {"id": "mower-b", "name": "Backyard Mower", "online": 0, "batteryLevel": 33},
        ]}))

        mowers = await client.get_mowers()

        self.assertEqual([mower.name for mower in mowers], ["Garden Mower", "Backyard Mower"])
        self.assertEqual(mowers[0].online, True)
        self.assertEqual(mowers[1].online, False)
        self.assertEqual(mowers[1].battery_level, 33)

    async def test_parses_mower_detail_and_network_data(self) -> None:
        client, _session = self._client(_Response(200, {"code": 0, "data": {
            "id": "mower-a",
            "name": "Garden Mower",
            "nickname": "Front Lawn",
            "model": "Example Model",
            "icon": "mower-icon",
            "version": "1.2.3",
            "online": 1,
            "status": "Mowing",
            "batteryLevel": 48,
            "chargeStatus": 0,
            "network": {
                "usedNetwork": "1",
                "wifiAvailable": True,
                "wifiRssi": -64,
                "cellularAvailable": False,
                "cellularRssi": -67,
            },
        }}))

        mower = await client.get_mower("mower-a")

        self.assertEqual(mower.nickname, "Front Lawn")
        self.assertIs(mower.online, True)
        self.assertEqual(mower.status, "Mowing")
        self.assertEqual(mower.charge_status, 0)
        self.assertEqual(mower.network.used_network if mower.network else None, "1")
        self.assertEqual(mower.network.wifi_rssi if mower.network else None, -64)
        self.assertFalse(mower.network.cellular_available if mower.network else True)

    async def test_parses_paused_mower_detail(self) -> None:
        client, _session = self._client(_Response(200, {"code": 0, "data": {
            "id": "mower-b", "name": "Backyard Mower", "online": 1,
            "status": "TaskPaused", "batteryLevel": 33, "chargeStatus": 2,
        }}))

        mower = await client.get_mower("mower-b")

        self.assertEqual(mower.status, "TaskPaused")
        self.assertEqual(mower.charge_status, 2)
        self.assertIsNone(mower.network)

    async def test_parses_official_one_item_detail_list(self) -> None:
        client, _session = self._client(_Response(200, {"code": 0, "data": [
            {"id": "mower-a", "name": "Garden Mower", "online": 1,
             "status": "Mowing", "batteryLevel": 48, "chargeStatus": 0},
        ]}))

        mower = await client.get_mower("mower-a")

        self.assertEqual(mower.status, "Mowing")
        self.assertEqual(mower.battery_level, 48)

    async def test_rejects_empty_detail_list(self) -> None:
        client, _session = self._client(_Response(200, {"code": 0, "data": []}))

        with self.assertRaises(MammotionMalformedResponseError):
            await client.get_mower("mower-a")

    async def test_rejects_mismatched_detail_id(self) -> None:
        client, _session = self._client(_Response(200, {"code": 0, "data": [
            {"id": "another-fake-id"},
        ]}))

        with self.assertRaises(MammotionMalformedResponseError):
            await client.get_mower("mower-a")

    async def test_parses_plans(self) -> None:
        client, _session = self._client(_Response(200, {"code": 0, "data": [
            {"taskId": "task-a", "taskName": "Morning mow"},
            {"taskId": "task-b", "taskName": "Evening mow"},
        ]}))

        plans = await client.get_plans("mower-a")

        self.assertEqual([(plan.task_id, plan.task_name) for plan in plans], [
            ("task-a", "Morning mow"),
            ("task-b", "Evening mow"),
        ])

    async def test_parses_empty_plan_list(self) -> None:
        client, _session = self._client(_Response(200, {"code": 0, "data": []}))

        self.assertEqual(await client.get_plans("mower-a"), ())

    async def test_rejects_non_list_plan_data(self) -> None:
        client, _session = self._client(_Response(200, {"code": 0, "data": {
            "taskId": "task-a", "taskName": "Morning mow",
        }}))

        with self.assertRaises(MammotionMalformedResponseError):
            await client.get_plans("mower-a")

    async def test_sends_successful_action(self) -> None:
        client, session = self._client(_Response(200, {"code": 0, "msg": "Request success"}))

        await client.send_action("mower-a", MowerAction.PAUSE)

        self.assertEqual(session.requests[0]["method"], "POST")
        self.assertEqual(session.requests[0]["url"], f"{API_BASE_URL}/v1/mower/action")
        self.assertEqual(session.requests[0]["json"], {
            "deviceId": "mower-a", "action": "PAUSE", "params": {},
        })

    async def test_sends_resume_with_explicit_empty_params(self) -> None:
        client, session = self._client(_Response(200, {"code": 0, "msg": "Request success"}))

        await client.send_action("mower-a", MowerAction.RESUME, {})

        self.assertEqual(session.requests[0]["json"], {
            "deviceId": "mower-a", "action": "RESUME", "params": {},
        })

    async def test_sends_named_task_using_official_start_payload(self) -> None:
        client, session = self._client(_Response(200, {"code": 0, "msg": "Request success"}))

        await client.send_action(
            "mower-a", MowerAction.START, {"taskName": "Front lawn"}
        )

        self.assertEqual(session.requests[0]["json"], {
            "deviceId": "mower-a",
            "action": "START",
            "params": {"taskName": "Front lawn"},
        })

    async def test_nonzero_api_code_raises_typed_error(self) -> None:
        client, _session = self._client(_Response(200, {"code": 1001, "msg": "Action rejected", "data": None}))

        with self.assertRaises(MammotionApiError) as context:
            await client.get_mowers()
        self.assertEqual(context.exception.code, 1001)

    async def test_malformed_response_raises_typed_error(self) -> None:
        client, _session = self._client(_Response(200, {"code": 0}))

        with self.assertRaises(MammotionMalformedResponseError):
            await client.get_mowers()

    async def test_api_http_failure_is_typed(self) -> None:
        client, _session = self._client(_Response(503, None))

        with self.assertRaises(MammotionTransportError):
            await client.get_mowers()

    async def test_api_auth_failure_is_typed_after_retry(self) -> None:
        client, session = self._client(_Response(401, None), _Response(401, None))
        session.token_responses.append(_token())

        with self.assertRaises(MammotionAuthenticationError):
            await client.get_mowers()
        self.assertEqual(len(session.posts), 2)
