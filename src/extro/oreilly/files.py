"""Authenticated file access for O'Reilly book assets."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, cast

import curl_cffi

from extro.oreilly.http import make_session
from extro.platform.cookies import (
    oreilly_cookies_from_profile,
    refresh_cookies_via_firefox,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

_AUTH_FAILURE_STATUS_CODES = {401, 403}


class _SessionResponse(curl_cffi.Response):
    def raise_for_status(self) -> None: ...


class _JsonResponse(Protocol):
    url: str

    def json(self) -> dict[str, str]: ...


class CookieFileClient:
    """HTTP client that authenticates using Firefox cookies."""

    def __init__(self, profile_dir: Path) -> None:
        self._profile_dir = profile_dir
        self._session = self._new_session()

    def get_json(self, url: str) -> dict[str, Any]:
        response = cast("_JsonResponse", self._get_with_refresh(url))
        return response.json()

    def get_bytes(self, url: str) -> curl_cffi.Response:
        return self._get_with_refresh(url)

    def _get_with_refresh(self, url: str) -> curl_cffi.Response:
        response = cast("_SessionResponse", self._session.get(url))
        if response.status_code not in _AUTH_FAILURE_STATUS_CODES:
            response.raise_for_status()
            return response

        logger.debug("Auth failure for %s; refreshing Firefox cookies.", url)
        refresh_cookies_via_firefox(self._profile_dir)
        self._session = self._new_session()
        response = cast("_SessionResponse", self._session.get(url))
        response.raise_for_status()
        return response

    def _new_session(self) -> curl_cffi.Session[curl_cffi.Response]:
        cookies = oreilly_cookies_from_profile(self._profile_dir)
        return make_session(cookies=cookies)
