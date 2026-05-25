"""CLI command: convert a downloaded snapshot to EPUB."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast

import curl_cffi
import questionary
import typer
from rich.console import Console
from rich.panel import Panel

from extro.app.config import AppConfig
from extro.app.exceptions import ConfigError, ExtroError
from extro.app.paths import export_file_path
from extro.downloads.manager import DownloadManager
from extro.downloads.status import (
    SnapshotStatusDetail,
    find_book,
    format_progress,
    snapshot_details,
)
from extro.epub import build_epub
from extro.oreilly.client import OreillyClient
from extro.oreilly.identifiers import normalize_book_identifier
from extro.storage.database import session_scope, upgrade_database
from extro.storage.models import SnapshotStatus

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from extro.oreilly.schemas import BookMetadata
    from extro.storage.models import Book, BookSnapshot

console = Console()
err_console = Console(stderr=True)


class _AutoConfirmDownloadManager(DownloadManager):
    """Download manager variant used after convert already asked the user."""

    def _confirm_new_version(
        self,
        previous_snapshot: BookSnapshot,
        new_version: str,
    ) -> bool:
        _ = previous_snapshot, new_version
        return True


def _require_firefox_profile() -> Path:
    try:
        app_config = AppConfig.load()
    except ConfigError as exc:
        msg = f"Run extro config before downloading snapshots: {exc}"
        raise ExtroError(msg) from exc

    if app_config.firefox_profile_dir is None:
        msg = (
            "Run extro config before downloading snapshots so Firefox cookies "
            "can be read."
        )
        raise ExtroError(msg)
    return app_config.firefox_profile_dir


def _download_latest_snapshot(
    *,
    session: Session,
    client: OreillyClient,
    book_identifier: str,
    profile_dir: Path,
    skip_new_version_prompt: bool,
) -> None:
    manager_class = (
        _AutoConfirmDownloadManager if skip_new_version_prompt else DownloadManager
    )
    manager = manager_class(
        api_client=client,
        session=session,
        console=console,
    )
    manager.download(book_identifier, profile_dir=profile_dir)
    session.expire_all()


def _convertible_snapshot_details(book: Book) -> list[SnapshotStatusDetail]:
    return [
        detail
        for detail in snapshot_details(book)
        if (
            detail.snapshot.status == SnapshotStatus.COMPLETED
            and detail.directory_exists
        )
    ]


def _snapshot_choice_title(detail: SnapshotStatusDetail) -> str:
    snapshot = detail.snapshot
    return (
        f"{snapshot.version} "
        f"({format_progress(snapshot)}, "
        f"files {detail.local_file_count}/{detail.db_file_count})"
    )


def _select_snapshot(book: Book) -> SnapshotStatusDetail | None:
    choices = [
        questionary.Choice(
            title=_snapshot_choice_title(detail),
            value=detail,
        )
        for detail in _convertible_snapshot_details(book)
    ]
    if not choices:
        return None
    return cast(
        "SnapshotStatusDetail | None",
        questionary.select(
            f"Select a snapshot to convert for {book.identifier}:",
            choices=choices,
            instruction="(up/down to move, enter to confirm)",
        ).ask(),
    )


def _maybe_download_missing_latest(
    *,
    session: Session,
    client: OreillyClient,
    book: Book,
    metadata: BookMetadata,
    profile_dir: Path,
) -> Book:
    completed_versions = {
        detail.snapshot.version for detail in _convertible_snapshot_details(book)
    }
    if metadata.version in completed_versions:
        return book

    answer = questionary.confirm(
        (
            "A newer snapshot is available "
            f"({max(completed_versions)} -> {metadata.version}). "
            "Download it before converting?"
        ),
        default=True,
    ).ask()
    if answer:
        _download_latest_snapshot(
            session=session,
            client=client,
            book_identifier=metadata.identifier,
            profile_dir=profile_dir,
            skip_new_version_prompt=True,
        )
        updated = find_book(session, metadata.identifier)
        if updated is None:
            msg = "Downloaded snapshot, but the book row could not be reloaded."
            raise ExtroError(msg)
        return updated
    return book


def _ensure_book_with_snapshot(
    *,
    session: Session,
    client: OreillyClient,
    book_identifier: str,
    metadata: BookMetadata,
    profile_dir: Path,
) -> Book:
    book = find_book(session, book_identifier)
    if book is None or not _convertible_snapshot_details(book):
        console.print(
            "[yellow]No completed local snapshots found; downloading latest.[/yellow]"
        )
        _download_latest_snapshot(
            session=session,
            client=client,
            book_identifier=metadata.identifier,
            profile_dir=profile_dir,
            skip_new_version_prompt=False,
        )
        book = find_book(session, book_identifier)
        if book is None:
            msg = "Downloaded snapshot, but the book row could not be reloaded."
            raise ExtroError(msg)
        return book

    return _maybe_download_missing_latest(
        session=session,
        client=client,
        book=book,
        metadata=metadata,
        profile_dir=profile_dir,
    )


def _target_path(book: Book, snapshot: BookSnapshot) -> Path:
    return export_file_path(
        book.title,
        snapshot.version,
        extension="epub",
        fallback=book.identifier,
    )


def _confirm_overwrite(path: Path) -> bool:
    if not path.exists():
        return True
    return bool(
        questionary.confirm(
            f"EPUB already exists at {path}. Overwrite?",
            default=False,
        ).ask()
    )


def convert_command(
    book_identifier: Annotated[
        str,
        typer.Argument(help="O'Reilly book identifier, URN, or URL."),
    ],
) -> None:
    """Convert a downloaded O'Reilly book snapshot to EPUB."""
    try:
        profile_dir = _require_firefox_profile()
        client = OreillyClient(profile_dir=profile_dir)
        identifier = normalize_book_identifier(book_identifier)
        metadata = client.fetch_metadata(identifier)
        upgrade_database()
        with session_scope() as session:
            book = _ensure_book_with_snapshot(
                session=session,
                client=client,
                book_identifier=identifier,
                metadata=metadata,
                profile_dir=profile_dir,
            )
            selected = _select_snapshot(book)
            if selected is None:
                console.print("[dim]Aborted - no snapshot converted.[/dim]")
                return

            output_path = _target_path(book, selected.snapshot)
            if not _confirm_overwrite(output_path):
                console.print("[dim]Aborted - existing EPUB left unchanged.[/dim]")
                return

            snapshot_path = Path(selected.snapshot.snapshot_path)

            result = build_epub(snapshot_path, output_path, title=book.title)
    except (
        ExtroError,
        curl_cffi.CurlError,
        ValueError,
        TypeError,
        OSError,
    ) as exc:
        err_console.print(f"[bold red]Convert failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        Panel(
            "[bold green]EPUB ready[/bold green]\n"
            f"[dim]{result.output_path}[/dim]\n"
            f"HTML files: {result.html_file_count}\n"
            f"Manifest items: {result.manifest_item_count}",
            title="[bold green]Convert Complete[/bold green]",
            border_style="green",
        )
    )
