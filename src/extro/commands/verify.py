"""CLI command: verify downloaded snapshot file integrity."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from extro.downloads.integrity import (
    FileIntegrityResult,
    IntegrityState,
    verify_snapshot,
)
from extro.downloads.status import find_book
from extro.storage.database import session_scope, upgrade_database
from extro.storage.models import Book, BookSnapshot

if TYPE_CHECKING:
    from collections.abc import Iterable

console = Console()
err_console = Console(stderr=True)


def _all_books() -> Select[tuple[Book]]:
    return (
        select(Book)
        .options(selectinload(Book.snapshots).selectinload(BookSnapshot.files))
        .order_by(Book.identifier.asc())
    )


def _result_detail(result: FileIntegrityResult) -> str:
    if result.state == IntegrityState.CHANGED:
        expected = result.expected_sha256 or "-"
        actual = result.actual_sha256 or "-"
        return f"expected {expected[:12]}, found {actual[:12]}"
    if result.state == IntegrityState.MISSING:
        return "file missing on disk"
    if result.state == IntegrityState.WRITABLE:
        return "file has write permission"
    if result.state == IntegrityState.UNVERIFIED:
        return "no stored SHA-256"
    if result.state == IntegrityState.ERROR:
        return result.error or "verification error"
    return "ok"


def _issue_table(
    rows: Iterable[tuple[Book, BookSnapshot, FileIntegrityResult]],
) -> Table:
    table = Table(
        title="Integrity Issues",
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Book", style="cyan", no_wrap=True)
    table.add_column("Snapshot", no_wrap=True)
    table.add_column("State", no_wrap=True)
    table.add_column("File", overflow="fold")
    table.add_column("Details", overflow="fold")
    for book, snapshot, result in rows:
        table.add_row(
            book.identifier,
            snapshot.version,
            result.state,
            result.file.full_path,
            _result_detail(result),
        )
    return table


def verify_command(
    book_identifier: Annotated[
        str | None,
        typer.Argument(help="Optional O'Reilly book identifier, URN, or URL."),
    ] = None,
) -> None:
    """Verify stored SHA-256 values and read-only flags for downloaded files."""
    upgrade_database()
    with session_scope() as session:
        if book_identifier is None:
            books = list(session.scalars(_all_books()).all())
        else:
            book = find_book(session, book_identifier)
            if book is None:
                err_console.print(
                    f"[bold yellow]Book not found:[/bold yellow] {book_identifier}"
                )
                raise typer.Exit(1)
            books = [book]

        if not books:
            console.print("[yellow]No downloaded books found.[/yellow]")
            return

        ok_count = 0
        issue_rows: list[tuple[Book, BookSnapshot, FileIntegrityResult]] = []
        state_counts: Counter[IntegrityState] = Counter()
        for book in books:
            for snapshot in book.snapshots:
                summary = verify_snapshot(snapshot)
                for result in summary.results:
                    state_counts[result.state] += 1
                    if result.state == IntegrityState.OK:
                        ok_count += 1
                    else:
                        issue_rows.append((book, snapshot, result))

    if issue_rows:
        console.print(_issue_table(issue_rows))
        console.print(
            Panel(
                "Integrity check failed\n"
                f"ok: {ok_count}\n"
                f"changed: {state_counts[IntegrityState.CHANGED]}\n"
                f"missing: {state_counts[IntegrityState.MISSING]}\n"
                f"writable: {state_counts[IntegrityState.WRITABLE]}\n"
                f"unverified: {state_counts[IntegrityState.UNVERIFIED]}\n"
                f"errors: {state_counts[IntegrityState.ERROR]}",
                title="[bold red]Verify Failed[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    console.print(
        Panel(
            f"Verified files: {ok_count}",
            title="[bold green]Verify Complete[/bold green]",
            border_style="green",
        )
    )
