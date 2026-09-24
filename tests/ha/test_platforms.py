"""Platform behavior with mower and RTK records from the official API shape."""

from __future__ import annotations

import unittest
from enum import Enum, IntFlag
from types import SimpleNamespace
from unittest.mock import patch

import voluptuous as vol

from homeassistant.components.lawn_mower import LawnMowerActivity
from homeassistant.exceptions import HomeAssistantError

from custom_components.mammotion_openapi import binary_sensor, button, lawn_mower, select, sensor, text
from custom_components.mammotion_openapi.api.exceptions import MammotionApiError, MammotionTransportError
from custom_components.mammotion_openapi.api.models import Mower, MowerAction, MowerNetwork, MowerPlan
from custom_components.mammotion_openapi.api.extended_models import (
    DeviceErrorCodePage, WorkParameters, WorkReport, WorkReportDetail,
    WorkReportPage, WorkReportSummary,
)
from custom_components.mammotion_openapi.coordinator import MammotionDataUpdateCoordinator
from custom_components.mammotion_openapi.read_only_coordinator import MammotionReadOnlyCoordinator
from tests.ha.support import FakeEntry, FakeHass


class _Client:
    def __init__(self) -> None:
        self.details: dict[str, Mower | Exception] = {
            "mower-a": Mower(
                id="mower-a", name="Garden Mower", online=True,
                status="Mowing", battery_level=48, charge_status=0,
                network=MowerNetwork(
                    used_network="1", wifi_available=True, wifi_rssi=-64,
                    cellular_available=False, cellular_rssi=-67,
                ),
            ),
            "mower-b": Mower(
                id="mower-b", name="Backyard Mower", online=True,
                status="TaskPaused", battery_level=33, charge_status=2,
            ),
            "rtk-a": Mower(
                id="rtk-a", nickname="RTK Antenna", model="RtkRefStationV1", online=True,
            ),
        }
        self.actions: list[tuple[str, MowerAction]] = []
        self.action_params: list[dict | None] = []
        self.action_error: Exception | None = None
        self.listed: dict[str, Mower] = {}
        self.plans: dict[str, tuple[MowerPlan, ...] | Exception] = {
            "mower-a": (MowerPlan(task_id="task-a", task_name="Front lawn"),),
            "mower-b": (),
        }
        self.plan_calls: list[str] = []
        self.read_calls: list[tuple[str, str]] = []

    async def get_mowers(self) -> tuple[Mower, ...]:
        for mower_id, detail in self.details.items():
            if not isinstance(detail, Mower):
                continue
            self.listed[mower_id] = Mower(
                id=mower_id,
                name=detail.name,
                nickname=detail.nickname,
                model=detail.model,
                online=detail.online,
            )
        return tuple(self.listed.values())

    async def get_mower(self, mower_id: str) -> Mower:
        detail = self.details[mower_id]
        if isinstance(detail, Exception):
            raise detail
        return detail

    async def get_plans(self, mower_id: str) -> tuple[MowerPlan, ...]:
        self.plan_calls.append(mower_id)
        plans = self.plans.get(mower_id, ())
        if isinstance(plans, Exception):
            raise plans
        return plans

    async def get_work_parameters(self, mower_id: str) -> WorkParameters:
        self.read_calls.append(("work_parameters", mower_id))
        return WorkParameters(knife_height=35, speed=60)

    async def get_work_report_summary(self, mower_id: str) -> WorkReportSummary:
        self.read_calls.append(("report_summary", mower_id))
        return WorkReportSummary(work_count=3, total_work_area=450.25)

    async def search_work_reports(self, mower_id: str) -> WorkReportPage:
        self.read_calls.append(("search_work_reports", mower_id))
        return WorkReportPage(records=(WorkReport(work_id="work-a"),), total=1)

    async def get_work_report(self, mower_id: str, work_id: str) -> WorkReportDetail:
        self.read_calls.append(("get_work_report", mower_id))
        return WorkReportDetail(energy_consume=120.5)

    async def search_error_codes(self, mower_id: str) -> DeviceErrorCodePage:
        self.read_calls.append(("search_error_codes", mower_id))
        return DeviceErrorCodePage(records=(), total=0)

    async def send_action(
        self, mower_id: str, action: MowerAction, params: dict | None = None
    ) -> None:
        if self.action_error:
            raise self.action_error
        self.actions.append((mower_id, action))
        self.action_params.append(params)


class PlatformTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.hass = FakeHass()
        self.entry = FakeEntry()
        self.client = _Client()
        self.coordinator = MammotionDataUpdateCoordinator(
            self.hass, self.entry, self.client  # type: ignore[arg-type]
        )
        await self.coordinator.async_config_entry_first_refresh()
        self.read_only_coordinator = MammotionReadOnlyCoordinator(
            self.hass, self.entry, self.client, self.coordinator  # type: ignore[arg-type]
        )
        await self.read_only_coordinator.async_config_entry_first_refresh()
        self.entry.runtime_data = SimpleNamespace(
            coordinator=self.coordinator, read_only_coordinator=self.read_only_coordinator,
            client=self.client,
            task_names={}, selected_task_names={},
        )
        self.mowers: list[lawn_mower.MammotionLawnMower] = []
        self.buttons: list[button.MammotionActionButton | button.MammotionRefreshButton] = []
        self.task_inputs: list[text.MammotionTaskNameText] = []
        self.sensors: list[sensor.MammotionSensor] = []
        self.last_update_sensors: list[sensor.MammotionLastDetailUpdateSensor] = []
        self.read_only_sensors: list[sensor.MammotionReadOnlySensor] = []
        self.task_selects: list[select.MammotionTaskSelect] = []
        self.binary_sensors: list[binary_sensor.MammotionBinarySensor] = []
        await lawn_mower.async_setup_entry(self.hass, self.entry, self.mowers.extend)  # type: ignore[arg-type]
        def add_sensors(entities: list) -> None:
            self.sensors.extend(item for item in entities if isinstance(item, sensor.MammotionSensor))
            self.last_update_sensors.extend(
                item for item in entities
                if isinstance(item, sensor.MammotionLastDetailUpdateSensor)
            )
            self.read_only_sensors.extend(
                item for item in entities
                if isinstance(item, sensor.MammotionReadOnlySensor)
            )
        await sensor.async_setup_entry(self.hass, self.entry, add_sensors)  # type: ignore[arg-type]
        await binary_sensor.async_setup_entry(
            self.hass, self.entry, self.binary_sensors.extend  # type: ignore[arg-type]
        )
        await button.async_setup_entry(self.hass, self.entry, self.buttons.extend)  # type: ignore[arg-type]
        await text.async_setup_entry(self.hass, self.entry, self.task_inputs.extend)  # type: ignore[arg-type]
        await select.async_setup_entry(self.hass, self.entry, self.task_selects.extend)  # type: ignore[arg-type]

    async def test_rtk_stays_a_device_without_mower_controls(self) -> None:
        self.assertEqual({entity.device_id for entity in self.mowers}, {"mower-a", "mower-b"})
        self.assertTrue(any(
            entity.device_id == "rtk-a" and entity.entity_description.key == "online"
            for entity in self.binary_sensors
        ))
        self.assertFalse(any(entity.device_id == "rtk-a" for entity in self.sensors))
        self.assertFalse(any(
            isinstance(entity, button.MammotionActionButton) and entity.device_id == "rtk-a"
            for entity in self.buttons
        ))
        self.assertTrue(any(
            isinstance(entity, button.MammotionRefreshButton) and entity.device_id == "rtk-a"
            for entity in self.buttons
        ))
        self.assertFalse(any(entity.device_id == "rtk-a" for entity in self.task_inputs))
        self.assertFalse(any(entity.device_id == "rtk-a" for entity in self.task_selects))
        self.assertFalse(any(entity.device_id == "rtk-a" for entity in self.read_only_sensors))
        self.assertFalse(any(device_id == "rtk-a" for _, device_id in self.client.read_calls))
        self.assertEqual(len(self.last_update_sensors), 3)

    async def test_observed_values_and_stable_identifiers(self) -> None:
        mower = next(entity for entity in self.mowers if entity.device_id == "mower-a")
        self.assertEqual(mower.activity, LawnMowerActivity.MOWING)
        self.assertEqual(mower._attr_unique_id, "mower-a_mower")
        self.assertEqual(mower._attr_device_info["identifiers"], {
            ("mammotion_openapi", "mower-a")
        })

        values = {
            entity.entity_description.key: entity.native_value
            for entity in self.sensors if entity.device_id == "mower-a"
        }
        self.assertEqual(values["battery_level"], 48)
        self.assertEqual(values["charge_status"], 0)
        self.assertEqual(values["status"], "Mowing")
        self.assertEqual(values["used_network"], "Wi-Fi")
        self.assertEqual(values["wifi_rssi"], -64)

        wifi_available = next(
            entity for entity in self.binary_sensors
            if entity.device_id == "mower-a" and entity.entity_description.key == "wifi_available"
        )
        self.assertIs(wifi_available.is_on, True)

    async def test_known_mower_actions(self) -> None:
        mowing = next(entity for entity in self.mowers if entity.device_id == "mower-a")
        paused = next(entity for entity in self.mowers if entity.device_id == "mower-b")

        await mowing.async_pause()
        await paused.async_start_mowing()
        await mowing.async_dock()
        self.client.details["mower-a"] = Mower(id="mower-a", online=True, status="Standby")
        await self.coordinator.async_request_refresh()
        await mowing.async_start_mowing()

        self.assertEqual(self.client.actions, [
            ("mower-a", MowerAction.PAUSE),
            ("mower-b", MowerAction.RESUME),
            ("mower-a", MowerAction.RETURN),
            ("mower-a", MowerAction.CMD_START),
        ])

    async def test_start_mowing_resumes_both_paused_statuses_only(self) -> None:
        mower = next(entity for entity in self.mowers if entity.device_id == "mower-a")
        cases = (
            ("TaskPaused", MowerAction.RESUME),
            ("Paused", MowerAction.RESUME),
            ("Standby", MowerAction.CMD_START),
            ("Mowing", MowerAction.CMD_START),
        )
        for status, expected_action in cases:
            with self.subTest(status=status):
                self.client.details["mower-a"] = Mower(
                    id="mower-a", online=True, status=status, charge_status=0,
                )
                await self.coordinator.async_request_refresh()
                self.client.actions.clear()

                await mower.async_start_mowing()

                self.assertEqual(self.client.actions, [("mower-a", expected_action)])

    async def test_all_explicit_commands_use_only_confirmed_payloads(self) -> None:
        mower = next(entity for entity in self.mowers if entity.device_id == "mower-a")

        await mower.async_cmd_start()
        await mower.async_start_task("Front lawn")
        await mower.async_pause()
        await mower.async_resume()
        await mower.async_stop()
        await mower.async_dock()
        await mower.async_cancel_return()

        self.assertEqual([action for _, action in self.client.actions], list(MowerAction))
        self.assertEqual(self.client.action_params, [
            None, {"taskName": "Front lawn"}, None, None, None, None, None,
        ])

    async def test_device_buttons_expose_all_actions(self) -> None:
        garden = [item for item in self.buttons if isinstance(item, button.MammotionActionButton) and item.device_id == "mower-a"]
        backyard = [item for item in self.buttons if isinstance(item, button.MammotionActionButton) and item.device_id == "mower-b"]

        self.assertEqual({item.entity_description.action for item in garden}, set(MowerAction))
        self.assertEqual({item.entity_description.action for item in backyard}, set(MowerAction))
        self.assertEqual(len({item._attr_unique_id for item in self.buttons}), 17)
        self.assertTrue(all(item.available for item in garden))

        for item in garden:
            if item.entity_description.action is MowerAction.START:
                continue
            await item.async_press()
        self.assertEqual([action for _, action in self.client.actions], [
            action for action in MowerAction if action is not MowerAction.START
        ])

    async def test_named_start_button_uses_local_task_name_only_for_its_mower(self) -> None:
        task_input = next(
            item for item in self.task_inputs if item.device_id == "mower-a"
        )
        garden_start = next(
            item for item in self.buttons
            if isinstance(item, button.MammotionActionButton)
            and item.device_id == "mower-a" and item.entity_description.action is MowerAction.START
        )
        backyard_start = next(
            item for item in self.buttons
            if isinstance(item, button.MammotionActionButton)
            and item.device_id == "mower-b" and item.entity_description.action is MowerAction.START
        )

        with self.assertRaises(HomeAssistantError):
            await garden_start.async_press()
        await task_input.async_set_value("Front lawn")
        self.assertEqual(task_input.native_value, "Front lawn")
        self.assertEqual(self.client.actions, [])
        with self.assertRaises(HomeAssistantError):
            await backyard_start.async_press()

        await garden_start.async_press()
        self.assertEqual(self.client.actions, [("mower-a", MowerAction.START)])
        self.assertEqual(self.client.action_params, [{"taskName": "Front lawn"}])

        await task_input.async_set_value(" ")
        self.assertEqual(task_input.native_value, "")

    async def test_offline_mower_buttons_are_unavailable(self) -> None:
        self.client.details["mower-b"] = Mower(id="mower-b", online=False)
        await self.coordinator.async_request_refresh()

        for item in self.buttons:
            if item.device_id != "mower-b" or not isinstance(item, button.MammotionActionButton):
                continue
            self.assertFalse(item.available)
            with self.assertRaises(HomeAssistantError):
                await item.async_press()
        self.assertEqual(self.client.actions, [])

    async def test_start_task_requires_nonempty_name(self) -> None:
        mower = next(entity for entity in self.mowers if entity.device_id == "mower-a")
        with self.assertRaises(HomeAssistantError):
            await mower.async_start_task("  ")
        self.assertEqual(self.client.actions, [])

    async def test_start_task_service_schema_requires_name(self) -> None:
        schema = next(
            schema for name, schema, _ in lawn_mower._MOWER_SERVICES
            if name == "start_task"
        )
        validator = vol.Schema(schema)
        with self.assertRaises(vol.Invalid):
            validator({})
        self.assertEqual(validator({"task_name": "Front lawn"}), {
            "task_name": "Front lawn"
        })

    async def test_stop_is_native_only_when_ha_supports_it(self) -> None:
        mower = next(entity for entity in self.mowers if entity.device_id == "mower-a")
        self.assertEqual(int(mower._attr_supported_features) & 8, 0)

        class NewerFeatures(IntFlag):
            START_MOWING = 1
            PAUSE = 2
            DOCK = 4
            STOP = 8

        with patch.object(lawn_mower, "LawnMowerEntityFeature", NewerFeatures):
            newer_mower = lawn_mower.MammotionLawnMower(self.coordinator, "mower-a")
        self.assertEqual(int(newer_mower._attr_supported_features) & 8, 8)

    async def test_legacy_entity_service_registration(self) -> None:
        from homeassistant.helpers import entity_platform, service

        modern_register = service.async_register_platform_entity_service
        del service.async_register_platform_entity_service
        try:
            entity_platform.current_platform.registered_services.clear()
            lawn_mower._register_legacy_mower_services()
            self.assertEqual(set(entity_platform.current_platform.registered_services), {
                "cmd_start", "start_task", "pause", "resume", "stop",
                "return_to_dock", "cancel_return",
            })
        finally:
            service.async_register_platform_entity_service = modern_register

    async def test_standby_on_dock_works_without_ha_idle_activity(self) -> None:
        mower = next(entity for entity in self.mowers if entity.device_id == "mower-a")
        self.client.details["mower-a"] = Mower(
            id="mower-a", online=True, status="Standby",
            battery_level=100, charge_status=2,
        )
        await self.coordinator.async_request_refresh()

        self.assertEqual(mower.activity, LawnMowerActivity.DOCKED)
        self.assertTrue(mower.available)

    async def test_confirmed_charging_and_raw_status_activity_mapping(self) -> None:
        mower = next(entity for entity in self.mowers if entity.device_id == "mower-a")
        cases = (
            ("TaskPaused", 0, LawnMowerActivity.PAUSED),
            ("TaskPaused", 1, LawnMowerActivity.DOCKED),
            ("TaskPaused", 2, LawnMowerActivity.DOCKED),
            ("TaskPaused", None, LawnMowerActivity.PAUSED),
            ("Paused", 0, LawnMowerActivity.PAUSED),
            ("Paused", 1, LawnMowerActivity.DOCKED),
            ("Paused", 2, LawnMowerActivity.DOCKED),
            ("Standby", 1, LawnMowerActivity.DOCKED),
            ("Standby", 2, LawnMowerActivity.DOCKED),
            ("Mowing", 0, LawnMowerActivity.MOWING),
            ("Working", 0, LawnMowerActivity.MOWING),
            ("Returning", 0, LawnMowerActivity.RETURNING),
            ("Abnormal", 0, LawnMowerActivity.ERROR),
            ("TaskPaused", 3, None),
            ("Paused", 3, None),
            ("Standby", 3, None),
        )
        for status, charge_status, expected in cases:
            with self.subTest(status=status, charge_status=charge_status):
                self.client.details["mower-a"] = Mower(
                    id="mower-a", online=True, status=status,
                    charge_status=charge_status,
                )
                await self.coordinator.async_request_refresh()
                self.assertEqual(mower.activity, expected)

    async def test_missing_ha_activity_members_are_not_used(self) -> None:
        mower = next(entity for entity in self.mowers if entity.device_id == "mower-a")

        class OlderActivities(Enum):
            MOWING = "mowing"
            PAUSED = "paused"

        with patch.object(lawn_mower, "LawnMowerActivity", OlderActivities):
            for status, charge_status in (
                ("TaskPaused", 2), ("Returning", 0), ("Abnormal", 0),
            ):
                with self.subTest(status=status):
                    self.client.details["mower-a"] = Mower(
                        id="mower-a", online=True, status=status,
                        charge_status=charge_status,
                    )
                    await self.coordinator.async_request_refresh()
                    self.assertIsNone(mower.activity)

    async def test_standby_off_dock_is_idle_when_ha_supports_it(self) -> None:
        mower = next(entity for entity in self.mowers if entity.device_id == "mower-a")
        self.client.details["mower-a"] = Mower(
            id="mower-a", online=True, status="Standby", charge_status=0,
        )
        await self.coordinator.async_request_refresh()

        self.assertIsNone(mower.activity)
        status = next(
            entity for entity in self.sensors
            if entity.device_id == "mower-a" and entity.entity_description.key == "status"
        )
        self.assertEqual(status.native_value, "Standby")

        class NewerLawnMowerActivity(Enum):
            IDLE = "idle"

        with patch.object(lawn_mower, "LawnMowerActivity", NewerLawnMowerActivity):
            self.assertEqual(mower.activity, NewerLawnMowerActivity.IDLE)

    async def test_offline_mower_is_unavailable(self) -> None:
        mower = next(entity for entity in self.mowers if entity.device_id == "mower-b")
        self.client.details["mower-b"] = Mower(
            id="mower-b", online=False, status="TaskPaused", charge_status=2,
        )
        await self.coordinator.async_request_refresh()

        self.assertFalse(mower.available)

    async def test_offline_and_failed_detail_block_commands(self) -> None:
        mowing = next(entity for entity in self.mowers if entity.device_id == "mower-a")
        online = next(
            entity for entity in self.binary_sensors
            if entity.device_id == "mower-a" and entity.entity_description.key == "online"
        )
        battery = next(
            entity for entity in self.sensors
            if entity.device_id == "mower-a" and entity.entity_description.key == "battery_level"
        )
        self.client.details["mower-a"] = MammotionTransportError("temporary outage")
        await self.coordinator.async_request_refresh()

        self.assertFalse(mowing.available)
        self.assertFalse(battery.available)
        self.assertTrue(online.available)
        with self.assertRaises(HomeAssistantError):
            await mowing.async_pause()

    async def test_api_error_does_not_echo_remote_text(self) -> None:
        mowing = next(entity for entity in self.mowers if entity.device_id == "mower-a")
        self.client.action_error = MammotionApiError(1, "test-client-secret")

        with self.assertRaises(HomeAssistantError) as context:
            await mowing.async_pause()
        self.assertNotIn("test-client-secret", str(context.exception))

    async def test_new_mower_and_new_fields_create_entities_after_refresh(self) -> None:
        self.client.details["mower-c"] = Mower(
            id="mower-c", online=True, status="Mowing", battery_level=74
        )

        await self.coordinator.async_request_refresh()

        self.assertIn("mower-c", {entity.device_id for entity in self.mowers})
        self.assertTrue(any(
            entity.device_id == "mower-c" and entity.entity_description.key == "battery_level"
            for entity in self.sensors
        ))
        self.assertEqual(
            len([item for item in self.buttons if item.device_id == "mower-c"]), 8
        )
        self.assertTrue(any(item.device_id == "mower-c" for item in self.task_inputs))

    async def test_saved_task_selection_is_local_and_used_by_start(self) -> None:
        task_select = next(item for item in self.task_selects if item.device_id == "mower-a")
        start = next(
            item for item in self.buttons
            if isinstance(item, button.MammotionActionButton)
            and item.device_id == "mower-a" and item.entity_description.action is MowerAction.START
        )
        self.assertEqual(task_select.options, ["Front lawn"])
        self.assertIsNone(task_select.current_option)
        await task_select.async_select_option("Front lawn")
        self.assertEqual(task_select.current_option, "Front lawn")
        self.assertEqual(self.client.actions, [])
        await start.async_press()
        self.assertEqual(self.client.action_params, [{"taskName": "Front lawn"}])

    async def test_empty_plans_keep_manual_input_and_no_select(self) -> None:
        self.assertNotIn("mower-b", {item.device_id for item in self.task_selects})
        task_input = next(item for item in self.task_inputs if item.device_id == "mower-b")
        await task_input.async_set_value("Back lawn")
        start = next(
            item for item in self.buttons
            if isinstance(item, button.MammotionActionButton)
            and item.device_id == "mower-b" and item.entity_description.action is MowerAction.START
        )
        await start.async_press()
        self.assertEqual(self.client.action_params, [{"taskName": "Back lawn"}])

    async def test_select_appears_when_plans_arrive_later(self) -> None:
        self.client.plans["mower-b"] = (
            MowerPlan(task_id="task-b", task_name="Back lawn"),
        )
        await self.coordinator.async_request_refresh()
        self.assertIn("mower-b", {item.device_id for item in self.task_selects})

    async def test_stale_plan_choice_cannot_send_removed_task(self) -> None:
        task_select = self.task_selects[0]
        await task_select.async_select_option("Front lawn")
        self.client.plans["mower-a"] = ()
        await self.coordinator.async_request_refresh()
        self.assertIsNone(task_select.current_option)
        start = next(
            item for item in self.buttons
            if isinstance(item, button.MammotionActionButton)
            and item.device_id == "mower-a" and item.entity_description.action is MowerAction.START
        )
        with self.assertRaises(HomeAssistantError):
            await start.async_press()
        self.assertEqual(self.client.actions, [])

    async def test_refresh_button_does_not_send_action(self) -> None:
        refresh = next(item for item in self.buttons if isinstance(item, button.MammotionRefreshButton))
        before = len(self.client.plan_calls)
        read_before = len(self.client.read_calls)
        await refresh.async_press()
        self.assertEqual(self.client.actions, [])
        self.assertGreater(len(self.client.plan_calls), before)
        self.assertGreater(len(self.client.read_calls), read_before)

    async def test_documented_read_only_values_have_separate_sensors(self) -> None:
        values = {
            item.entity_description.key: item.native_value
            for item in self.read_only_sensors if item.device_id == "mower-a"
        }
        self.assertEqual(values["work_count"], 3)
        self.assertEqual(values["total_work_area"], 450.25)
        self.assertNotIn("knife_height_code", values)
        self.assertNotIn("work_speed_code", values)
        self.assertEqual(values["recorded_error_count"], 0)
        self.assertEqual(values["first_returned_report_energy"], 120.5)
        self.assertIsNotNone(values["last_read_only_update"])
        self.assertEqual(self.client.actions, [])
        self.assertFalse(any(name == "work_parameters" for name, _ in self.client.read_calls))

    async def test_optional_endpoint_failure_does_not_disable_mower(self) -> None:
        async def failing_summary(_mower_id: str) -> WorkReportSummary:
            raise MammotionTransportError("temporary outage")

        self.client.get_work_report_summary = failing_summary  # type: ignore[method-assign]
        await self.read_only_coordinator.async_request_refresh()
        summary_sensor = next(
            item for item in self.read_only_sensors
            if item.device_id == "mower-a" and item.entity_description.key == "work_count"
        )
        mower = next(item for item in self.mowers if item.device_id == "mower-a")
        self.assertFalse(summary_sensor.available)
        self.assertTrue(mower.available)

    async def test_unexpected_optional_failure_is_isolated(self) -> None:
        async def failing_summary(_mower_id: str) -> WorkReportSummary:
            raise RuntimeError("fake-sensitive-response")

        self.client.get_work_report_summary = failing_summary  # type: ignore[method-assign]
        await self.read_only_coordinator.async_request_refresh()
        summary_sensor = next(
            item for item in self.read_only_sensors
            if item.device_id == "mower-a" and item.entity_description.key == "work_count"
        )
        mower = next(item for item in self.mowers if item.device_id == "mower-a")
        self.assertFalse(summary_sensor.available)
        self.assertTrue(mower.available)

    async def test_action_then_optional_failure_keeps_all_core_devices_available(self) -> None:
        async def failing_summary(_mower_id: str) -> WorkReportSummary:
            raise MammotionTransportError("temporary optional outage")

        self.client.get_work_report_summary = failing_summary  # type: ignore[method-assign]
        self.client.plans["mower-a"] = MammotionTransportError("temporary plan outage")
        mower = next(item for item in self.mowers if item.device_id == "mower-a")
        other_mower = next(item for item in self.mowers if item.device_id == "mower-b")
        rtk_online = next(
            item for item in self.binary_sensors
            if item.device_id == "rtk-a" and item.entity_description.key == "online"
        )

        await mower.async_pause()
        await self.read_only_coordinator.async_request_refresh()

        self.assertEqual(self.client.actions, [("mower-a", MowerAction.PAUSE)])
        self.assertTrue(self.coordinator.last_update_success)
        self.assertTrue(mower.available)
        self.assertTrue(other_mower.available)
        self.assertTrue(rtk_online.available)

    async def test_failed_post_action_core_refresh_preserves_known_availability(self) -> None:
        async def failing_list() -> tuple[Mower, ...]:
            raise MammotionTransportError("brief outage after command")

        self.client.get_mowers = failing_list  # type: ignore[method-assign]
        mower = next(item for item in self.mowers if item.device_id == "mower-a")
        other_mower = next(item for item in self.mowers if item.device_id == "mower-b")

        await mower.async_pause()

        self.assertEqual(self.client.actions, [("mower-a", MowerAction.PAUSE)])
        self.assertTrue(self.coordinator.last_update_success)
        self.assertTrue(mower.available)
        self.assertTrue(other_mower.available)

    async def test_empty_post_action_list_does_not_drop_known_devices(self) -> None:
        async def empty_list() -> tuple[Mower, ...]:
            return ()

        self.client.get_mowers = empty_list  # type: ignore[method-assign]
        mower = next(item for item in self.mowers if item.device_id == "mower-a")
        other_mower = next(item for item in self.mowers if item.device_id == "mower-b")

        await mower.async_pause()

        self.assertTrue(self.coordinator.last_update_success)
        self.assertTrue(mower.available)
        self.assertTrue(other_mower.available)
        self.assertIn("rtk-a", self.coordinator.data)

    async def test_action_button_uses_safe_post_command_refresh(self) -> None:
        async def failing_list() -> tuple[Mower, ...]:
            raise MammotionTransportError("brief outage after button command")

        self.client.get_mowers = failing_list  # type: ignore[method-assign]
        pause_button = next(
            item for item in self.buttons
            if isinstance(item, button.MammotionActionButton)
            and item.device_id == "mower-a"
            and item.entity_description.action is MowerAction.PAUSE
        )
        other_mower = next(item for item in self.mowers if item.device_id == "mower-b")

        await pause_button.async_press()

        self.assertEqual(self.client.actions, [("mower-a", MowerAction.PAUSE)])
        self.assertTrue(self.coordinator.last_update_success)
        self.assertTrue(other_mower.available)

    async def test_manual_refresh_never_calls_unsafe_work_params(self) -> None:
        refresh = next(
            item for item in self.buttons
            if isinstance(item, button.MammotionRefreshButton)
            and item.device_id == "mower-a"
        )
        self.client.read_calls.clear()

        await refresh.async_press()

        self.assertFalse(any(name == "work_parameters" for name, _ in self.client.read_calls))

    async def test_empty_reports_do_not_request_report_detail(self) -> None:
        async def empty_reports(_mower_id: str) -> WorkReportPage:
            return WorkReportPage(records=(), total=0)

        self.client.search_work_reports = empty_reports  # type: ignore[method-assign]
        self.client.read_calls.clear()
        await self.read_only_coordinator.async_request_refresh()
        self.assertFalse(any(name == "get_work_report" for name, _ in self.client.read_calls))

    async def test_unexpected_history_shape_preserves_previous_optional_snapshot(self) -> None:
        async def broken_reports(_mower_id: str) -> WorkReportPage:
            return SimpleNamespace(records=None)  # type: ignore[return-value]

        previous = self.read_only_coordinator.data["mower-a"]
        self.client.search_work_reports = broken_reports  # type: ignore[method-assign]

        await self.read_only_coordinator.async_request_refresh()

        self.assertTrue(self.read_only_coordinator.last_update_success)
        self.assertEqual(self.read_only_coordinator.data["mower-a"], previous)
        self.assertTrue(next(item for item in self.mowers if item.device_id == "mower-a").available)

    async def test_rtk_manual_refresh_does_not_request_read_only_paths(self) -> None:
        refresh = next(
            item for item in self.buttons
            if isinstance(item, button.MammotionRefreshButton) and item.device_id == "rtk-a"
        )
        self.client.read_calls.clear()
        await refresh.async_press()
        self.assertEqual(self.client.read_calls, [])

    async def test_network_code_fallback(self) -> None:
        self.assertEqual(sensor._network_name("2"), "Cellular")
        self.assertEqual(sensor._network_name("99"), "99")
        self.assertIsNone(sensor._network_name(None))

    async def test_unknown_status_is_not_assigned_an_activity(self) -> None:
        mower = next(entity for entity in self.mowers if entity.device_id == "mower-a")
        self.client.details["mower-a"] = Mower(
            id="mower-a", online=True, status="UndocumentedState", charge_status=0,
        )
        await self.coordinator.async_request_refresh()
        self.assertIsNone(mower.activity)
