"""Coordinator tests for multiple devices and partial failures."""

from __future__ import annotations

import unittest

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.mammotion_openapi.api.exceptions import (
    MammotionAuthenticationError,
    MammotionTransportError,
)
from custom_components.mammotion_openapi.api.models import Mower
from custom_components.mammotion_openapi.coordinator import MammotionDataUpdateCoordinator
from tests.ha.support import FakeEntry, FakeHass


class _Client:
    def __init__(self) -> None:
        self.listed = (
            Mower(id="mower-a", name="Garden Mower"),
            Mower(id="mower-b", name="Backyard Mower"),
        )
        self.details: dict[str, Mower | Exception] = {
            "mower-a": Mower(id="mower-a", name="Garden Mower", status="Mowing"),
            "mower-b": Mower(id="mower-b", name="Backyard Mower", status="TaskPaused"),
        }
        self.calls: list[str] = []

    async def get_mowers(self) -> tuple[Mower, ...]:
        if isinstance(self.listed, Exception):
            raise self.listed
        return self.listed

    async def get_mower(self, mower_id: str) -> Mower:
        self.calls.append(mower_id)
        detail = self.details[mower_id]
        if isinstance(detail, Exception):
            raise detail
        return detail


class CoordinatorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = _Client()
        self.coordinator = MammotionDataUpdateCoordinator(
            FakeHass(), FakeEntry(), self.client  # type: ignore[arg-type]
        )

    async def test_multiple_mower_discovery(self) -> None:
        await self.coordinator.async_config_entry_first_refresh()

        self.assertEqual(set(self.coordinator.data), {"mower-a", "mower-b"})
        self.assertEqual(set(self.client.calls), {"mower-a", "mower-b"})
        self.assertEqual(self.coordinator.data["mower-a"].mower.status, "Mowing")
        self.assertTrue(self.coordinator.data["mower-b"].detail_available)

    async def test_refresh_keeps_last_detail_when_one_request_fails(self) -> None:
        await self.coordinator.async_config_entry_first_refresh()
        self.client.details["mower-a"] = Mower(id="mower-a", status="TaskPaused")
        self.client.details["mower-b"] = MammotionTransportError("temporary outage")

        await self.coordinator.async_request_refresh()

        self.assertEqual(self.coordinator.data["mower-a"].mower.status, "TaskPaused")
        self.assertTrue(self.coordinator.data["mower-a"].detail_available)
        self.assertEqual(self.coordinator.data["mower-b"].mower.status, "TaskPaused")
        self.assertFalse(self.coordinator.data["mower-b"].detail_available)

    async def test_list_metadata_is_retained_when_detail_omits_it(self) -> None:
        self.client.listed = (
            Mower(id="mower-a", name="Garden Mower", model="Example Model", online=True),
        )
        self.client.details["mower-a"] = Mower(id="mower-a", status="Mowing")

        await self.coordinator.async_config_entry_first_refresh()

        mower = self.coordinator.data["mower-a"].mower
        self.assertEqual(mower.model, "Example Model")
        self.assertEqual(mower.name, "Garden Mower")
        self.assertIs(mower.online, True)

    async def test_first_refresh_falls_back_to_list_for_failed_detail(self) -> None:
        self.client.details["mower-b"] = MammotionTransportError("temporary outage")

        await self.coordinator.async_config_entry_first_refresh()

        self.assertEqual(self.coordinator.data["mower-b"].mower.name, "Backyard Mower")
        self.assertFalse(self.coordinator.data["mower-b"].detail_available)

    async def test_auth_failure_triggers_reauth_without_secret_in_error(self) -> None:
        self.client.details["mower-b"] = MammotionAuthenticationError("test-client-secret")

        with self.assertRaises(ConfigEntryAuthFailed) as context:
            await self.coordinator.async_config_entry_first_refresh()
        self.assertNotIn("test-client-secret", str(context.exception))

    async def test_list_failure_is_update_failure(self) -> None:
        self.client.listed = MammotionTransportError("test-client-secret")

        with self.assertRaises(UpdateFailed) as context:
            await self.coordinator.async_config_entry_first_refresh()
        self.assertNotIn("test-client-secret", str(context.exception))
