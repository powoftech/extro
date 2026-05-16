"""O'Reilly Learning API client and response models."""

from __future__ import annotations

import secrets
import time
from typing import Literal, Protocol, cast

import curl_cffi
from pydantic import BaseModel, ConfigDict, Field

from extro.core.http import BROWSER_HEADERS

SearchField = Literal["title", "publishers", "authors", "isbn"]

API_BASE_URL = "https://learning.oreilly.com/api/v2"


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    archive_id: str
    ourn: str
    isbn: str | None = None
    issued: str | None = None
    last_modified_time: str | None = None
    authors: list[str] = Field(default_factory=list)
    publishers: list[str] = Field(default_factory=list)
    language: str | None = None
    title: str
    web_url: str | None = None
    popularity: int | None = None


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[SearchResult] = Field(default_factory=list)
    total: int = 0


class BookMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    ourn: str
    identifier: str
    isbn: str | None = None
    title: str
    language: str | None = None
    issued: str
    last_modified_time: str
    spine: str
    files: str
    table_of_contents: str
    chapters: str


class FilesManifestItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    url: str
    full_path: str
    media_type: str | None = None
    file_size: int | None = None
    last_modified_time: str | None = None


class FilesManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    count: int
    next: str | None = None
    previous: str | None = None
    results: list[FilesManifestItem] = Field(default_factory=list)


def normalize_book_identifier(value: str) -> str:
    cleaned = value.strip().rstrip("/")
    if not cleaned:
        msg = "Book identifier cannot be empty."
        raise ValueError(msg)

    marker = "urn:orm:book:"
    if marker in cleaned:
        return cleaned.split(marker, maxsplit=1)[1].split("/", maxsplit=1)[0]

    return cleaned.rsplit("/", maxsplit=1)[-1]


_DEFAULT_DELAY_MIN: float = 0.75
_DEFAULT_DELAY_MAX: float = 1.0


class _JsonResponse(Protocol):
    url: str

    def raise_for_status(self) -> None: ...
    def json(self) -> dict[str, str] | list[dict[str, str]]: ...


class OreillyClient:
    """Unauthenticated client for the public O'Reilly Learning API.

    All endpoints accessed here (search, metadata, spine, files, TOC,
    chapters) are reachable without authentication cookies.  File-download
    CDN URLs, by contrast, require session cookies and are handled by
    :class:`extro.core.download.CookieFileClient`.
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

    def search(self, keyword: str, *, field: SearchField = "title") -> SearchResponse:
        response = cast(
            "_JsonResponse",
            curl_cffi.get(
                f"{self._base_url}/search/",
                params={
                    "formats": "book",
                    "languages": "en",
                    "include_facets": "false",
                    "field": field,
                    "query": keyword,
                    "sort": "popularity",
                    "order": "desc",
                    "limit": "10",
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
        data = self._get_json(f"{self._base_url}/epubs/urn:orm:book:{book_id}/")
        return BookMetadata.model_validate(data)

    def fetch_spine(self, metadata: BookMetadata) -> object:
        return self._get_json(metadata.spine, params={"limit": "1000"})

    def fetch_files(self, metadata: BookMetadata) -> object:
        return self._get_json(metadata.files, params={"limit": "10000"})

    def fetch_table_of_contents(self, metadata: BookMetadata) -> object:
        return self._get_json_or_list(metadata.table_of_contents)

    def fetch_chapters(self, metadata: BookMetadata) -> object:
        return self._get_json(metadata.chapters, params={"limit": "1000"})

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

    def _get_json_or_list(self, url: str) -> object:
        self._random_delay()
        response = cast(
            "_JsonResponse",
            curl_cffi.get(
                url,
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
