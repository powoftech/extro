from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast

import questionary
import typer
from rich.console import Console
from rich.panel import Panel

from extro.app.exceptions import ExtroError
from extro.app.paths import downloads_dir, export_file_stem, exports_dir
from extro.downloads.status import (
    find_book,
    format_progress,
    snapshot_details,
    snapshot_path_exists,
)
from extro.storage.database import session_scope, upgrade_database

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from extro.storage.models import Book, BookSnapshot

console = Console()
err_console = Console(stderr=True)


@dataclass(frozen=True)
class DeleteResult:
    """Result of deleting selected snapshots."""

    deleted_snapshots: int
    removed_directories: int
    missing_directories: int
    removed_exports: int
    deleted_book: bool


def _managed_snapshot_path(snapshot: BookSnapshot) -> Path:
    root = downloads_dir().resolve()
    path = Path(snapshot.snapshot_path).resolve()
    if path == root or root not in path.parents:
        msg = f"Refusing to delete snapshot outside extro downloads directory: {path}"
        raise ExtroError(msg)
    return path


def _managed_export_base_path(book: Book, snapshot: BookSnapshot) -> Path:
    root = exports_dir().resolve()
    path = root / export_file_stem(
        book.title,
        snapshot.version,
        fallback=book.identifier,
    )
    if path == root or root not in path.parents:
        msg = f"Refusing to delete export outside extro exports directory: {path}"
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


def _remove_export_files(book: Book, snapshots: list[BookSnapshot]) -> int:
    removed = 0
    for snapshot in snapshots:
        base_path = _managed_export_base_path(book, snapshot)
        for path in sorted(base_path.parent.glob(f"{base_path.name}.*")):
            if not path.is_file():
                continue
            path.unlink()
            removed += 1
    return removed


def delete_snapshots(
    session: Session,
    book: Book,
    snapshot_ids: set[int],
    *,
    remove_exports: bool = False,
) -> DeleteResult:
    """Delete selected snapshot rows and their local directories or exports."""
    selected = [snapshot for snapshot in book.snapshots if snapshot.id in snapshot_ids]
    if not selected:
        return DeleteResult(
            deleted_snapshots=0,
            removed_directories=0,
            missing_directories=0,
            removed_exports=0,
            deleted_book=False,
        )

    removed_exports = _remove_export_files(book, selected) if remove_exports else 0
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
        removed_exports=removed_exports,
        deleted_book=deleted_book,
    )


def _snapshot_choice_title(snapshot: BookSnapshot) -> str:
    exists = "local:yes" if snapshot_path_exists(snapshot) else "local:no"
    return (
        f"{snapshot.version} ({snapshot.status}, {format_progress(snapshot)}, {exists})"
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

            selected_snapshots = [
                snapshot for snapshot in book.snapshots if snapshot.id in selected
            ]
            export_paths: list[Path] = []
            for snapshot in selected_snapshots:
                base_path = _managed_export_base_path(book, snapshot)
                export_paths.extend(
                    path
                    for path in sorted(base_path.parent.glob(f"{base_path.name}.*"))
                    if path.is_file()
                )

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

            remove_exports = False
            if export_paths:
                remove_exports = bool(
                    questionary.confirm(
                        f"Delete {len(export_paths)} converted file(s) from exports/?",
                        default=False,
                    ).ask()
                )

            result = delete_snapshots(
                session,
                book,
                set(selected),
                remove_exports=remove_exports,
            )
    except ExtroError as exc:
        err_console.print(f"[bold red]Delete failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    book_message = "\n[dim]Book row deleted because no snapshots remain.[/dim]"
    console.print(
        Panel(
            "[bold green]Deleted snapshots:[/bold green] "
            f"{result.deleted_snapshots}\n"
            f"Removed directories: {result.removed_directories}\n"
            f"Missing directories: {result.missing_directories}\n"
            f"Removed exports: {result.removed_exports}"
            f"{book_message if result.deleted_book else ''}",
            title="[bold green]Delete Complete[/bold green]",
            border_style="green",
        )
    )
