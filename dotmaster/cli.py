"""
dotmaster/cli.py
Entry-point: defines all `dotmaster` CLI commands using Typer.

Commands
--------
  init      Run the wizard and generate all dotfiles
  sync      Regenerate dotfiles from an existing dotmaster.yaml
  add       Add / regenerate a single plugin
  list      Show all available plugins
  profile   Apply or inspect a preset profile
  validate  Check dotmaster.yaml for inconsistencies
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from dotmaster import __version__

app = typer.Typer(
    name="dotmaster",
    help=(
        "[bold magenta]dotmaster[/bold magenta] — "
        "Interactive dotfile generator and manager.\n\n"
        "Run [bold]dotmaster init[/bold] to get started."
    ),
    rich_markup_mode="rich",
    add_completion=True,
)

console = Console()
err_console = Console(stderr=True, style="bold red")


# ---------------------------------------------------------------------------
# Root callback — provides --version at the app level
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def root_callback(
    ctx: typer.Context,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version", "-v",
            help="Show version and exit.",
            is_eager=True,
        ),
    ] = None,
) -> None:
    """dotmaster — Interactive dotfile generator and manager."""
    if version:
        console.print(f"dotmaster v{__version__}")
        raise typer.Exit()
    # No subcommand and no --version → show help
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_generation(
    config,
    output_dir: Path,
    *,
    single_plugin: str | None = None,
) -> None:
    """Run active plugins and persist generated-file metadata to config."""
    from dotmaster.config import save_config
    from dotmaster.plugins import registry

    config_path = output_dir / "dotmaster.yaml"

    if single_plugin:
        plugin = registry.get(single_plugin)
        if plugin is None:
            err_console.print(f"Unknown plugin: '{single_plugin}'")
            raise typer.Exit(1)
        plugins_to_run = [plugin]
    else:
        plugins_to_run = registry.active(config)

    if not plugins_to_run:
        console.print("[yellow]No plugins matched your configuration.[/yellow]")
        return

    console.print()
    generated_paths: list[Path] = []

    for plugin in plugins_to_run:
        console.print(f"  [dim]→[/dim]  [bold]{plugin.name}[/bold]  [dim]{plugin.description}[/dim]")
        try:
            paths = plugin.run(config, output_dir)
            for p in paths:
                rel = p.relative_to(output_dir)
                console.print(f"       [green]✓[/green]  {rel}")
                config.record_generated(rel, plugin.name)
                generated_paths.append(p)
        except Exception as exc:
            console.print(f"       [red]✗[/red]  {exc}")

    save_config(config, config_path)
    console.print()
    console.print(
        f"  [bold green]Done![/bold green] "
        f"Generated [bold]{len(generated_paths)}[/bold] file(s). "
        f"Config saved to [bold]{config_path.name}[/bold]."
    )
    console.print()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def init(
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o",
            help="Target directory (defaults to current directory).",
            file_okay=False,
            dir_okay=True,
            writable=True,
            resolve_path=True,
        ),
    ] = Path("."),
    preset: Annotated[
        Optional[str],
        typer.Option(
            "--preset", "-p",
            help="Skip profile selection and apply this preset directly.",
        ),
    ] = None,
) -> None:
    """
    [bold]Initialize[/bold] a project: run the wizard and generate dotfiles.

    Creates [bold]dotmaster.yaml[/bold] and all selected config files
    in the target directory.
    """
    from dotmaster.config import config_exists, load_config, save_config
    from dotmaster.wizard import run_wizard

    output.mkdir(parents=True, exist_ok=True)

    if config_exists(output):
        overwrite = typer.confirm(
            f"dotmaster.yaml already exists in {output}. Overwrite settings?",
            default=False,
        )
        if not overwrite:
            console.print(
                "  Keeping existing config. "
                "Use [bold]dotmaster sync[/bold] to regenerate files."
            )
            raise typer.Exit()

    try:
        config = run_wizard(preset_profile=preset, output_dir=output)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Aborted.[/yellow]")
        raise typer.Exit()

    _run_generation(config, output)


@app.command()
def sync(
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o",
            help="Project directory containing dotmaster.yaml.",
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path("."),
) -> None:
    """
    [bold]Sync[/bold]: regenerate all dotfiles from [bold]dotmaster.yaml[/bold].

    Useful after manually editing dotmaster.yaml or after a dotmaster upgrade.
    """
    from dotmaster.config import load_config

    try:
        config = load_config(output / "dotmaster.yaml")
    except FileNotFoundError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1)

    console.print(
        f"\n  [bold magenta]dotmaster sync[/bold magenta]  [dim]{output}[/dim]\n"
    )
    _run_generation(config, output)


@app.command(name="add")
def add_plugin(
    plugin_name: Annotated[
        str,
        typer.Argument(help="Plugin name (e.g. docker, eslint, github_actions)."),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o",
            help="Project directory containing dotmaster.yaml.",
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path("."),
) -> None:
    """
    [bold]Add[/bold] or regenerate a single plugin's dotfiles.

    Reads [bold]dotmaster.yaml[/bold] for context, then runs only the specified plugin.
    """
    from dotmaster.config import load_config

    try:
        config = load_config(output / "dotmaster.yaml")
    except FileNotFoundError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1)

    console.print(
        f"\n  [bold magenta]dotmaster add[/bold magenta] [bold]{plugin_name}[/bold]\n"
    )
    _run_generation(config, output, single_plugin=plugin_name)


@app.command(name="list")
def list_plugins() -> None:
    """
    [bold]List[/bold] all available plugins.

    Shows which plugins are built-in and what files each one generates.
    """
    from dotmaster.plugins import registry

    plugins = registry.all()

    table = Table(
        title="Available plugins",
        show_header=True,
        header_style="bold magenta",
        border_style="dim",
        show_lines=False,
    )
    table.add_column("Plugin", style="bold", min_width=20)
    table.add_column("Description")
    table.add_column("Trigger condition(s)", style="dim")

    for plugin in plugins:
        table.add_row(
            plugin.name,
            plugin.description,
            "\n".join(plugin.triggers) or "[italic dim]always[/italic dim]",
        )

    console.print()
    console.print(table)
    console.print(
        "\n  Run [bold]dotmaster add <plugin>[/bold] to generate a single plugin's files.\n"
    )


@app.command()
def profile(
    name: Annotated[
        Optional[str],
        typer.Argument(help="Profile name to inspect or apply."),
    ] = None,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Apply the profile to the existing dotmaster.yaml."),
    ] = False,
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o",
            help="Project directory (used with --apply).",
            resolve_path=True,
        ),
    ] = Path("."),
) -> None:
    """
    [bold]Inspect[/bold] or [bold]apply[/bold] a preset profile.

    Without --apply, shows what a profile would configure.
    With --apply, merges the profile defaults into dotmaster.yaml.
    """
    from dotmaster.profiles import get_profile, list_profiles

    if name is None:
        # Show all profiles
        profiles = list_profiles()
        table = Table(
            title="Preset profiles",
            show_header=True,
            header_style="bold magenta",
            border_style="dim",
        )
        table.add_column("Name", style="bold", min_width=14)
        table.add_column("Description")
        for n, desc in profiles:
            table.add_row(n, desc)
        console.print()
        console.print(table)
        console.print(
            "\n  Run [bold]dotmaster profile <name>[/bold] to inspect a profile.\n"
        )
        return

    data = get_profile(name)
    if data is None:
        err_console.print(f"Unknown profile: '{name}'")
        raise typer.Exit(1)

    # Print profile contents
    import yaml

    console.print(
        Panel(
            yaml.dump(data, default_flow_style=False).strip(),
            title=f"[bold magenta]{name}[/bold magenta] profile",
            border_style="magenta",
            expand=False,
        )
    )

    if apply:
        from dotmaster.config import load_config, save_config

        try:
            config = load_config(output / "dotmaster.yaml")
        except FileNotFoundError as exc:
            err_console.print(str(exc))
            raise typer.Exit(1)

        # Merge profile into config (profile is the default; existing wins on conflict)
        s = data.get("stack", {})
        q = data.get("quality", {})
        i = data.get("infrastructure", {})

        if s.get("languages"):
            config.stack.languages = config.stack.languages or s["languages"]
        if s.get("framework") and config.stack.framework == "none":
            config.stack.framework = s["framework"]
        if s.get("package_manager") and config.stack.package_manager == "none":
            config.stack.package_manager = s["package_manager"]
        if q.get("linter") and config.quality.linter == "none":
            config.quality.linter = q["linter"]
        if q.get("formatter") and config.quality.formatter == "none":
            config.quality.formatter = q["formatter"]
        if q.get("testing") and config.quality.testing == "none":
            config.quality.testing = q["testing"]
        config.profile = name

        save_config(config, output / "dotmaster.yaml")
        console.print(
            f"\n  [green]✓[/green] Profile [bold]{name}[/bold] merged into dotmaster.yaml.\n"
            "  Run [bold]dotmaster sync[/bold] to regenerate files."
        )


@app.command()
def validate(
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o",
            help="Project directory containing dotmaster.yaml.",
            resolve_path=True,
        ),
    ] = Path("."),
) -> None:
    """
    [bold]Validate[/bold] dotmaster.yaml for configuration inconsistencies.
    """
    from dotmaster.config import load_config

    try:
        config = load_config(output / "dotmaster.yaml")
    except FileNotFoundError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1)

    issues: list[str] = []

    # Rule: ESLint requires a JS/TS language
    if config.quality.linter == "eslint" and not any(
        l in config.stack.languages for l in ("javascript", "typescript")
    ):
        issues.append(
            "Linter is 'eslint' but no JavaScript/TypeScript language is selected."
        )

    # Rule: Ruff requires Python
    if config.quality.linter == "ruff" and "python" not in config.stack.languages:
        issues.append(
            "Linter is 'ruff' but 'python' is not in the selected languages."
        )

    # Rule: Prettier requires JS/TS
    if config.quality.formatter == "prettier" and not any(
        l in config.stack.languages for l in ("javascript", "typescript")
    ):
        issues.append(
            "Formatter is 'prettier' but no JavaScript/TypeScript language is selected."
        )

    # Rule: Pytest requires Python
    if config.quality.testing == "pytest" and "python" not in config.stack.languages:
        issues.append(
            "Testing is 'pytest' but 'python' is not in the selected languages."
        )

    # Rule: Jest/Vitest require JS/TS
    if config.quality.testing in ("jest", "vitest") and not any(
        l in config.stack.languages for l in ("javascript", "typescript")
    ):
        issues.append(
            f"Testing is '{config.quality.testing}' but no JS/TS language is selected."
        )

    # Rule: multi-stage Docker without Docker enabled
    if config.infrastructure.docker_multistage and not config.infrastructure.docker:
        issues.append(
            "docker_multistage is True but docker is False."
        )

    console.print()
    if issues:
        console.print(
            f"  [bold red]Found {len(issues)} issue(s) in dotmaster.yaml:[/bold red]\n"
        )
        for i, issue in enumerate(issues, 1):
            console.print(f"  {i}. [yellow]{issue}[/yellow]")
        console.print()
        raise typer.Exit(1)
    else:
        console.print(
            "  [bold green]✓ dotmaster.yaml is valid![/bold green]\n"
        )


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
