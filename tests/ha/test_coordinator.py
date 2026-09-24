"""Coordinator tests for multiple devices and partial failures."""

from __future__ import annotations

import unittest

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.mammotion_openapi.api.exceptions import (
    MammotionAuthenticationError,
    MammotionTransportError,
)
from custom_components.mammotion_openapi.api.models import Mower, MowerPlan
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
        self.plan_calls: list[str] = []
        self.plans: dict[str, tuple[MowerPlan, ...] | Exception] = {
            "mower-a": (MowerPlan(task_id="task-a", task_name="Front lawn"),),
            "mower-b": (),
        }

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

    async def get_plans(self, mower_id: str) -> tuple[MowerPlan, ...]:
        self.plan_calls.append(mower_id)
        plans = self.plans[mower_id]
        if isinstance(plans, Exception):
            raise plans
        return plans


class CoordinatorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = _Client()
        self.entry = FakeEntry()
        self.coordinator = MammotionDataUpdateCoordinator(
            FakeHass(), self.entry, self.client  # type: ignore[arg-type]
        )

    async def test_multiple_mower_discovery(self) -> None:
        await self.coordinator.async_config_entry_first_refresh()

        self.assertEqual(set(self.coordinator.data), {"mower-a", "mower-b"})
        self.assertEqual(set(self.client.calls), {"mower-a", "mower-b"})
        self.assertEqual(self.coordinator.data["mower-a"].mower.status, "Mowing")
        self.assertTrue(self.coordinator.data["mower-b"].detail_available)
        self.assertEqual(self.coordinator.data["mower-a"].plans[0].task_name, "Front lawn")
        self.assertEqual(self.coordinator.data["mower-b"].plans, ())
        self.assertIsNotNone(self.coordinator.data["mower-a"].last_detail_update)

    async def test_refresh_keeps_last_detail_when_one_request_fails(self) -> None:
        await self.coordinator.async_config_entry_first_refresh()
        previous_update = self.coordinator.data["mower-b"].last_detail_update
        self.client.details["mower-a"] = Mower(id="mower-a", status="TaskPaused")
        self.client.details["mower-b"] = MammotionTransportError("temporary outage")

        await self.coordinator.async_request_refresh()

        self.assertEqual(self.coordinator.data["mower-a"].mower.status, "TaskPaused")
        self.assertTrue(self.coordinator.data["mower-a"].detail_available)
        self.assertEqual(self.coordinator.data["mower-b"].mower.status, "TaskPaused")
        self.assertFalse(self.coordinator.data["mower-b"].detail_available)
        self.assertEqual(self.coordinator.data["mower-b"].plans, ())
        self.assertEqual(self.coordinator.data["mower-b"].last_detail_update, previous_update)

    async def test_plan_failure_keeps_last_successful_plan(self) -> None:
        await self.coordinator.async_config_entry_first_refresh()
        self.client.plans["mower-a"] = MammotionTransportError("temporary outage")

        await self.coordinator.async_request_refresh()

        self.assertTrue(self.coordinator.data["mower-a"].detail_available)
        self.assertEqual(self.coordinator.data["mower-a"].plans[0].task_name, "Front lawn")

    async def test_rtk_does_not_request_plans(self) -> None:
        self.client.listed += (Mower(id="rtk-a", model="RtkRefStationV1"),)
        self.client.details["rtk-a"] = Mower(id="rtk-a", model="RtkRefStationV1")

        await self.coordinator.async_config_entry_first_refresh()

        self.assertNotIn("rtk-a", self.client.plan_calls)
        self.assertEqual(self.coordinator.data["rtk-a"].plans, ())

    async def test_optional_plan_auth_failure_does_not_fail_core(self) -> None:
        self.client.plans["mower-a"] = MammotionAuthenticationError("test-client-secret")

        await self.coordinator.async_config_entry_first_refresh()

        self.assertTrue(self.coordinator.last_update_success)
        self.assertEqual(self.coordinator.data["mower-a"].plans, ())
        self.assertTrue(self.coordinator.data["mower-b"].detail_available)

    async def test_configured_interval(self) -> None:
        from datetime import timedelta

        entry = FakeEntry()
        entry.options["update_interval"] = 10
        coordinator = MammotionDataUpdateCoordinator(FakeHass(), entry, self.client)
        self.assertEqual(coordinator.update_interval, timedelta(minutes=10))

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
        await self.coordinator.async_config_entry_first_refresh()
        self.client.listed = MammotionTransportError("test-client-secret")

        with self.assertRaises(UpdateFailed) as context:
            await self.coordinator.async_request_refresh()
        self.assertNotIn("test-client-secret", str(context.exception))
        self.assertFalse(self.coordinator.last_update_success)

    async def test_list_auth_failure_still_requires_reauth(self) -> None:
        self.client.listed = MammotionAuthenticationError("test-client-secret")

        with self.assertRaises(ConfigEntryAuthFailed) as context:
            await self.coordinator.async_config_entry_first_refresh()
        self.assertNotIn("test-client-secret", str(context.exception))

    async def test_post_action_auth_failure_starts_reauth_without_dropping_data(self) -> None:
        await self.coordinator.async_config_entry_first_refresh()
        self.client.listed = MammotionAuthenticationError("test-client-secret")

        await self.coordinator.async_refresh_after_action()

        self.assertTrue(self.entry.reauth_started)
        self.assertTrue(self.coordinator.last_update_success)
        self.assertEqual(set(self.coordinator.data), {"mower-a", "mower-b"})

    async def test_unexpected_detail_failure_is_isolated(self) -> None:
        await self.coordinator.async_config_entry_first_refresh()
        self.client.details["mower-a"] = RuntimeError("temporary detail parsing failure")
        self.client.details["mower-b"] = Mower(
            id="mower-b", status="Mowing", online=True
        )

        await self.coordinator.async_request_refresh()

        self.assertTrue(self.coordinator.last_update_success)
        self.assertFalse(self.coordinator.data["mower-a"].detail_available)
        self.assertTrue(self.coordinator.data["mower-b"].detail_available)
        self.assertEqual(self.coordinator.data["mower-b"].mower.status, "Mowing")

    async def test_mismatched_detail_id_is_isolated(self) -> None:
        await self.coordinator.async_config_entry_first_refresh()
        self.client.details["mower-a"] = Mower(id="wrong-fake-id")

        await self.coordinator.async_request_refresh()

        self.assertTrue(self.coordinator.last_update_success)
        self.assertFalse(self.coordinator.data["mower-a"].detail_available)
        self.assertTrue(self.coordinator.data["mower-b"].detail_available)
