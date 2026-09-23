"""Account-wide polling of mower data from the official Open API."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api.client import MammotionApiClient
from .api.exceptions import MammotionAuthenticationError, MammotionError
from .api.models import Mower, MowerPlan
from .const import (
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
    MAX_CONCURRENT_DETAILS,
    RTK_STATION_MODEL,
    UPDATE_INTERVAL_CHOICES,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MowerSnapshot:
    """Mower data and whether its latest detail request succeeded.

    A failed detail request retains the last known detail, or uses the current
    list response if no earlier detail exists. Future device kinds can have
    their own snapshot type when Mammotion documents a type discriminator.
    """

    mower: Mower
    detail_available: bool
    plans: tuple[MowerPlan, ...] = ()
    last_detail_update: datetime | None = None


class MammotionDataUpdateCoordinator(DataUpdateCoordinator[dict[str, MowerSnapshot]]):
    """Refresh every mower attached to one credential set."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: MammotionApiClient
    ) -> None:
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_MINUTES)
        if interval not in UPDATE_INTERVAL_CHOICES:
            interval = DEFAULT_UPDATE_INTERVAL_MINUTES
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval),
            always_update=False,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, MowerSnapshot]:
        try:
            listed = await self.client.get_mowers()
        except MammotionAuthenticationError:
            raise ConfigEntryAuthFailed("Mammotion authentication failed") from None
        except MammotionError:
            raise UpdateFailed("Unable to retrieve Mammotion devices") from None

        # The mower list is the only confirmed discovery source. The observed
        # RTK model remains a device but has no mower plans or controls.
        mowers_by_id = {mower.id: mower for mower in listed}
        limit = asyncio.Semaphore(MAX_CONCURRENT_DETAILS)

        async def fetch_device(
            mower_id: str, listed_mower: Mower
        ) -> tuple[Mower, tuple[MowerPlan, ...] | None]:
            async with limit:
                detail = await self.client.get_mower(mower_id)
                if (detail.model or listed_mower.model) == RTK_STATION_MODEL:
                    return detail, ()
                try:
                    plans = await self.client.get_plans(mower_id)
                except MammotionAuthenticationError:
                    raise
                except MammotionError:
                    plans = None
                return detail, plans

        results = await asyncio.gather(
            *(fetch_device(mower_id, mower) for mower_id, mower in mowers_by_id.items()),
            return_exceptions=True,
        )

        previous = self.data or {}
        current: dict[str, MowerSnapshot] = {}
        refreshed_at = datetime.now(timezone.utc)
        for (mower_id, listed_mower), result in zip(mowers_by_id.items(), results):
            if isinstance(result, MammotionAuthenticationError):
                raise ConfigEntryAuthFailed("Mammotion authentication failed") from None
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, MammotionError):
                cached = previous.get(mower_id)
                current[mower_id] = MowerSnapshot(
                    mower=_merge_list_fields(listed_mower, cached.mower) if cached else listed_mower,
                    detail_available=False,
                    plans=cached.plans if cached else (),
                    last_detail_update=cached.last_detail_update if cached else None,
                )
                continue
            if isinstance(result, BaseException):
                raise UpdateFailed("Unexpected Mammotion detail error") from None
            detail, plans = result
            if detail.id != mower_id:
                raise UpdateFailed("Mammotion detail returned a mismatched device ID")
            cached = previous.get(mower_id)
            current[mower_id] = MowerSnapshot(
                mower=_merge_list_fields(listed_mower, detail),
                detail_available=True,
                plans=plans if plans is not None else (cached.plans if cached else ()),
                last_detail_update=refreshed_at,
            )

        return current


def _merge_list_fields(listed: Mower, detail: Mower) -> Mower:
    """Keep identity and metadata from the current list if detail omits them."""
    return replace(
        detail,
        name=detail.name if detail.name is not None else listed.name,
        nickname=detail.nickname if detail.nickname is not None else listed.nickname,
        model=detail.model if detail.model is not None else listed.model,
        icon=detail.icon if detail.icon is not None else listed.icon,
        online=listed.online if listed.online is not None else detail.online,
    )
