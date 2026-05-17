"""Path helpers for local downloaded snapshots."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from extro.app.exceptions import ExtroError

if TYPE_CHECKING:
    from extro.storage.models import BookSnapshot


def snapshot_file_path(snapshot: BookSnapshot, remote_full_path: str) -> Path:
    relative = PurePosixPath(remote_full_path)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        msg = f"Unsafe remote file path: {remote_full_path}"
        raise ExtroError(msg)
    root = Path(snapshot.snapshot_path) / "files"
    candidate = root.joinpath(*relative.parts).resolve()
    root_resolved = root.resolve()
    if root_resolved not in candidate.parents and candidate != root_resolved:
        msg = f"Unsafe remote file path: {remote_full_path}"
        raise ExtroError(msg)
    return candidate
