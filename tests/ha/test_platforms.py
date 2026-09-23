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
from custom_components.mammotion_openapi.coordinator import MammotionDataUpdateCoordinator
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
        self.entry.runtime_data = SimpleNamespace(
            coordinator=self.coordinator, client=self.client,
            task_names={}, selected_task_names={},
        )
        self.mowers: list[lawn_mower.MammotionLawnMower] = []
        self.buttons: list[button.MammotionActionButton | button.MammotionRefreshButton] = []
        self.task_inputs: list[text.MammotionTaskNameText] = []
        self.sensors: list[sensor.MammotionSensor] = []
        self.last_update_sensors: list[sensor.MammotionLastDetailUpdateSensor] = []
        self.task_selects: list[select.MammotionTaskSelect] = []
        self.binary_sensors: list[binary_sensor.MammotionBinarySensor] = []
        await lawn_mower.async_setup_entry(self.hass, self.entry, self.mowers.extend)  # type: ignore[arg-type]
        def add_sensors(entities: list) -> None:
            self.sensors.extend(item for item in entities if isinstance(item, sensor.MammotionSensor))
            self.last_update_sensors.extend(
                item for item in entities
                if isinstance(item, sensor.MammotionLastDetailUpdateSensor)
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

    async def test_standby_without_dock_evidence_remains_unmapped(self) -> None:
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
            self.assertIsNone(mower.activity)

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
        await refresh.async_press()
        self.assertEqual(self.client.actions, [])
        self.assertGreater(len(self.client.plan_calls), before)

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
