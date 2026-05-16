from __future__ import annotations

from enum import StrEnum
from typing import Annotated

import curl_cffi
import typer
from rich.console import Console
from rich.table import Table

from extro.core.api import OreillyClient, SearchField, SearchResult

console = Console()
err_console = Console(stderr=True)


class SearchFieldOption(StrEnum):
    TITLE = "title"
    PUBLISHERS = "publishers"
    AUTHORS = "authors"
    ISBN = "isbn"


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "-"


def _build_results_table(results: list[SearchResult]) -> Table:
    table = Table(
        title="O'Reilly Books",
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Identifier", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold white", overflow="fold")
    table.add_column("Authors", overflow="fold")
    table.add_column("Publishers", overflow="fold")
    table.add_column("ISBN", no_wrap=True)
    table.add_column("Issued", no_wrap=True)
    table.add_column("Modified", no_wrap=True)
    # table.add_column("Popularity", justify="right", no_wrap=True)
    # table.add_column("URL", overflow="fold")

    for result in results:
        table.add_row(
            result.archive_id,
            result.title,
            _format_list(result.authors),
            _format_list(result.publishers),
            result.isbn or "-",
            result.issued or "-",
            result.last_modified_time or "-",
            # str(result.popularity) if result.popularity is not None else "-",
            # result.web_url or "-",
        )
    return table


def search_command(
    keyword: Annotated[str, typer.Argument(help="Keyword to search for.")],
    field: Annotated[
        SearchFieldOption,
        typer.Option(
            "--field",
            help="Search field to constrain the query.",
            case_sensitive=False,
        ),
    ] = SearchFieldOption.TITLE,
) -> None:
    """Search English O'Reilly books."""
    client = OreillyClient()
    try:
        search_field: SearchField = field.value
        response = client.search(keyword, field=search_field)
    except curl_cffi.CurlError as exc:
        err_console.print(f"[bold red]Search failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    if not response.results:
        console.print("[yellow]No matching books found.[/yellow]")
        return

    console.print(_build_results_table(response.results))
    console.print(
        f"[dim]Showing {len(response.results)} of {response.total} result(s).[/dim]",
    )
