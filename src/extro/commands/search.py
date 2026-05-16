from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Annotated

import curl_cffi
import typer
from rich.console import Console
from rich.table import Table

from extro.oreilly.client import OreillyClient, SearchParams

if TYPE_CHECKING:
    from extro.oreilly.schemas import (
        SearchField,
        SearchResult,
        SearchSort,
        SearchSortOrder,
    )

console = Console()
err_console = Console(stderr=True)


class SearchFieldOption(StrEnum):
    TITLE = "title"
    PUBLISHERS = "publishers"
    AUTHORS = "authors"
    ISBN = "isbn"


class SearchSortOption(StrEnum):
    RELEVANCE = "relevance"
    POPULARITY = "popularity"
    DATE_ADDED = "date_added"
    PUBLICATION_DATE = "publication_date"
    AVERAGE_RATING = "average_rating"
    TITLE = "title"
    DURATION = "duration"


class SearchSortOrderOption(StrEnum):
    DESC = "desc"
    ASC = "asc"


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "-"


def _build_results_table(results: list[SearchResult]) -> Table:
    table = Table(
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


def search_command(  # noqa: PLR0913
    keyword: Annotated[str, typer.Argument(help="Keyword to search for.")],
    field: Annotated[
        SearchFieldOption,
        typer.Option(
            "--field",
            help="Search field to constrain the query.",
            case_sensitive=False,
        ),
    ] = SearchFieldOption.TITLE,
    sort: Annotated[
        SearchSortOption,
        typer.Option(
            "--sort",
            help="Result field to sort by.",
            case_sensitive=False,
        ),
    ] = SearchSortOption.POPULARITY,
    order: Annotated[
        SearchSortOrderOption,
        typer.Option("--order", help="The sort order to use.", case_sensitive=False),
    ] = SearchSortOrderOption.DESC,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-l",
            min=1,
            max=200,
            help="Number of results to show.",
        ),
    ] = 10,
    page: Annotated[
        int,
        typer.Option(
            "--page",
            "-p",
            min=1,
            help="Page number to show, starting at 1.",
        ),
    ] = 1,
) -> None:
    """Search English O'Reilly books."""
    client = OreillyClient()
    try:
        search_field: SearchField = field.value
        search_sort: SearchSort = sort.value
        search_sort_order: SearchSortOrder = order.value
        response = client.search(
            keyword,
            params=SearchParams(
                field=search_field,
                sort=search_sort,
                order=search_sort_order,
                limit=limit,
                page=page,
            ),
        )
    except curl_cffi.CurlError as exc:
        err_console.print(f"[bold red]Search failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    if not response.results:
        console.print("[yellow]No matching books found.[/yellow]")
        return

    console.print(_build_results_table(response.results))
    console.print(
        f"[dim]Page {page}: showing {len(response.results)} "
        f"of {response.total} result(s).[/dim]",
    )
    if response.total > page * limit:
        console.print(
            f"[dim]Next page: extro search {keyword!r} "
            f"--field {field.value} --sort {sort.value} "
            f"--limit {limit} --page {page + 1}[/dim]",
        )
