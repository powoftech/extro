"""CLI commands for inspecting and deleting downloaded book snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from extro.app.time import ms_epoch_to_iso8601
from extro.downloads.status import (
    BookStatusSummary,
    SnapshotStatusDetail,
    find_book,
    format_list,
    format_progress,
    list_book_summaries,
    snapshot_details,
)
from extro.storage.database import session_scope, upgrade_database

if TYPE_CHECKING:
    from extro.storage.models import Book

console = Console()
err_console = Console(stderr=True)


def _build_summary_table(
    summaries: list[BookStatusSummary],
) -> Table:
    table = Table(
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Identifier", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold white", overflow="fold")
    table.add_column("Authors", overflow="fold")
    table.add_column("Publishers", overflow="fold")
    table.add_column("Publication\nDate", no_wrap=True)
    table.add_column("DB\nSnapshots", justify="right", no_wrap=True)
    table.add_column("Local\nSnapshots", justify="right", no_wrap=True)
    table.add_column("Latest\nVersion", no_wrap=True)
    table.add_column("Latest\nStatus", no_wrap=True)
    table.add_column("Latest\nIntegrity", no_wrap=True)
    table.add_column("Progress", overflow="fold")
    table.add_column("Paths", no_wrap=True)

    for summary in summaries:
        latest = summary.latest_snapshot
        table.add_row(
            summary.book.identifier,
            summary.book.title,
            format_list(summary.book.authors),
            format_list(summary.book.publishers),
            summary.book.publication_date or "-",
            str(summary.snapshot_count),
            str(summary.local_snapshot_count),
            ms_epoch_to_iso8601(latest.version) if latest is not None else "-",
            latest.status if latest is not None else "-",
            summary.latest_integrity_state or "-",
            format_progress(latest),
            summary.local_path_state,
        )

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
    details.add_row("Authors", format_list(book.authors))
    details.add_row("Publishers", format_list(book.publishers))
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
    table.add_column("Integrity", no_wrap=True)
    table.add_column("Path", overflow="fold")

    for detail in details:
        snapshot = detail.snapshot
        table.add_row(
            str(snapshot.id),
            ms_epoch_to_iso8601(snapshot.version),
            snapshot.status,
            format_progress(snapshot),
            "yes" if detail.directory_exists else "no",
            f"{detail.local_file_count}/{detail.db_file_count}",
            detail.integrity_state,
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
            console.print(_build_summary_table(summaries))
            console.print(
                f"[dim]Page {page}: showing {len(summaries)} "
                f"of {total} result(s).[/dim]",
            )
            if total > page * limit:
                console.print(
                    f"[dim]Next page: extro status "
                    f"--limit {limit} --page {page + 1}[/dim]",
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
