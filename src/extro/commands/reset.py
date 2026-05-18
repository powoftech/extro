from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import questionary
import typer
from rich.console import Console
from rich.panel import Panel

from extro.app import paths as app_paths
from extro.app.cleanup import remove_path
from extro.storage.database import upgrade_database

if TYPE_CHECKING:
    from pathlib import Path

console = Console()
err_console = Console(stderr=True)

_APP_CONFIRMATION = "extro"


@dataclass(frozen=True)
class ResetSummary:
    books: int | None
    snapshots: int | None
    files: int | None
    downloads_exists: bool
    database_exists: bool


def _count_books(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT count(*) FROM books").fetchone()
    return int(row[0] if row is not None else 0)


def _count_snapshots(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT count(*) FROM book_snapshots").fetchone()
    return int(row[0] if row is not None else 0)


def _count_files(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT count(*) FROM book_files").fetchone()
    return int(row[0] if row is not None else 0)


def _reset_summary(db_path: Path, downloads_root: Path) -> ResetSummary:
    if not db_path.exists():
        return ResetSummary(
            books=0,
            snapshots=0,
            files=0,
            downloads_exists=downloads_root.exists(),
            database_exists=False,
        )

    try:
        with closing(sqlite3.connect(str(db_path))) as connection:
            books = _count_books(connection)
            snapshots = _count_snapshots(connection)
            files = _count_files(connection)
    except sqlite3.Error:
        return ResetSummary(
            books=None,
            snapshots=None,
            files=None,
            downloads_exists=downloads_root.exists(),
            database_exists=True,
        )

    return ResetSummary(
        books=books,
        snapshots=snapshots,
        files=files,
        downloads_exists=downloads_root.exists(),
        database_exists=True,
    )


def _count_display(value: int | None) -> str:
    return "unavailable" if value is None else str(value)


def _summary_panel(summary: ResetSummary, db_path: Path, downloads_root: Path) -> Panel:
    message = (
        "This will permanently delete your local Extro library.\n\n"
        f"Books: {_count_display(summary.books)}\n"
        f"Snapshots: {_count_display(summary.snapshots)}\n"
        f"Files: {_count_display(summary.files)}\n"
        f"Downloads: {downloads_root if summary.downloads_exists else 'not present'}\n"
        f"Database: {db_path if summary.database_exists else 'not present'}\n\n"
        f"Type [bold]{_APP_CONFIRMATION}[/bold] to continue."
    )
    return Panel(
        message,
        title="[bold red]Destructive Reset[/bold red]",
        border_style="red",
    )


def reset_command() -> None:
    """Delete all downloaded books, snapshots, and local assets."""
    root = app_paths.user_data_dir_path()
    downloads_root = root / "downloads"
    db_path = root / "extro.db"

    summary = _reset_summary(db_path, downloads_root)
    console.print(_summary_panel(summary, db_path, downloads_root))

    typed = cast(
        "str | None",
        questionary.text(
            f"Type {_APP_CONFIRMATION} to confirm reset:",
            default="",
        ).ask(),
    )
    if typed is None or typed.strip().casefold() != _APP_CONFIRMATION:
        console.print("[dim]Aborted - confirmation text did not match.[/dim]")
        return

    try:
        remove_path(downloads_root)
        remove_path(db_path)
        upgrade_database(db_path)
    except OSError as exc:
        err_console.print(f"[bold red]Reset failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        Panel(
            "Local Extro data has been reset.\n"
            "The database was recreated and downloaded assets were removed.",
            title="[bold green]Reset Complete[/bold green]",
            border_style="green",
        )
    )
