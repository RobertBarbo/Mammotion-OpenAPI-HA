"""Entry setup, device registration and unload tests."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from custom_components.mammotion_openapi import async_setup, async_setup_entry, async_unload_entry
from custom_components.mammotion_openapi.api.models import Mower
from tests.ha.support import FakeEntry, FakeHass


class _Client:
    def __init__(self, _session: object, _client_id: str, _client_secret: str) -> None:
        self.details = {
            "mower-a": Mower(
                id="mower-a", name="Garden Mower", nickname="Front Lawn",
                model="Example Model", version="1.2.3",
            ),
            "mower-b": Mower(id="mower-b", name="Backyard Mower"),
            "rtk-a": Mower(
                id="rtk-a", name="RTK station", nickname="RTK Antenna",
                model="RtkRefStationV1",
            ),
        }

    async def get_mowers(self) -> tuple[Mower, ...]:
        return tuple(self.details.values())

    async def get_mower(self, mower_id: str) -> Mower:
        return self.details[mower_id]

    async def get_plans(self, mower_id: str) -> tuple:
        return ()


class SetupTest(unittest.IsolatedAsyncioTestCase):
    async def test_registers_all_command_services_before_entries_load(self) -> None:
        hass = FakeHass()

        self.assertTrue(await async_setup(hass, {}))  # type: ignore[arg-type]
        self.assertEqual(set(hass.registered_services), {
            "cmd_start", "start_task", "pause", "resume", "stop",
            "return_to_dock", "cancel_return",
        })
        self.assertTrue(all(
            domain == "lawn_mower"
            for domain, _, _ in hass.registered_services.values()
        ))

    async def test_setup_registers_multiple_devices_and_unload_removes_listener(self) -> None:
        hass = FakeHass()
        entry = FakeEntry()
        with patch("custom_components.mammotion_openapi.MammotionApiClient", _Client):
            self.assertTrue(await async_setup_entry(hass, entry))  # type: ignore[arg-type]

        self.assertEqual(set(hass.registry.devices), {"mower-a", "mower-b", "rtk-a"})
        self.assertEqual(hass.registry.devices["mower-a"]["identifiers"], {
            ("mammotion_openapi", "mower-a")
        })
        self.assertEqual(hass.registry.devices["mower-a"]["name"], "Front Lawn")
        self.assertEqual(hass.registry.devices["mower-a"]["manufacturer"], "Mammotion")
        self.assertEqual(hass.registry.devices["mower-a"]["model"], "Example Model")
        self.assertEqual(hass.registry.devices["mower-a"]["sw_version"], "1.2.3")
        self.assertEqual(hass.registry.devices["mower-b"]["name"], "Backyard Mower")
        self.assertEqual(hass.registry.devices["rtk-a"]["name"], "RTK Antenna")
        self.assertEqual(hass.registry.devices["rtk-a"]["model"], "RtkRefStationV1")
        self.assertIs(entry.runtime_data.coordinator.config_entry, entry)
        self.assertEqual(len(entry.runtime_data.coordinator._listeners), 1)
        self.assertEqual(hass.config_entries.forwarded, [
            ("lawn_mower", "sensor", "binary_sensor", "button", "text", "select")
        ])

        entry.runtime_data.client.details["mower-c"] = Mower(id="mower-c")
        await entry.runtime_data.coordinator.async_request_refresh()
        self.assertEqual(
            hass.registry.devices["mower-c"]["name"], "Mammotion device mower-c"
        )

        self.assertTrue(await async_unload_entry(hass, entry))  # type: ignore[arg-type]
        self.assertEqual(hass.config_entries.unloaded, [
            ("lawn_mower", "sensor", "binary_sensor", "button", "text", "select")
        ])
        entry.process_unload_callbacks()
        self.assertEqual(entry.runtime_data.coordinator._listeners, [])
