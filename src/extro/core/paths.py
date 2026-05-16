from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import platformdirs

_APP_NAME: Final = "extro"
_SAFE_TIMESTAMP_RE: Final = re.compile(r"[^A-Za-z0-9_.-]+")


def user_data_dir() -> Path:
    path = Path(platformdirs.user_data_dir(_APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return user_data_dir() / "extro.db"


def downloads_dir() -> Path:
    path = user_data_dir() / "downloads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_snapshot_name(version: str) -> str:
    return _SAFE_TIMESTAMP_RE.sub("_", version).strip("._") or "unknown"
