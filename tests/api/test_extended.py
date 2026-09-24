"""Mocked tests for additional, documented read-only Open API endpoints."""

from __future__ import annotations

import unittest

from custom_components.mammotion_openapi.api.client import API_BASE_URL, MammotionApiClient
from custom_components.mammotion_openapi.api.exceptions import (
    MammotionApiError,
    MammotionMalformedResponseError,
)
from tests.api.test_client import FakeSession, _Response, _token


class ExtendedApiTest(unittest.IsolatedAsyncioTestCase):
    def _client(self, *responses: _Response) -> tuple[MammotionApiClient, FakeSession]:
        session = FakeSession([_token()], list(responses))
        client = MammotionApiClient(session, "test-client-id", "test-client-secret")
        return client, session  # type: ignore[arg-type]

    async def test_work_parameters_accept_documented_success_code(self) -> None:
        client, session = self._client(_Response(200, {"code": 200, "data": {
            "knifeHeight": 35, "speed": 60, "channelWidth": 25,
            "rideBoundaryDistance": 0.2, "visualHashs": ["fake-hash"],
        }}))

        params = await client.get_work_parameters("mower-a")

        self.assertEqual((params.knife_height, params.speed), (35, 60))
        self.assertEqual(params.ride_boundary_distance, 0.2)
        self.assertNotIn("fake-hash", repr(params))
        self.assertEqual(session.requests[0]["method"], "GET")
        self.assertEqual(
            session.requests[0]["url"],
            f"{API_BASE_URL}/v1/mower/mower-a/work-params",
        )

    async def test_search_work_reports_uses_documented_query(self) -> None:
        client, session = self._client(_Response(200, {"code": 0, "data": {
            "records": [{
                "workId": "work-a", "endWorkTime": 1760000000000,
                "workResult": 5, "workProgress": 100, "workArea": 82.5,
                "workTimeUsed": 3600,
            }],
            "total": 1, "pageNumber": 2, "pageSize": 5, "pages": 1,
        }}))

        page = await client.search_work_reports(
            "mower-a", page_number=2, page_size=5,
            end_work_time_start=1750000000000, work_result=5,
        )

        self.assertEqual(page.total, 1)
        self.assertEqual(page.records[0].work_id, "work-a")
        self.assertEqual(page.records[0].work_area, 82.5)
        self.assertEqual(session.requests[0]["method"], "POST")
        self.assertEqual(
            session.requests[0]["url"], f"{API_BASE_URL}/v1/mower/work-reports/search"
        )
        self.assertEqual(session.requests[0]["json"], {
            "deviceId": "mower-a", "pageNumber": 2, "pageSize": 5,
            "endWorkTimeStart": 1750000000000, "workResult": 5,
        })

    async def test_empty_work_report_page(self) -> None:
        client, _ = self._client(_Response(200, {"code": 0, "data": {
            "records": [], "total": 0,
        }}))

        page = await client.search_work_reports("mower-a")

        self.assertEqual(page.records, ())
        self.assertEqual(page.total, 0)

    async def test_work_report_summary(self) -> None:
        client, session = self._client(_Response(200, {"code": 200, "data": {
            "saveTime": 90, "carbonReduction": 12.5,
            "workCount": 3, "totalWorkArea": 450.25,
        }}))

        summary = await client.get_work_report_summary("mower-a")

        self.assertEqual(summary.work_count, 3)
        self.assertEqual(summary.total_work_area, 450.25)
        self.assertEqual(session.requests[0]["json"], {
            "deviceId": "mower-a", "pageNumber": 1, "pageSize": 10,
        })

    async def test_work_report_detail_does_not_show_signed_map_url_in_repr(self) -> None:
        client, session = self._client(_Response(200, {"code": 200, "data": {
            "workArea": 82.5, "workTimeUsed": 3600,
            "energyConsume": 120.5,
            "workProcess": [{"timeStamp": 1760000000000, "eventCode": 12}],
            "workParam": {"knifeHeight": 35},
            "mapFilePath": "https://example.invalid/map?signature=redacted-test-value",
        }}))

        detail = await client.get_work_report("mower-a", "work/a")

        self.assertEqual(detail.energy_consume, 120.5)
        self.assertEqual(detail.work_process[0].event_code, 12)
        self.assertEqual(detail.work_param.knife_height if detail.work_param else None, 35)
        self.assertNotIn("signature", repr(detail))
        self.assertEqual(
            session.requests[0]["url"],
            f"{API_BASE_URL}/v1/mower/mower-a/work-reports/work%2Fa",
        )

    async def test_error_code_search_does_not_clear_faults(self) -> None:
        client, session = self._client(_Response(200, {"code": 200, "data": {
            "records": [{
                "code": 123, "implication": "Sanitized test fault",
                "solution": "Inspect the device", "gmtCreate": 1760000000000,
                "faultLevel": 2, "priority": 2,
                "imageList": [{"url": "https://example.invalid/private"}],
            }],
            "total": 1, "hasMore": False,
        }}))

        page = await client.search_error_codes(
            "mower-a", page_number=1, page_size=5, start_date="2026-09-01"
        )

        self.assertEqual(page.records[0].code, 123)
        self.assertEqual(page.records[0].fault_level, 2)
        self.assertNotIn("private", repr(page))
        self.assertEqual(session.requests[0]["json"], {
            "deviceId": "mower-a", "pageNumber": 1,
            "pageSize": 5, "startDate": "2026-09-01",
        })
        self.assertEqual(
            session.requests[0]["url"],
            f"{API_BASE_URL}/v1/mower/error-codes/search",
        )

    async def test_rejects_non_success_code_and_malformed_data(self) -> None:
        client, _ = self._client(_Response(200, {"code": 402, "data": {}}))
        with self.assertRaises(MammotionApiError):
            await client.get_work_parameters("mower-a")

        client, _ = self._client(_Response(200, {"code": 200, "data": []}))
        with self.assertRaises(MammotionMalformedResponseError):
            await client.get_work_report_summary("mower-a")

        client, _ = self._client(_Response(200, {"code": 200, "data": {
            "records": {"not": "a list"},
        }}))
        with self.assertRaises(MammotionMalformedResponseError):
            await client.search_error_codes("mower-a")

    async def test_existing_endpoint_accepts_both_success_codes(self) -> None:
        for code in (0, 200):
            with self.subTest(code=code):
                client, _ = self._client(_Response(200, {"code": code, "data": []}))
                self.assertEqual(await client.get_mowers(), ())

    async def test_invalid_pagination_is_rejected_before_network(self) -> None:
        client, session = self._client()
        with self.assertRaises(ValueError):
            await client.search_work_reports("mower-a", page_number=0)
        with self.assertRaises(ValueError):
            await client.search_error_codes("mower-a", page_size=0)
        self.assertEqual(session.requests, [])
