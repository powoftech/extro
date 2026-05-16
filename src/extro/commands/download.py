from __future__ import annotations

from typing import Annotated

import curl_cffi
import typer
from rich.console import Console
from rich.panel import Panel

from extro.core.api import OreillyClient
from extro.core.database import session_scope, upgrade_database
from extro.core.download import DownloadManager
from extro.core.exceptions import ExtroError

console = Console()
err_console = Console(stderr=True)


def download_command(
    book_identifier: Annotated[
        str,
        typer.Argument(help="O'Reilly book identifier, URN, or URL."),
    ],
) -> None:
    """Download a book snapshot and resume incomplete downloads."""
    try:
        upgrade_database()
        with session_scope() as session:
            manager = DownloadManager(
                api_client=OreillyClient(),
                session=session,
                console=console,
            )
            snapshot_path = manager.download(book_identifier)
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
