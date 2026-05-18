"""extro CLI - main entry point."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from extro.app.version import APP_NAME, get_app_version
from extro.commands.config import config_command
from extro.commands.convert import convert_command
from extro.commands.delete import delete_command
from extro.commands.download import download_command
from extro.commands.reset import reset_command
from extro.commands.search import search_command
from extro.commands.status import status_command
from extro.commands.verify import verify_command

console = Console()

app = typer.Typer(
    name=APP_NAME,
    help=(
        "[bold cyan]extro[/bold cyan]\n\nRun [bold]extro config[/bold] to get started."
    ),
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)


def _version_callback(*, value: bool) -> None:
    if value:
        console.print(f"{APP_NAME} [bold cyan]{get_app_version()}[/bold cyan]")
        raise typer.Exit


@app.callback()
def main(
    *,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show the application version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """extro"""


app.command(
    name="config",
    help="Select a Firefox profile and save it as the active profile.",
    epilog="Run this first to configure which Firefox profile extro should use.",
)(config_command)
app.command(
    name="search",
    help="Search English books on O'Reilly Learning.",
)(search_command)
app.command(
    name="download",
    help="Download an O'Reilly book snapshot and resume progress.",
)(download_command)
app.command(
    name="convert",
    help="Convert an O'Reilly book snapshot to Send to Kindle-compatible EPUB.",
)(convert_command)
app.command(
    name="status",
    help="Show database and local filesystem status for downloaded books.",
)(status_command)
app.command(
    name="verify",
    help="Verify downloaded file hashes and read-only protection.",
)(verify_command)
app.command(
    name="delete",
    help="Delete one or more downloaded snapshots for a book.",
)(delete_command)
app.command(
    name="reset",
    help="Delete all books, snapshots, and local download assets.",
)(reset_command)


if __name__ == "__main__":
    app()
