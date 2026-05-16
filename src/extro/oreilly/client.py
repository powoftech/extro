"""Unauthenticated O'Reilly Learning API client."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Protocol, cast

import curl_cffi

from extro.oreilly.http import BROWSER_HEADERS
from extro.oreilly.identifiers import normalize_book_identifier
from extro.oreilly.schemas import (
    BookMetadata,
    SearchField,
    SearchResponse,
    SearchSort,
    SearchSortOrder,
)

API_BASE_URL = "https://learning.oreilly.com/api/v2"
SEARCH_LIMIT_MIN = 1
SEARCH_LIMIT_MAX = 200
_DEFAULT_DELAY_MIN: float = 0.75
_DEFAULT_DELAY_MAX: float = 1.0


@dataclass(slots=True)
class SearchParams:
    field: SearchField = "title"
    sort: SearchSort = "popularity"
    order: SearchSortOrder = "desc"
    limit: int = 10
    page: int = 1


class _JsonResponse(Protocol):
    url: str

    def raise_for_status(self) -> None: ...
    def json(self) -> object: ...


class OreillyClient:
    """Unauthenticated client for the public O'Reilly Learning API.

    All endpoints accessed here (search, metadata, spine, files, TOC,
    chapters) are reachable without authentication cookies. File-download
    CDN URLs, by contrast, require session cookies and are handled by
    :class:`extro.oreilly.files.CookieFileClient`.
    """

    def __init__(
        self,
        *,
        base_url: str = API_BASE_URL,
        timeout: float = 30.0,
        delay_min: float = _DEFAULT_DELAY_MIN,
        delay_max: float = _DEFAULT_DELAY_MAX,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._delay_min = delay_min
        self._delay_max = delay_max

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
        # print(response.url)
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
        response = cast(
            "_JsonResponse",
            curl_cffi.get(
                url,
                params=params,
                headers=BROWSER_HEADERS,
                http_version="v2",
                allow_redirects=True,
                verify=True,
                impersonate="chrome146",
                timeout=self._timeout,
            ),
        )
        response.raise_for_status()
        return response.json()
