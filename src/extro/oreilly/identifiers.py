"""Helpers for normalizing O'Reilly book identifiers."""

from __future__ import annotations


def normalize_book_identifier(value: str) -> str:
    cleaned = value.strip().rstrip("/")
    if not cleaned:
        msg = "Book identifier cannot be empty."
        raise ValueError(msg)

    marker = "urn:orm:book:"
    if marker in cleaned:
        return cleaned.split(marker, maxsplit=1)[1].split("/", maxsplit=1)[0]

    return cleaned.rsplit("/", maxsplit=1)[-1]
