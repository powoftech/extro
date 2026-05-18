from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import platformdirs

from extro.app.version import APP_NAME

_SAFE_TIMESTAMP_RE: Final = re.compile(r"[^A-Za-z0-9_.-]+")
_SAFE_EXPORT_STEM_RE: Final = re.compile(r"[^A-Za-z0-9_.-]+")


def user_data_dir_path() -> Path:
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))


def user_data_dir() -> Path:
    path = user_data_dir_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return user_data_dir() / "extro.db"


def downloads_dir() -> Path:
    path = user_data_dir() / "downloads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def exports_dir() -> Path:
    path = user_data_dir() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_snapshot_name(version: str) -> str:
    return _SAFE_TIMESTAMP_RE.sub("_", version).strip("._") or "unknown"


def _normalize_export_stem(value: str) -> str:
    normalized = re.sub(r"\s+", "_", value.casefold())
    cleaned = _SAFE_EXPORT_STEM_RE.sub("_", normalized)
    return re.sub(r"_+", "_", cleaned).strip("._-")


def safe_export_stem(value: str, *, fallback: str) -> str:
    cleaned = _normalize_export_stem(value)
    if cleaned:
        return cleaned

    fallback_cleaned = _normalize_export_stem(fallback)
    return fallback_cleaned or "unknown"


def export_file_stem(title: str, snapshot_version: str, *, fallback: str) -> str:
    return (
        f"{safe_export_stem(title, fallback=fallback)}-"
        f"{safe_snapshot_name(snapshot_version)}"
    )


def export_file_path(
    title: str,
    snapshot_version: str,
    *,
    extension: str,
    fallback: str,
) -> Path:
    suffix = extension.lstrip(".")
    if not suffix:
        msg = "Export file extension must not be empty."
        raise ValueError(msg)

    return exports_dir() / (
        f"{export_file_stem(title, snapshot_version, fallback=fallback)}.{suffix}"
    )
