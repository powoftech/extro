from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast

import questionary
import typer
from rich.console import Console
from rich.panel import Panel

from extro.commands.status import (
    _format_progress,
    _snapshot_path_exists,
    find_book,
    snapshot_details,
)
from extro.core.database import session_scope, upgrade_database
from extro.core.exceptions import ExtroError
from extro.core.paths import downloads_dir

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from extro.core.models import Book, BookSnapshot

console = Console()
err_console = Console(stderr=True)


@dataclass(frozen=True)
class DeleteResult:
    """Result of deleting selected snapshots."""

    deleted_snapshots: int
    removed_directories: int
    missing_directories: int
    deleted_book: bool


def _managed_snapshot_path(snapshot: BookSnapshot) -> Path:
    root = downloads_dir().resolve()
    path = Path(snapshot.snapshot_path).resolve()
    if path == root or root not in path.parents:
        msg = f"Refusing to delete snapshot outside extro downloads directory: {path}"
        raise ExtroError(msg)
    return path


def _remove_snapshot_directories(snapshots: list[BookSnapshot]) -> tuple[int, int]:
    paths = [_managed_snapshot_path(snapshot) for snapshot in snapshots]
    removed = 0
    missing = 0
    for path in paths:
        if not path.exists():
            missing += 1
            continue
        shutil.rmtree(path)
        removed += 1
    return removed, missing


def delete_snapshots(
    session: Session,
    book: Book,
    snapshot_ids: set[int],
) -> DeleteResult:
    """Delete selected snapshot rows and their local directories."""
    selected = [snapshot for snapshot in book.snapshots if snapshot.id in snapshot_ids]
    if not selected:
        return DeleteResult(
            deleted_snapshots=0,
            removed_directories=0,
            missing_directories=0,
            deleted_book=False,
        )

    removed, missing = _remove_snapshot_directories(selected)
    remaining = [
        snapshot for snapshot in book.snapshots if snapshot.id not in snapshot_ids
    ]
    deleted_book = not remaining
    if deleted_book:
        session.delete(book)
    else:
        for snapshot in selected:
            session.delete(snapshot)
    session.flush()

    return DeleteResult(
        deleted_snapshots=len(selected),
        removed_directories=removed,
        missing_directories=missing,
        deleted_book=deleted_book,
    )


def _snapshot_choice_title(snapshot: BookSnapshot) -> str:
    exists = "local:yes" if _snapshot_path_exists(snapshot) else "local:no"
    return (
        f"{snapshot.version} "
        f"({snapshot.status}, {_format_progress(snapshot)}, {exists})"
    )


def delete_command(
    book_identifier: Annotated[
        str,
        typer.Argument(help="O'Reilly book identifier, URN, or URL."),
    ],
) -> None:
    """Interactively delete one or more snapshots for a downloaded book."""
    upgrade_database()
    try:
        with session_scope() as session:
            book = find_book(session, book_identifier)
            if book is None:
                err_console.print(
                    f"[bold yellow]Book not found:[/bold yellow] {book_identifier}"
                )
                raise typer.Exit(1)
            if not book.snapshots:
                console.print("[yellow]No snapshots found for this book.[/yellow]")
                return

            choices = [
                questionary.Choice(
                    title=_snapshot_choice_title(detail.snapshot),
                    value=detail.snapshot.id,
                )
                for detail in snapshot_details(book)
            ]
            selected = cast(
                "list[int] | None",
                questionary.checkbox(
                    f"Select snapshots to delete for {book.identifier}:",
                    choices=choices,
                    instruction="(space to select, enter to confirm)",
                ).ask(),
            )
            if selected is None:
                console.print("[dim]Aborted - no snapshots deleted.[/dim]")
                return
            if not selected:
                console.print("[dim]No snapshots selected.[/dim]")
                return

            deleting_all = len(selected) == len(book.snapshots)
            prompt = (
                "Delete all selected snapshots and the book database row?"
                if deleting_all
                else "Delete selected snapshots?"
            )
            confirmed = questionary.confirm(prompt, default=False).ask()
            if not confirmed:
                console.print("[dim]Aborted - no snapshots deleted.[/dim]")
                return

            result = delete_snapshots(session, book, set(selected))
    except ExtroError as exc:
        err_console.print(f"[bold red]Delete failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    book_message = "\n[dim]Book row deleted because no snapshots remain.[/dim]"
    console.print(
        Panel(
            "[bold green]Deleted snapshots:[/bold green] "
            f"{result.deleted_snapshots}\n"
            f"Removed directories: {result.removed_directories}\n"
            f"Missing directories: {result.missing_directories}"
            f"{book_message if result.deleted_book else ''}",
            title="[bold green]Delete Complete[/bold green]",
            border_style="green",
        )
    )
