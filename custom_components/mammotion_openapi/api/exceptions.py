"""Exceptions raised by the Mammotion Open API client."""

from __future__ import annotations


class MammotionError(Exception):
    """Base error for the Mammotion Open API layer."""


class MammotionAuthenticationError(MammotionError):
    """Authentication or authorization failed."""


class MammotionTransportError(MammotionError):
    """A network failure, timeout, or non-authentication HTTP failure occurred."""


class MammotionMalformedResponseError(MammotionError):
    """The server response did not match the expected documented shape."""


class MammotionApiError(MammotionError):
    """The Mammotion API returned a non-zero envelope code."""

    def __init__(self, code: int, message: str | None = None) -> None:
        self.code = code
        self.message = message
        detail = f"Mammotion API returned code {code}"
        if message:
            detail = f"{detail}: {message}"
        super().__init__(detail)
