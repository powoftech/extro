"""CLI command: download an O'Reilly book snapshot."""

from __future__ import annotations

from typing import Annotated

import curl_cffi
import typer
from rich.console import Console
from rich.panel import Panel

from extro.app.config import AppConfig
from extro.app.exceptions import ConfigError, ExtroError
from extro.downloads.manager import DownloadManager
from extro.oreilly.client import OreillyClient
from extro.storage.database import session_scope, upgrade_database

console = Console()
err_console = Console(stderr=True)


def download_command(
    book_identifier: Annotated[
        str,
        typer.Argument(help="O'Reilly book identifier, URN, or URL."),
    ],
) -> None:
    """Download a book snapshot and resume incomplete downloads."""
    # Load config at the command boundary so domain classes stay decoupled.
    try:
        app_config = AppConfig.load()
    except ConfigError as exc:
        err_console.print(f"[bold red]Config error:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    if app_config.firefox_profile_dir is None:
        err_console.print(
            "[bold red]Config error:[/bold red] "
            "Run [bold]extro config[/bold] before downloading so Firefox cookies "
            "can be read."
        )
        raise typer.Exit(1)

    try:
        upgrade_database()
        with session_scope() as session:
            manager = DownloadManager(
                api_client=OreillyClient(
                    profile_dir=app_config.firefox_profile_dir,
                ),
                session=session,
                console=console,
            )
            snapshot_path = manager.download(
                book_identifier,
                profile_dir=app_config.firefox_profile_dir,
            )
    except (
        ExtroError,
        curl_cffi.CurlError,
        ValueError,
        TypeError,
    ) as exc:
        err_console.print(f"[bold red]Download failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        Panel(
            f"[bold green]Download complete[/bold green]\n[dim]{snapshot_path}[/dim]",
            title="[bold green]Snapshot Ready[/bold green]",
            border_style="green",
        ),
    )
