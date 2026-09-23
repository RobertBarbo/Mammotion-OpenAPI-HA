"""Tests for OAuth client-credentials handling."""

from __future__ import annotations

import unittest

from custom_components.mammotion_openapi.api.auth import MammotionAuth, TOKEN_URL
from custom_components.mammotion_openapi.api.exceptions import MammotionAuthenticationError


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
    """Small aiohttp-session double that never performs network I/O."""

    def __init__(self, token_responses: list[_Response]) -> None:
        self.token_responses = token_responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    def post(self, url: str, *, data: dict[str, str]) -> _RequestContext:
        self.calls.append((url, data))
        return _RequestContext(self.token_responses.pop(0))


class MammotionAuthTest(unittest.IsolatedAsyncioTestCase):
    async def test_successful_authentication(self) -> None:
        session = FakeSession([_Response(200, {
            "code": 0,
            "msg": "Request success",
            "data": {"access_token": "test-token-one", "expires_in": 3600},
        })])
        auth = MammotionAuth(session, "test-client-id", "test-client-secret")  # type: ignore[arg-type]

        self.assertEqual(await auth.async_get_access_token(), "test-token-one")
        self.assertEqual(session.calls, [(TOKEN_URL, {
            "grant_type": "client_credentials",
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
        })])

    async def test_reuses_unexpired_token(self) -> None:
        session = FakeSession([_Response(200, {
            "code": 0, "msg": "Request success",
            "data": {"access_token": "test-token-one", "expires_in": 3600},
        })])
        auth = MammotionAuth(session, "test-client-id", "test-client-secret")  # type: ignore[arg-type]

        await auth.async_get_access_token()
        self.assertEqual(await auth.async_get_access_token(), "test-token-one")
        self.assertEqual(len(session.calls), 1)

    async def test_renews_token_before_expiry(self) -> None:
        now = [0.0]
        session = FakeSession([
            _Response(200, {"code": 0, "data": {"access_token": "test-token-one", "expires_in": 100}}),
            _Response(200, {"code": 0, "data": {"access_token": "test-token-two", "expires_in": 100}}),
        ])
        auth = MammotionAuth(
            session,  # type: ignore[arg-type]
            "test-client-id",
            "test-client-secret",
            clock=lambda: now[0],
        )

        self.assertEqual(await auth.async_get_access_token(), "test-token-one")
        now[0] = 70.0  # expiry is 100 - the 30-second renewal buffer
        self.assertEqual(await auth.async_get_access_token(), "test-token-two")
        self.assertEqual(len(session.calls), 2)

    async def test_http_auth_failure_is_typed(self) -> None:
        session = FakeSession([_Response(401, {"error": "invalid_client"})])
        auth = MammotionAuth(session, "test-client-id", "test-client-secret")  # type: ignore[arg-type]

        with self.assertRaises(MammotionAuthenticationError):
            await auth.async_get_access_token()
