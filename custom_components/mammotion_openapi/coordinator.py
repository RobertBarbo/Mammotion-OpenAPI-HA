"""Account-wide polling of mower data from the official Open API."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api.client import MammotionApiClient
from .api.exceptions import MammotionAuthenticationError, MammotionError
from .api.models import Mower
from .const import DOMAIN, MAX_CONCURRENT_DETAILS, UPDATE_INTERVAL

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


class MammotionDataUpdateCoordinator(DataUpdateCoordinator[dict[str, MowerSnapshot]]):
    """Refresh every mower attached to one credential set."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: MammotionApiClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
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

        # The /v1/mowers endpoint is the only confirmed discovery source. It
        # does not expose a documented device-type field, so model/name based
        # filtering would risk excluding valid mowers. No mower entities are
        # created in this phase; future platforms must gate mower features.
        mowers_by_id = {mower.id: mower for mower in listed}
        limit = asyncio.Semaphore(MAX_CONCURRENT_DETAILS)

        async def fetch_detail(mower_id: str) -> Mower:
            async with limit:
                return await self.client.get_mower(mower_id)

        results = await asyncio.gather(
            *(fetch_detail(mower_id) for mower_id in mowers_by_id),
            return_exceptions=True,
        )

        previous = self.data or {}
        current: dict[str, MowerSnapshot] = {}
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
                )
                continue
            if isinstance(result, BaseException):
                raise UpdateFailed("Unexpected Mammotion detail error") from None
            if result.id != mower_id:
                raise UpdateFailed("Mammotion detail returned a mismatched device ID")
            current[mower_id] = MowerSnapshot(
                mower=_merge_list_fields(listed_mower, result), detail_available=True
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
