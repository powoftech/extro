from __future__ import annotations

import random
import time
from typing import Any, Literal

import curl_cffi
from pydantic import BaseModel, ConfigDict, Field
from rich import print

SearchField = Literal["title", "publishers", "authors", "isbn"]

API_BASE_URL = "https://learning.oreilly.com/api/v2"


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    archive_id: str
    ourn: str
    isbn: str | None = None
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


class OreillyClient:
    def __init__(
        self,
        *,
        base_url: str = API_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def search(self, keyword: str, *, field: SearchField = "title") -> SearchResponse:
        with curl_cffi.Session(
            # impersonate="chrome146",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Sec-Gpc": "1",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "Windows",
                "DNT": "1",
            },
            http_version="v2",
            allow_redirects=True,
            verify=True,
            timeout=self._timeout,
        ) as session:
            response = session.get(
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
            )
            response.raise_for_status()
            return SearchResponse.model_validate(response.json())

    def fetch_metadata(self, identifier: str) -> BookMetadata:
        book_id = normalize_book_identifier(identifier)
        data = self._get_json(f"{self._base_url}/epubs/urn:orm:book:{book_id}/")
        return BookMetadata.model_validate(data)

    def fetch_spine(self, metadata: BookMetadata) -> dict[str, Any]:
        return self._get_json(metadata.spine, params={"limit": "1000"})

    def fetch_files(self, metadata: BookMetadata) -> dict[str, Any]:
        return self._get_json(metadata.files, params={"limit": "10000"})

    def fetch_table_of_contents(self, metadata: BookMetadata) -> object:
        return self._get_json_or_list(metadata.table_of_contents)

    def fetch_chapters(self, metadata: BookMetadata) -> dict[str, Any]:
        return self._get_json(metadata.chapters, params={"limit": "1000"})

    def _get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        time.sleep(random.uniform(1, 2))
        response = curl_cffi.get(
            url,
            params=params,
            # impersonate="chrome146",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Sec-Gpc": "1",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "Windows",
                "DNT": "1",
            },
            http_version="v2",
            allow_redirects=True,
            verify=True,
            # akamai="1:65536;2:0;4:6291456;6:262144|15663105|0|m,a,s,p",
        )
        print(response.url)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            msg = f"Expected object response from {url}"
            raise TypeError(msg)
        return data

    def _get_json_or_list(self, url: str) -> object:
        response = curl_cffi.get(
            url,
            # impersonate="chrome146",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Sec-Gpc": "1",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "Windows",
                "DNT": "1",
            },
            http_version="v2",
            allow_redirects=True,
            verify=True,
            # akamai="1:65536;2:0;4:6291456;6:262144|15663105|0|m,a,s,p",
        )
        print(response.url)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, (dict, list)):
            msg = f"Expected object or array response from {url}"
            raise TypeError(msg)
        return data
