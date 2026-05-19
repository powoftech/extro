"""O'Reilly Learning API client."""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

import curl_cffi

from extro.app.exceptions import ConfigError
from extro.oreilly.http import BROWSER_HEADERS, make_session
from extro.oreilly.identifiers import normalize_book_identifier
from extro.oreilly.schemas import (
    BookMetadata,
    SearchField,
    SearchResponse,
    SearchSort,
    SearchSortOrder,
)
from extro.platform.cookies import (
    oreilly_cookies_from_profile,
    refresh_cookies_via_firefox,
)

if TYPE_CHECKING:
    from pathlib import Path

API_BASE_URL = "https://learning.oreilly.com/api/v2"
SEARCH_LIMIT_MIN = 1
SEARCH_LIMIT_MAX = 200
_DEFAULT_DELAY_MIN: float = 0.75
_DEFAULT_DELAY_MAX: float = 1.0
_AUTH_FAILURE_STATUS_CODES = {401, 403}

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchParams:
    field: SearchField = "title"
    sort: SearchSort = "popularity"
    order: SearchSortOrder = "desc"
    limit: int = 10
    page: int = 1


class _JsonResponse(Protocol):
    url: str
    status_code: int

    def raise_for_status(self) -> None: ...
    def json(self) -> object: ...


class _JsonSession(Protocol):
    def get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> _JsonResponse: ...


class OreillyClient:
    """Client for the O'Reilly Learning API.

    Search remains unauthenticated. Metadata and manifest endpoints use
    cookies from the configured Firefox profile because O'Reilly may require
    an active authenticated session for book-specific JSON.
    """

    def __init__(
        self,
        *,
        base_url: str = API_BASE_URL,
        timeout: float = 30.0,
        delay_min: float = _DEFAULT_DELAY_MIN,
        delay_max: float = _DEFAULT_DELAY_MAX,
        profile_dir: Path | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._delay_min = delay_min
        self._delay_max = delay_max
        self._profile_dir = profile_dir
        self._session: _JsonSession | None = None

    def search(
        self,
        keyword: str,
        *,
        params: SearchParams | None = None,
    ) -> SearchResponse:
        params = params or SearchParams()
        if params.limit < SEARCH_LIMIT_MIN:
            msg = f"Limit must be at least {SEARCH_LIMIT_MIN}."
            raise ValueError(msg)
        if params.limit > SEARCH_LIMIT_MAX:
            msg = f"Limit cannot exceed {SEARCH_LIMIT_MAX}."
            raise ValueError(msg)
        if params.page < 1:
            msg = "Page must be at least 1."
            raise ValueError(msg)

        response = cast(
            "_JsonResponse",
            curl_cffi.get(
                f"{self._base_url}/search/",
                params={
                    "formats": "book",
                    "languages": "en",
                    "include_facets": "false",
                    "field": params.field,
                    "query": keyword,
                    "sort": params.sort,
                    "order": params.order,
                    "limit": str(params.limit),
                    "page": str(params.page - 1),
                },
                headers=BROWSER_HEADERS,
                http_version="v2",
                allow_redirects=True,
                verify=True,
                impersonate="chrome146",
                timeout=self._timeout,
            ),
        )
        response.raise_for_status()
        data = response.json()
        return SearchResponse.model_validate(data)

    def fetch_metadata(self, identifier: str) -> BookMetadata:
        book_id = normalize_book_identifier(identifier)
        data = self._get_json(f"{self._base_url}/metadata/urn:orm:book:{book_id}/")
        return BookMetadata.model_validate(data)

    def fetch_spine(self, metadata: BookMetadata) -> object:
        return self._get_json(
            f"{self._base_url}/epubs/{metadata.ourn}/spine/",
            params={"limit": "1000"},
        )

    def fetch_files(self, metadata: BookMetadata) -> object:
        return self._get_json(
            f"{self._base_url}/epubs/{metadata.ourn}/files/",
            params={"limit": "10000"},
        )

    def fetch_table_of_contents(self, metadata: BookMetadata) -> object:
        return self._get_json(
            f"{self._base_url}/epubs/{metadata.ourn}/table-of-contents/",
        )

    def fetch_chapters(self, metadata: BookMetadata) -> object:
        return self._get_json(
            f"{self._base_url}/epub-chapters/",
            params={"epub_identifier": metadata.ourn, "limit": "1000"},
        )

    def _random_delay(self) -> None:
        time.sleep(secrets.SystemRandom().uniform(self._delay_min, self._delay_max))

    def _get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> object:
        self._random_delay()
        response = self._get_with_refresh(url, params=params)
        response.raise_for_status()
        return response.json()

    def _get_with_refresh(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> _JsonResponse:
        response = self._get_session().get(url, params=params)
        if response.status_code not in _AUTH_FAILURE_STATUS_CODES:
            return response

        if self._profile_dir is None:
            raise self._missing_profile_error()

        logger.debug("Auth failure for %s; refreshing Firefox cookies.", url)
        refresh_cookies_via_firefox(self._profile_dir)
        self._session = self._new_session()
        return self._get_session().get(url, params=params)

    def _get_session(self) -> _JsonSession:
        if self._session is None:
            self._session = self._new_session()
        return self._session

    def _new_session(self) -> _JsonSession:
        if self._profile_dir is None:
            raise self._missing_profile_error()

        cookies = oreilly_cookies_from_profile(self._profile_dir)
        return cast(
            "_JsonSession",
            make_session(cookies=cookies, timeout=self._timeout),
        )

    def _missing_profile_error(self) -> ConfigError:
        return ConfigError(
            "Run extro config before fetching O'Reilly book metadata so Firefox "
            "cookies can be read."
        )
