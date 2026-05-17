"""Pydantic models for O'Reilly Learning API responses."""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

SearchField = Literal["title", "publishers", "authors", "isbn"]
SearchSort = Literal[
    "popularity",
    "date_added",
    "publication_date",
    "average_rating",
    "title",
    "duration",
    "relevance",
]
SearchSortOrder = Literal["desc", "asc"]


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

    results: list[SearchResult] = Field(default_factory=list[SearchResult])
    total: int = 0
    page: int = 0


class BookMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    ourn: str
    identifier: str
    isbn: str | None = None
    title: str = Field(validation_alias=AliasChoices("title", "name"))
    language: str | None = None
    publication_date: str | None = None
    version: str = Field(validation_alias=AliasChoices("version", "last_modified_time"))
    authors: list[str] = Field(default_factory=list)
    publishers: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _extract_people(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        normalized = cast("dict[str, Any]", data)
        if "authors" not in normalized:
            talent = cast("dict[str, Any]", normalized.get("talent"))
            contributors = cast("list[dict[str, Any]]", talent.get("contributors", []))
            normalized["authors"] = [
                contributor["name"]
                for contributor in contributors
                if contributor.get("contributor_type") == "author"
                and isinstance(contributor.get("name"), str)
            ]
        return normalized

    @field_validator("publishers", mode="before")
    @classmethod
    def _publisher_names(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []

        normalized = cast("list[dict[str, Any]]", value)

        names: list[str] = []
        for item in normalized:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item.get("name"), str):
                names.append(item["name"])
        return names

    @field_validator("version", mode="before")
    @classmethod
    def _string_version(cls, value: object) -> str:
        return str(value)


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
    results: list[FilesManifestItem] = Field(default_factory=list[FilesManifestItem])
