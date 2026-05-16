from __future__ import annotations

from typing import TYPE_CHECKING

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from extro.app.config import AppConfig
from extro.app.exceptions import ExtroError, FirefoxNotFoundError, NoProfilesError
from extro.platform.firefox import FirefoxProfile, get_firefox_profiles

if TYPE_CHECKING:
    from pathlib import Path

console = Console()
err_console = Console(stderr=True)

_QUESTIONARY_STYLE = questionary.Style(
    [
        ("qmark", "fg:#5fd7ff bold"),
        ("question", "fg:#ffffff bold"),
        ("pointer", "fg:#5fd7ff bold"),
        ("highlighted", "fg:#5fd7ff bold"),
        ("selected", "fg:#5fd7ff"),
        ("answer", "fg:#5fd7ff bold"),
    ]
)


def _build_profile_table(
    profiles: list[FirefoxProfile],
    selected_dir: Path | None,
) -> Table:
    """Render a Rich table summarising loaded profiles."""
    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=False,
    )
    table.add_column("Profile Name", style="bold white", no_wrap=True)
    table.add_column("Path", style="dim", overflow="fold")
    table.add_column("Status", justify="center")

    for profile in profiles:
        badges: list[str] = []
        if profile.is_default:
            badges.append("[green]default[/green]")
        if selected_dir is not None and profile.path == selected_dir:
            badges.append("[yellow]★ saved[/yellow]")
        status = " · ".join(badges) if badges else ""
        table.add_row(profile.name, str(profile.path), status)

    return table


def config_command() -> None:
    """Select a Firefox profile and save it as the active profile for extro."""
    # ── Load existing config ────────────────────────────────────────────
    try:
        app_config = AppConfig.load()
    except ExtroError as exc:
        err_console.print(f"[bold red]Config error:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    # ── Discover Firefox profiles ───────────────────────────────────────
    console.print()
    with console.status("[bold cyan]Scanning for Firefox profiles…[/bold cyan]"):
        try:
            profiles = get_firefox_profiles()
        except FirefoxNotFoundError as exc:
            err_console.print(
                Panel(
                    Text(str(exc), style="red"),
                    title="[bold red]Firefox Not Found[/bold red]",
                    border_style="red",
                )
            )
            raise typer.Exit(1) from exc
        except NoProfilesError as exc:
            err_console.print(
                Panel(
                    Text(str(exc), style="yellow"),
                    title="[bold yellow]No Profiles Found[/bold yellow]",
                    border_style="yellow",
                )
            )
            raise typer.Exit(1) from exc

    # ── Display profile table ───────────────────────────────────────────
    table = _build_profile_table(profiles, app_config.firefox_profile_dir)
    console.print(
        Panel(
            table,
            title="[bold cyan]Firefox Profiles[/bold cyan]",
            subtitle=f"[dim]{len(profiles)} profile(s) found[/dim]",
            border_style="cyan",
        )
    )
    console.print()

    # ── Interactive selection ───────────────────────────────────────────
    # Pre-select the currently saved profile if any, else the first one.
    default_profile: FirefoxProfile = next(
        (p for p in profiles if p.path == app_config.firefox_profile_dir),
        profiles[0],
    )

    choices = [
        questionary.Choice(
            title=f"{profile.name}",
            value=profile,
            # Mark the pre-selected profile as the shortcut default
            shortcut_key=None,
        )
        for profile in profiles
    ]

    # questionary.select `default` must match a Choice.value - pass the object.
    selected: FirefoxProfile | None = questionary.select(
        "Select a Firefox profile to use:",
        choices=choices,
        default=default_profile,  # type: ignore
        style=_QUESTIONARY_STYLE,
        instruction="(↑↓ to move, Enter to confirm)",
    ).ask()

    if selected is None:
        # User cancelled with Ctrl-C
        console.print("[dim]Aborted - no changes saved.[/dim]")
        raise typer.Exit(0)

    # ── Persist selection ───────────────────────────────────────────────
    app_config = AppConfig(firefox_profile_dir=selected.path)
    try:
        saved_path = app_config.save()
    except ExtroError as exc:
        err_console.print(f"[bold red]Failed to save config:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    console.print()
    console.print(
        Panel(
            f"[bold green]✓[/bold green]  Profile [bold white]{selected.name}"
            f"[/bold white] saved.\n"
            f"    Path: [dim]{selected.path}[/dim]\n"
            f"    Config: [dim]{saved_path}[/dim]",
            title="[bold green]Configuration Saved[/bold green]",
            border_style="green",
        )
    )
    console.print()
