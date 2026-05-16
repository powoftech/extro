"""extro CLI - main entry point."""

from __future__ import annotations

import typer
from rich.console import Console

from extro import __version__
from extro.commands.config import config_command
from extro.commands.delete import delete_command
from extro.commands.download import download_command
from extro.commands.search import search_command
from extro.commands.status import status_command

console = Console()

app = typer.Typer(
    name="extro",
    help=(
        "[bold cyan]extro[/bold cyan]\n\nRun [bold]extro config[/bold] to get started."
    ),
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)


def _version_callback(value: str | None) -> None:
    if value is not None:
        console.print(f"extro [bold cyan]{__version__}[/bold cyan]")
        raise typer.Exit


@app.callback()
def main(
    version: str | None = typer.Option(
        None,
        "--version",
        "-V",
        help="Show the application version and exit.",
        callback=_version_callback,
        is_eager=True,
        is_flag=True,
        flag_value="1",
    ),
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
    name="status",
    help="Show database and local filesystem status for downloaded books.",
)(status_command)
app.command(
    name="delete",
    help="Delete one or more downloaded snapshots for a book.",
)(delete_command)


if __name__ == "__main__":
    app()
