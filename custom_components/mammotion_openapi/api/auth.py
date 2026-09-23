"""OAuth client-credentials token management for Mammotion Open API."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import aiohttp

from .exceptions import (
    MammotionApiError,
    MammotionAuthenticationError,
    MammotionMalformedResponseError,
    MammotionTransportError,
)

TOKEN_URL = "https://id.mammotion.com/oauth2/token"
_EXPIRY_SKEW_SECONDS = 30


@dataclass(frozen=True, slots=True)
class _AccessToken:
    value: str
    expires_at: float | None


class MammotionAuth:
    """Acquire and cache OAuth access tokens using an injected session."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        client_secret: str,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session = session
        self._client_id = client_id
        self._client_secret = client_secret
        self._clock = clock
        self._token: _AccessToken | None = None
        self._lock = asyncio.Lock()

    async def async_get_access_token(self) -> str:
        """Return a usable token, obtaining a new one when needed."""
        if self._has_usable_token():
            return self._token.value  # type: ignore[union-attr]

        async with self._lock:
            if self._has_usable_token():
                return self._token.value  # type: ignore[union-attr]
            self._token = await self._async_request_client_credentials_token()
            return self._token.value

    def async_invalidate_token(self) -> None:
        """Discard a token after an authorization failure."""
        self._token = None

    def _has_usable_token(self) -> bool:
        if self._token is None:
            return False
        return self._token.expires_at is None or self._clock() < self._token.expires_at

    async def _async_request_client_credentials_token(self) -> _AccessToken:
        form = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        response = await self._async_request_token(form)
        token_data = _unwrap_token_response(response)
        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise MammotionAuthenticationError("Token response did not include an access token")

        expires_at = None
        expires_in = token_data.get("expires_in")
        if expires_in is not None:
            if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float)):
                raise MammotionMalformedResponseError("Token expires_in must be a number")
            expires_at = self._clock() + max(0, float(expires_in) - _EXPIRY_SKEW_SECONDS)
        return _AccessToken(value=access_token, expires_at=expires_at)

    async def _async_request_token(self, form: Mapping[str, str]) -> Mapping[str, Any]:
        try:
            async with self._session.post(TOKEN_URL, data=form) as response:
                if response.status in (401, 403):
                    raise MammotionAuthenticationError("Mammotion rejected the client credentials")
                if response.status < 200 or response.status >= 300:
                    raise MammotionTransportError(f"Token endpoint returned HTTP {response.status}")
                try:
                    payload = await response.json(content_type=None)
                except (aiohttp.ClientError, ValueError, TypeError) as err:
                    raise MammotionMalformedResponseError("Token endpoint returned invalid JSON") from err
        except MammotionAuthenticationError:
            raise
        except MammotionTransportError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise MammotionTransportError("Unable to reach Mammotion token endpoint") from err

        if not isinstance(payload, Mapping):
            raise MammotionMalformedResponseError("Token endpoint response must be an object")
        return payload


def _unwrap_token_response(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Handle OAuth token JSON and a possible Mammotion-style envelope."""
    if "code" not in payload:
        if "error" in payload:
            raise MammotionAuthenticationError("Mammotion rejected the token request")
        return payload

    code = payload.get("code")
    if isinstance(code, bool) or not isinstance(code, int):
        raise MammotionMalformedResponseError("Token response code must be an integer")
    if code != 0:
        message = payload.get("msg")
        raise MammotionAuthenticationError(
            str(MammotionApiError(code, message if isinstance(message, str) else None))
        )
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise MammotionMalformedResponseError("Successful token response data must be an object")
    return data
