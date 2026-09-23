"""Credential flow tests with no network access."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from custom_components.mammotion_openapi.api.exceptions import (
    MammotionAuthenticationError,
    MammotionMalformedResponseError,
    MammotionTransportError,
)
from custom_components.mammotion_openapi.api.models import Mower
from custom_components.mammotion_openapi.config_flow import MammotionOpenAPIConfigFlow
from tests.ha.support import FakeEntry, FakeHass

_INPUT = {"client_id": "test-client-id", "client_secret": "test-client-secret"}


class _Client:
    response: object = (Mower(id="mower-a", name="Garden Mower"),)

    def __init__(self, _session: object, _client_id: str, _client_secret: str) -> None:
        pass

    async def get_mowers(self) -> tuple[Mower, ...]:
        if isinstance(self.response, Exception):
            raise self.response
        return self.response  # type: ignore[return-value]


class ConfigFlowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.flow = MammotionOpenAPIConfigFlow()
        self.flow.hass = FakeHass()
        self.flow._entries = []
        _Client.response = (Mower(id="mower-a", name="Garden Mower"),)
        self.patcher = patch(
            "custom_components.mammotion_openapi.config_flow.MammotionApiClient", _Client
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    async def test_successful_configuration(self) -> None:
        result = await self.flow.async_step_user(_INPUT)

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"], _INPUT)
        self.assertEqual(result["title"], "Mammotion OpenAPI")

    async def test_invalid_credentials(self) -> None:
        _Client.response = MammotionAuthenticationError("test-client-secret")

        result = await self.flow.async_step_user(_INPUT)

        self.assertEqual(result["errors"], {"base": "invalid_auth"})
        self.assertNotIn("test-client-secret", str(result["errors"]))

    async def test_connection_failure(self) -> None:
        _Client.response = MammotionTransportError("test-client-secret")

        result = await self.flow.async_step_user(_INPUT)

        self.assertEqual(result["errors"], {"base": "cannot_connect"})
        self.assertNotIn("test-client-secret", str(result["errors"]))

    async def test_malformed_response(self) -> None:
        _Client.response = MammotionMalformedResponseError("bad response")

        result = await self.flow.async_step_user(_INPUT)

        self.assertEqual(result["errors"], {"base": "invalid_response"})

    async def test_unexpected_error_does_not_echo_credentials(self) -> None:
        _Client.response = RuntimeError("test-client-secret")

        result = await self.flow.async_step_user(_INPUT)

        self.assertEqual(result["errors"], {"base": "unknown"})
        self.assertNotIn("test-client-secret", str(result["errors"]))

    async def test_no_mowers(self) -> None:
        _Client.response = ()

        result = await self.flow.async_step_user(_INPUT)

        self.assertEqual(result["errors"], {"base": "no_mowers"})

    async def test_duplicate_client_id_is_rejected_without_account_identity(self) -> None:
        self.flow._entries = [FakeEntry()]

        result = await self.flow.async_step_user(_INPUT)

        self.assertEqual(result, {"type": "abort", "reason": "already_configured"})

    async def test_reauth_updates_existing_entry(self) -> None:
        entry = FakeEntry()
        self.flow._entries = [entry]
        self.flow._reauth_entry = entry
        replacement = {"client_id": "test-client-id", "client_secret": "new-test-secret"}

        initial = await self.flow.async_step_reauth(entry.data)
        result = await self.flow.async_step_reauth_confirm(replacement)

        self.assertEqual(initial["step_id"], "reauth_confirm")
        self.assertNotIn("new-test-secret", str(initial))
        self.assertEqual(result, {"type": "abort", "reason": "reauth_successful"})
        self.assertEqual(entry.data["client_secret"], "new-test-secret")

    async def test_options_flow_uses_conservative_poll_intervals(self) -> None:
        entry = FakeEntry()
        flow = MammotionOpenAPIConfigFlow.async_get_options_flow(entry)
        flow.config_entry = entry

        initial = await flow.async_step_init()
        self.assertEqual(initial["type"], "form")
        self.assertEqual(initial["data_schema"]({"update_interval": 10}), {
            "update_interval": 10,
        })
        with self.assertRaises(Exception):
            initial["data_schema"]({"update_interval": 1})

        result = await flow.async_step_init({"update_interval": 10})
        self.assertEqual(result, {
            "type": "create_entry", "data": {"update_interval": 10}
        })
