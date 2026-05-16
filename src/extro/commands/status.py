"""CLI commands for inspecting and deleting downloaded book snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from extro.core.api import normalize_book_identifier
from extro.core.database import session_scope, upgrade_database
from extro.core.download import snapshot_file_path
from extro.core.exceptions import ExtroError
from extro.core.models import Book, BookSnapshot
from extro.core.paths import downloads_dir

console = Console()
err_console = Console(stderr=True)
_BYTES_PER_UNIT: Final = 1024


@dataclass(frozen=True)
class BookStatusSummary:
    """Computed status for one book in the summary table."""

    book: Book
    snapshot_count: int
    local_snapshot_count: int
    local_path_state: str
    latest_snapshot: BookSnapshot | None


@dataclass(frozen=True)
class SnapshotStatusDetail:
    """Computed local status for one database snapshot."""

    snapshot: BookSnapshot
    directory_exists: bool
    local_file_count: int
    db_file_count: int


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < _BYTES_PER_UNIT or unit == "GiB":
            if unit == "B":
                return f"{value} B"
            return f"{size:.1f} {unit}"
        size /= _BYTES_PER_UNIT
    return f"{value} B"


def _format_progress(snapshot: BookSnapshot | None) -> str:
    if snapshot is None:
        return "-"
    files = f"{snapshot.completed_files}/{snapshot.total_files} files"
    bytes_ = (
        f"{_format_bytes(snapshot.downloaded_bytes)}/"
        f"{_format_bytes(snapshot.total_bytes)}"
    )
    return f"{files}, {bytes_}"


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "-"


def _latest_snapshot(book: Book) -> BookSnapshot | None:
    if not book.snapshots:
        return None
    return max(book.snapshots, key=lambda snapshot: snapshot.version)


def _snapshot_path_exists(snapshot: BookSnapshot) -> bool:
    return Path(snapshot.snapshot_path).is_dir()


def _local_path_state(snapshots: list[BookSnapshot]) -> str:
    if not snapshots:
        return "none"
    existing = sum(1 for snapshot in snapshots if _snapshot_path_exists(snapshot))
    if existing == len(snapshots):
        return "yes"
    if existing == 0:
        return "no"
    return "partial"


def _local_snapshot_dir_count(book: Book) -> int:
    book_dir = downloads_dir() / book.identifier
    if not book_dir.is_dir():
        return 0
    return sum(1 for path in book_dir.iterdir() if path.is_dir())


def _book_summary(book: Book) -> BookStatusSummary:
    snapshots = list(book.snapshots)
    return BookStatusSummary(
        book=book,
        snapshot_count=len(snapshots),
        local_snapshot_count=_local_snapshot_dir_count(book),
        local_path_state=_local_path_state(snapshots),
        latest_snapshot=_latest_snapshot(book),
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
    return [_book_summary(book) for book in books], total


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


def _local_file_count(snapshot: BookSnapshot) -> int:
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
            directory_exists=_snapshot_path_exists(snapshot),
            local_file_count=_local_file_count(snapshot),
            db_file_count=len(snapshot.files),
        )
        for snapshot in snapshots
    ]


def _build_summary_table(
    summaries: list[BookStatusSummary],
    *,
    total: int,
    limit: int,
    page: int,
) -> Table:
    table = Table(
        title=f"Downloaded Books (page {page}, showing {len(summaries)} of {total})",
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Identifier", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold white", overflow="fold")
    table.add_column("Authors", overflow="fold")
    table.add_column("Publishers", overflow="fold")
    table.add_column("Published", no_wrap=True)
    table.add_column("DB Snapshots", justify="right", no_wrap=True)
    table.add_column("Local Snapshots", justify="right", no_wrap=True)
    table.add_column("Latest Version", no_wrap=True)
    table.add_column("Latest Status", no_wrap=True)
    table.add_column("Progress", overflow="fold")
    table.add_column("Paths", no_wrap=True)

    for summary in summaries:
        latest = summary.latest_snapshot
        table.add_row(
            summary.book.identifier,
            summary.book.title,
            _format_list(summary.book.authors),
            _format_list(summary.book.publishers),
            summary.book.publication_date or "-",
            str(summary.snapshot_count),
            str(summary.local_snapshot_count),
            latest.version if latest is not None else "-",
            latest.status if latest is not None else "-",
            _format_progress(latest),
            summary.local_path_state,
        )

    if total > page * limit:
        table.caption = f"Next page: extro status --limit {limit} --page {page + 1}"
    return table


def _build_book_panel(book: Book) -> Panel:
    details = Table.grid(padding=(0, 2))
    details.add_column(style="bold cyan", no_wrap=True)
    details.add_column()
    details.add_row("Identifier", book.identifier)
    details.add_row("Title", book.title)
    details.add_row("OURN", book.ourn)
    details.add_row("ISBN", book.isbn or "-")
    details.add_row("Language", book.language or "-")
    details.add_row("Authors", _format_list(book.authors))
    details.add_row("Publishers", _format_list(book.publishers))
    details.add_row("Publication Date", book.publication_date or "-")
    details.add_row("Latest Version", book.latest_version)
    details.add_row("Created", str(book.created_at))
    details.add_row("Updated", str(book.updated_at))
    return Panel(details, title="[bold cyan]Book[/bold cyan]", border_style="cyan")


def _build_snapshot_table(details: list[SnapshotStatusDetail]) -> Table:
    table = Table(
        title="Snapshots",
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("ID", justify="right", no_wrap=True)
    table.add_column("Version", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Progress", overflow="fold")
    table.add_column("Directory", no_wrap=True)
    table.add_column("Local Files", justify="right", no_wrap=True)
    table.add_column("Path", overflow="fold")

    for detail in details:
        snapshot = detail.snapshot
        table.add_row(
            str(snapshot.id),
            snapshot.version,
            snapshot.status,
            _format_progress(snapshot),
            "yes" if detail.directory_exists else "no",
            f"{detail.local_file_count}/{detail.db_file_count}",
            snapshot.snapshot_path,
        )
    return table


def status_command(
    book_identifier: Annotated[
        str | None,
        typer.Argument(help="Optional O'Reilly book identifier, URN, or URL."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-l",
            min=1,
            help="Number of books to show in list mode.",
        ),
    ] = 10,
    page: Annotated[
        int,
        typer.Option(
            "--page",
            "-p",
            min=1,
            help="Page number for list mode, starting at 1.",
        ),
    ] = 1,
) -> None:
    """Show database and local filesystem status for downloaded books."""
    upgrade_database()
    with session_scope() as session:
        if book_identifier is None:
            summaries, total = list_book_summaries(session, limit=limit, page=page)
            if not summaries:
                console.print("[yellow]No downloaded books found.[/yellow]")
                return
            console.print(
                _build_summary_table(
                    summaries,
                    total=total,
                    limit=limit,
                    page=page,
                )
            )
            return

        book = find_book(session, book_identifier)
        if book is None:
            err_console.print(
                f"[bold yellow]Book not found:[/bold yellow] {book_identifier}"
            )
            raise typer.Exit(1)
        console.print(_build_book_panel(book))
        console.print(_build_snapshot_table(snapshot_details(book)))
