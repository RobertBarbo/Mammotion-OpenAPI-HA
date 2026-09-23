"""Conservative polling of optional documented read-only mower data."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api.client import MammotionApiClient
from .api.extended_models import (
    DeviceErrorCodePage,
    WorkParameters,
    WorkReportDetail,
    WorkReportPage,
    WorkReportSummary,
)
from .const import DOMAIN, RTK_STATION_MODEL
from .coordinator import MammotionDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
_READ_INTERVAL = timedelta(hours=1)
_MAX_CONCURRENT_MOWERS = 2
_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class ReadOnlySnapshot:
    """Optional data; missing values never block basic mower integration."""

    work_parameters: WorkParameters | None = None
    report_summary: WorkReportSummary | None = None
    report_page: WorkReportPage | None = None
    report_detail: WorkReportDetail | None = None
    error_codes: DeviceErrorCodePage | None = None
    last_successful_update: datetime | None = None


class MammotionReadOnlyCoordinator(DataUpdateCoordinator[dict[str, ReadOnlySnapshot]]):
    """Fetch history/parameters hourly, separate from five-minute state polls."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: MammotionApiClient,
        mower_coordinator: MammotionDataUpdateCoordinator,
    ) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=f"{DOMAIN}_read_only",
            update_interval=_READ_INTERVAL, always_update=False,
        )
        self.client = client
        self.mower_coordinator = mower_coordinator

    async def _async_update_data(self) -> dict[str, ReadOnlySnapshot]:
        current_mowers = self.mower_coordinator.data or {}
        limit = asyncio.Semaphore(_MAX_CONCURRENT_MOWERS)

        async def fetch_mower(device_id: str) -> tuple[str, ReadOnlySnapshot]:
            async with limit:
                params = await _optional(self.client.get_work_parameters(device_id))
                summary = await _optional(self.client.get_work_report_summary(device_id))
                reports = await _optional(self.client.search_work_reports(device_id))
                errors = await _optional(self.client.search_error_codes(device_id))
                detail = None
                if reports is not None:
                    # Work IDs are used only as returned; no ordering is assumed.
                    first_with_id = next(
                        (record for record in reports.records if record.work_id), None
                    )
                    if first_with_id is not None:
                        detail = await _optional(
                            self.client.get_work_report(device_id, first_with_id.work_id)
                        )
                successful = any(
                    value is not None for value in (params, summary, reports, errors, detail)
                )
                return device_id, ReadOnlySnapshot(
                    work_parameters=params,
                    report_summary=summary,
                    report_page=reports,
                    report_detail=detail,
                    error_codes=errors,
                    last_successful_update=(
                        datetime.now(timezone.utc) if successful else None
                    ),
                )

        results = await asyncio.gather(
            *(
                fetch_mower(device_id)
                for device_id, snapshot in current_mowers.items()
                if snapshot.mower.model != RTK_STATION_MODEL
            )
        )
        return dict(results)


async def _optional(awaitable: Awaitable[_T]) -> _T | None:
    """An unsupported or failed optional endpoint must not disable mowers."""
    try:
        return await awaitable
    except Exception as err:
        # Keep core mower setup usable even if an optional endpoint behaves
        # unexpectedly. Never log the exception text or a remote response.
        _LOGGER.debug("Optional Mammotion read failed (%s)", type(err).__name__)
        return None
