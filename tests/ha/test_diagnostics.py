"""Diagnostics must remain useful without exporting account or device secrets."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from custom_components.mammotion_openapi.api.models import Mower, MowerNetwork
from custom_components.mammotion_openapi.api.extended_models import (
    DeviceErrorCode, DeviceErrorCodePage, WorkReport, WorkReportPage,
)
from custom_components.mammotion_openapi.coordinator import MowerSnapshot
from custom_components.mammotion_openapi.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)
from custom_components.mammotion_openapi.read_only_coordinator import ReadOnlySnapshot
from tests.ha.support import FakeEntry, FakeHass


class DiagnosticsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.entry = FakeEntry(client_id="fake-private-client-id")
        self.entry.data["client_secret"] = "fake-private-client-secret"
        self.entry.data["access_token"] = "fake-access-token"
        self.entry.data["Authorization"] = "Bearer fake-authorization"
        self.entry.runtime_data = SimpleNamespace(
            coordinator=SimpleNamespace(
                last_update_success=True,
                data={
                    "fake-private-device-id": MowerSnapshot(
                        mower=Mower(
                            id="fake-private-device-id",
                            name="Private Garden Name",
                            nickname="Private Nickname",
                            icon="https://example.invalid/private-image.png",
                            model="Example Mower",
                            version="1.2.3",
                            online=True,
                            status="Standby",
                            battery_level=100,
                            charge_status=2,
                            network=MowerNetwork(
                                used_network="1", wifi_available=True, wifi_rssi=-53,
                                cellular_available=False, cellular_rssi=-63,
                            ),
                        ),
                        detail_available=True,
                    ),
                    "fake-rtk-id": MowerSnapshot(
                        mower=Mower(id="fake-rtk-id", model="RtkRefStationV1", online=True),
                        detail_available=True,
                    ),
                },
            ),
            read_only_coordinator=SimpleNamespace(data={
                "fake-private-device-id": ReadOnlySnapshot(
                    report_page=WorkReportPage(records=(
                        WorkReport(work_id="fake-private-work-id"),
                    )),
                    error_codes=DeviceErrorCodePage(records=(
                        DeviceErrorCode(implication="Private fault description"),
                    )),
                ),
            }),
            task_names={"fake-private-device-id": "Private Task Name"},
        )

    async def test_account_diagnostics_redact_credentials_and_identifiers(self) -> None:
        result = await async_get_config_entry_diagnostics(FakeHass(), self.entry)
        rendered = json.dumps(result)

        self.assertEqual(result["coordinator"]["device_count"], 2)
        self.assertEqual({device["kind"] for device in result["devices"]}, {
            "mower", "rtk_station"
        })
        self.assertEqual(result["credentials"], {
            "client_id": "**REDACTED**", "client_secret": "**REDACTED**"
        })
        self.assertIn("Standby", rendered)
        self.assertIn("-53", rendered)
        for secret in (
            "fake-private-client-id", "fake-private-client-secret",
            "fake-access-token", "fake-authorization", "fake-private-device-id",
            "fake-rtk-id", "Private Garden Name", "Private Nickname",
            "Private Task Name", "private-image.png",
            "fake-private-work-id", "Private fault description",
        ):
            self.assertNotIn(secret, rendered)

    async def test_device_diagnostics_select_only_the_requested_device(self) -> None:
        device = SimpleNamespace(identifiers={
            ("mammotion_openapi", "fake-private-device-id")
        })

        result = await async_get_device_diagnostics(FakeHass(), self.entry, device)
        rendered = json.dumps(result)

        self.assertEqual(result["device"]["model"], "Example Mower")
        self.assertEqual(result["device"]["battery_level"], 100)
        self.assertNotIn("fake-private-device-id", rendered)
        self.assertNotIn("fake-private-client-secret", rendered)

    async def test_unknown_device_diagnostics_are_safe(self) -> None:
        device = SimpleNamespace(identifiers={
            ("mammotion_openapi", "fake-unknown-id")
        })

        result = await async_get_device_diagnostics(FakeHass(), self.entry, device)

        self.assertEqual(result, {
            "domain": "mammotion_openapi", "device_found": False
        })
