"""Shared status queries and filesystem checks for downloaded books."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from extro.app.exceptions import ExtroError
from extro.app.paths import downloads_dir
from extro.downloads.integrity import IntegrityState, verify_snapshot
from extro.downloads.paths import snapshot_file_path
from extro.oreilly.identifiers import normalize_book_identifier
from extro.storage.models import Book, BookSnapshot

_BYTES_PER_UNIT: Final = 1024


@dataclass(frozen=True)
class BookStatusSummary:
    """Computed status for one book in the summary table."""

    book: Book
    snapshot_count: int
    local_snapshot_count: int
    local_path_state: str
    latest_snapshot: BookSnapshot | None
    latest_integrity_state: IntegrityState | None


@dataclass(frozen=True)
class SnapshotStatusDetail:
    """Computed local status for one database snapshot."""

    snapshot: BookSnapshot
    directory_exists: bool
    local_file_count: int
    db_file_count: int
    integrity_state: IntegrityState


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < _BYTES_PER_UNIT or unit == "GiB":
            if unit == "B":
                return f"{value} B"
            return f"{size:.1f} {unit}"
        size /= _BYTES_PER_UNIT
    return f"{value} B"


def format_progress(snapshot: BookSnapshot | None) -> str:
    if snapshot is None:
        return "-"
    files = f"{snapshot.completed_files}/{snapshot.total_files} files"
    bytes_ = (
        f"{format_bytes(snapshot.downloaded_bytes)}/"
        f"{format_bytes(snapshot.total_bytes)}"
    )
    return f"{files}, {bytes_}"


def format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "-"


def latest_snapshot(book: Book) -> BookSnapshot | None:
    if not book.snapshots:
        return None
    return max(book.snapshots, key=lambda snapshot: snapshot.version)


def snapshot_path_exists(snapshot: BookSnapshot) -> bool:
    return Path(snapshot.snapshot_path).is_dir()


def local_path_state(snapshots: list[BookSnapshot]) -> str:
    if not snapshots:
        return "none"
    existing = sum(1 for snapshot in snapshots if snapshot_path_exists(snapshot))
    if existing == len(snapshots):
        return "yes"
    if existing == 0:
        return "no"
    return "partial"


def local_snapshot_dir_count(book: Book) -> int:
    book_dir = downloads_dir() / book.identifier
    if not book_dir.is_dir():
        return 0
    return sum(1 for path in book_dir.iterdir() if path.is_dir())


def book_summary(book: Book) -> BookStatusSummary:
    snapshots = list(book.snapshots)
    latest = latest_snapshot(book)
    return BookStatusSummary(
        book=book,
        snapshot_count=len(snapshots),
        local_snapshot_count=local_snapshot_dir_count(book),
        local_path_state=local_path_state(snapshots),
        latest_snapshot=latest,
        latest_integrity_state=verify_snapshot(latest).state if latest else None,
    )


def list_book_summaries(
    session: Session,
    *,
    limit: int,
    page: int,
) -> tuple[list[BookStatusSummary], int]:
    """Return a paged list of book status summaries and the total book count."""
    if limit < 1:
        msg = "Limit must be at least 1."
        raise ValueError(msg)
    if page < 1:
        msg = "Page must be at least 1."
        raise ValueError(msg)

    total = session.scalar(select(func.count()).select_from(Book)) or 0
    stmt: Select[tuple[Book]] = (
        select(Book)
        .options(selectinload(Book.snapshots).selectinload(BookSnapshot.files))
        .order_by(Book.updated_at.desc(), Book.identifier.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    books = list(session.scalars(stmt).all())
    return [book_summary(book) for book in books], total


def find_book(session: Session, book_identifier: str) -> Book | None:
    """Find a book using the same identifier forms accepted by download."""
    identifier = normalize_book_identifier(book_identifier)
    stmt: Select[tuple[Book]] = (
        select(Book)
        .options(selectinload(Book.snapshots).selectinload(BookSnapshot.files))
        .where(
            or_(
                Book.identifier == identifier,
                Book.ourn == f"urn:orm:book:{identifier}",
            )
        )
    )
    return session.scalars(stmt).one_or_none()


def local_file_count(snapshot: BookSnapshot) -> int:
    count = 0
    for file in snapshot.files:
        try:
            path = snapshot_file_path(snapshot, file.full_path)
        except ExtroError:
            continue
        if path.is_file():
            count += 1
    return count


def snapshot_details(book: Book) -> list[SnapshotStatusDetail]:
    """Return filesystem detail for all snapshots on a book."""
    snapshots = sorted(
        book.snapshots,
        key=lambda snapshot: snapshot.version,
        reverse=True,
    )
    return [
        SnapshotStatusDetail(
            snapshot=snapshot,
            directory_exists=snapshot_path_exists(snapshot),
            local_file_count=local_file_count(snapshot),
            db_file_count=len(snapshot.files),
            integrity_state=verify_snapshot(snapshot).state,
        )
        for snapshot in snapshots
    ]
