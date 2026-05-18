"""Filesystem integrity helpers for downloaded snapshot files."""

from __future__ import annotations

import hashlib
import stat
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from extro.app.exceptions import ExtroError
from extro.downloads.paths import snapshot_file_path

if TYPE_CHECKING:
    from pathlib import Path

    from extro.storage.models import BookFile, BookSnapshot

_HASH_CHUNK_SIZE: Final = 1024 * 1024
_WRITE_BITS: Final = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


class IntegrityState(StrEnum):
    """Current local integrity state for one downloaded file."""

    OK = "ok"
    CHANGED = "changed"
    MISSING = "missing"
    WRITABLE = "writable"
    UNVERIFIED = "unverified"
    ERROR = "error"


@dataclass(frozen=True)
class FileIntegrityResult:
    """Verification result for one database file row."""

    file: BookFile
    state: IntegrityState
    path: Path | None
    expected_sha256: str | None
    actual_sha256: str | None
    read_only: bool | None
    error: str | None = None


@dataclass(frozen=True)
class SnapshotIntegritySummary:
    """Verification summary for one snapshot."""

    snapshot: BookSnapshot
    results: list[FileIntegrityResult]

    @property
    def state(self) -> IntegrityState:
        return summarize_integrity_state(self.results)

    @property
    def ok(self) -> bool:
        return self.results != [] and self.state == IntegrityState.OK


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_read_only(path: Path) -> None:
    path.chmod(path.stat().st_mode & ~_WRITE_BITS)


def is_read_only(path: Path) -> bool:
    return not path.stat().st_mode & _WRITE_BITS


def verify_file(snapshot: BookSnapshot, file: BookFile) -> FileIntegrityResult:
    expected_sha256 = file.content_sha256
    try:
        path = snapshot_file_path(snapshot, file.full_path)
    except ExtroError as exc:
        return FileIntegrityResult(
            file=file,
            state=IntegrityState.ERROR,
            path=None,
            expected_sha256=expected_sha256,
            actual_sha256=None,
            read_only=None,
            error=str(exc),
        )

    if not path.is_file():
        return FileIntegrityResult(
            file=file,
            state=IntegrityState.MISSING,
            path=path,
            expected_sha256=expected_sha256,
            actual_sha256=None,
            read_only=None,
        )

    try:
        read_only = is_read_only(path)
    except OSError as exc:
        return FileIntegrityResult(
            file=file,
            state=IntegrityState.ERROR,
            path=path,
            expected_sha256=expected_sha256,
            actual_sha256=None,
            read_only=None,
            error=str(exc),
        )

    if expected_sha256 is None:
        return FileIntegrityResult(
            file=file,
            state=IntegrityState.UNVERIFIED,
            path=path,
            expected_sha256=None,
            actual_sha256=None,
            read_only=read_only,
        )

    try:
        actual_sha256 = hash_file(path)
    except OSError as exc:
        return FileIntegrityResult(
            file=file,
            state=IntegrityState.ERROR,
            path=path,
            expected_sha256=expected_sha256,
            actual_sha256=None,
            read_only=read_only,
            error=str(exc),
        )

    if actual_sha256 != expected_sha256:
        state = IntegrityState.CHANGED
    elif not read_only:
        state = IntegrityState.WRITABLE
    else:
        state = IntegrityState.OK
    return FileIntegrityResult(
        file=file,
        state=state,
        path=path,
        expected_sha256=expected_sha256,
        actual_sha256=actual_sha256,
        read_only=read_only,
    )


def verify_snapshot(snapshot: BookSnapshot) -> SnapshotIntegritySummary:
    return SnapshotIntegritySummary(
        snapshot=snapshot,
        results=[verify_file(snapshot, file) for file in snapshot.files],
    )


def summarize_integrity_state(
    results: list[FileIntegrityResult],
) -> IntegrityState:
    if not results:
        return IntegrityState.UNVERIFIED
    for state in (
        IntegrityState.CHANGED,
        IntegrityState.MISSING,
        IntegrityState.WRITABLE,
        IntegrityState.ERROR,
        IntegrityState.UNVERIFIED,
    ):
        if any(result.state == state for result in results):
            return state
    return IntegrityState.OK
