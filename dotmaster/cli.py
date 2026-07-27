"""
dotmaster/cli.py
Entry point: defines every `dotmaster` command with Typer.

Commands
--------
  init      Run the wizard (or --yes/--set) and generate dotfiles
  sync      Regenerate dotfiles from dotmaster.yaml
  add       Add / regenerate one plugin
  remove    Delete a plugin's generated files
  diff      Show what sync would change, without changing anything
  check     CI mode: exit non-zero if the project has drifted
  restore   Restore files from a pre-generation backup
  list      Show available plugins
  profile   Inspect or apply a preset profile
  validate  Check dotmaster.yaml for problems
  doctor    Report on the detected stack, plugins and config health
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dotmaster import __version__

logger = logging.getLogger("dotmaster")

app = typer.Typer(
    name="dotmaster",
    help=(
        "[bold magenta]dotmaster[/bold magenta] — "
        "Interactive dotfile generator and manager.\n\n"
        "Run [bold]dotmaster init[/bold] to get started."
    ),
    rich_markup_mode="rich",
    add_completion=True,
    pretty_exceptions_show_locals=False,
)
profile_app = typer.Typer(
    name="profile", help="Inspect or apply a preset profile.", rich_markup_mode="rich"
)
app.add_typer(profile_app, name="profile")

console = Console()
err_console = Console(stderr=True, style="bold red")

OutputOption = Annotated[
    Path,
    typer.Option(
        "--output",
        "-o",
        help="Project directory (defaults to the current directory).",
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
]
YesOption = Annotated[bool, typer.Option("--yes", "-y", help="Accept every default; never prompt.")]
DryRunOption = Annotated[
    bool, typer.Option("--dry-run", "-n", help="Show what would change, without writing anything.")
]
ForceOption = Annotated[
    bool,
    typer.Option(
        "--force", help="Overwrite files even if they were modified since dotmaster generated them."
    ),
]
OfflineOption = Annotated[
    bool | None,
    typer.Option(
        "--offline/--online", help="Override the offline setting in dotmaster.yaml for this run."
    ),
]
JsonOption = Annotated[bool, typer.Option("--json", help="Machine-readable output.")]
SetOption = Annotated[
    list[str] | None,
    typer.Option(
        "--set", help="Override a setting, e.g. --set stack.framework=nextjs. Repeatable."
    ),
]


# ---------------------------------------------------------------------------
# Root callback
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def root_callback(
    ctx: typer.Context,
    version: Annotated[
        bool | None, typer.Option("--version", "-V", help="Show version and exit.", is_eager=True)
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable debug logging.", is_eager=True)
    ] = False,
    log_file: Annotated[
        Path | None,
        typer.Option(
            "--log-file", help="Write debug logs here instead of the platform log directory."
        ),
    ] = None,
) -> None:
    """dotmaster — Interactive dotfile generator and manager."""
    _configure_logging(verbose=verbose, log_file=log_file)

    if version:
        console.print(f"dotmaster v{__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


def _configure_logging(*, verbose: bool, log_file: Path | None) -> None:
    """
    Log to the platform state directory, not the project directory.

    The handler is attached to the ``dotmaster`` logger only (not the root
    logger) and created lazily, so `dotmaster --version` touches nothing on
    disk and third-party library logs never leak into it.
    """
    dm_logger = logging.getLogger("dotmaster")
    dm_logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
    dm_logger.propagate = False
    if dm_logger.handlers:
        return

    if log_file is None:
        try:
            import platformdirs

            log_dir = Path(platformdirs.user_state_dir("dotmaster"))
        except ImportError:  # pragma: no cover - platformdirs is a dependency
            log_dir = Path.home() / ".dotmaster"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "dotmaster.log"

    try:
        handler = logging.FileHandler(log_file, encoding="utf-8")
    except OSError:
        return  # a read-only environment must not crash the whole CLI
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    dm_logger.addHandler(handler)
    if verbose:
        console.print(f"[dim]Verbose logging enabled → {log_file}[/dim]")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_config_or_exit(output: Path):
    from dotmaster.config import ConfigError, load_config

    try:
        return load_config(output / "dotmaster.yaml")
    except ConfigError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from None


def _discover_or_warn(config, output: Path):
    from dotmaster.plugins import discover

    registry, warnings = discover(config, output)
    for warning in warnings:
        console.print(f"  [yellow]![/yellow] {warning}")
    return registry


def _kind_style(kind) -> tuple[str, str]:
    from dotmaster.core.plan import ChangeKind

    return {
        ChangeKind.CREATE: ("green", "+"),
        ChangeKind.UPDATE: ("yellow", "~"),
        ChangeKind.CONFLICT: ("red", "!"),
        ChangeKind.SKIP: ("dim", "·"),
        ChangeKind.UNCHANGED: ("dim", "="),
    }[kind]


def _render_plan(plan, *, show_unchanged: bool = False) -> None:
    from dotmaster.core.plan import ChangeKind

    if plan.errors:
        console.print("  [bold red]Plugin errors:[/bold red]")
        for name, message in plan.errors.items():
            console.print(f"    [red]✗[/red] {name}: {message}")
        console.print()

    if plan.conflicts:
        console.print("  [bold yellow]Conflicts between plugins:[/bold yellow]")
        for conflict in plan.conflicts:
            console.print(f"    [yellow]![/yellow] {conflict.detail}")
        console.print()

    for change in plan.changes:
        if change.kind is ChangeKind.UNCHANGED and not show_unchanged:
            continue
        style, mark = _kind_style(change.kind)
        added, removed = change.stat if change.kind is ChangeKind.UPDATE else (0, 0)
        suffix = f"  [dim]+{added} -{removed}[/dim]" if change.kind is ChangeKind.UPDATE else ""
        reason = f"  [dim]({change.reason})[/dim]" if change.reason else ""
        console.print(f"  [{style}]{mark}[/{style}]  {change.path}{suffix}{reason}")

    if plan.blocked:
        console.print()
        console.print(
            f"  [yellow]{len(plan.blocked)} file(s) need attention "
            "— re-run with --force to overwrite, or resolve by hand.[/yellow]"
        )


def _resolve_plugins(registry, single_plugin: str | None, config):
    if single_plugin is None:
        return registry.active(config), []
    plugin = registry.get(single_plugin)
    if plugin is None:
        suggestion = registry.suggest(single_plugin)
        hint = f" Did you mean '{suggestion}'?" if suggestion else ""
        err_console.print(f"Unknown plugin: '{single_plugin}'.{hint}")
        err_console.print("Run 'dotmaster list' to see all available plugins.")
        raise typer.Exit(1)
    warnings = []
    if not plugin.matches(config):
        warnings.append(
            f"'{single_plugin}' is not active for this configuration — generating anyway."
        )
    return [plugin], warnings


def _run(
    config,
    output: Path,
    *,
    single_plugin: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    offline: bool | None = None,
) -> None:
    from dotmaster.config import save_config
    from dotmaster.core.apply import ApplyError, apply_plan
    from dotmaster.core.engine import build_plan

    registry = _discover_or_warn(config, output)
    plugins, warnings = _resolve_plugins(registry, single_plugin, config)
    for warning in warnings:
        console.print(f"  [yellow]![/yellow] {warning}")

    if not plugins:
        console.print("[yellow]No plugins matched your configuration.[/yellow]")
        return

    plan = build_plan(config, output, plugins, force=force, offline=offline)
    console.print()
    _render_plan(plan)
    console.print()

    if plan.is_noop and not plan.blocked and not plan.errors:
        console.print("  [dim]Already up to date.[/dim]\n")
        return

    if dry_run:
        console.print("  [dim]Dry run — nothing was written.[/dim]\n")
        return

    try:
        result = apply_plan(
            plan, output, backup=config.options.backup, keep_backups=config.options.keep_backups
        )
    except ApplyError as exc:
        err_console.print(f"Apply failed and was rolled back: {exc}")
        raise typer.Exit(1) from None

    if result.backup:
        console.print(f"  [dim]Backup saved to {result.backup.relative_to(output)}[/dim]")

    save_config(config, output / "dotmaster.yaml")

    for plugin in plugins:
        try:
            from dotmaster.plugins.api import Context

            plugin.post_apply(
                config, Context(root=output, config=config, offline=config.options.offline)
            )
        except Exception as exc:
            logger.exception("Plugin %s failed during post_apply", plugin.name)
            console.print(f"  [yellow]⚠[/yellow]  {plugin.name} post-apply hook failed: {exc}")

    console.print(
        f"  [bold green]Done![/bold green] "
        f"{result.written} file(s) written"
        f"{f', {len(result.blocked)} need attention' if result.blocked else ''}. "
        f"Config saved to [bold]dotmaster.yaml[/bold].\n"
    )


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@app.command()
def init(
    output: OutputOption = Path("."),
    preset: Annotated[
        str | None,
        typer.Option("--preset", "-p", help="Skip profile selection and use this preset."),
    ] = None,
    yes: YesOption = False,
    set_: SetOption = None,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
    offline: OfflineOption = None,
) -> None:
    """
    [bold]Initialize[/bold] a project: run the wizard and generate dotfiles.

    Non-interactive: [bold]dotmaster init --preset backend_api --yes[/bold]
    """
    from dotmaster.config import ConfigError, apply_overrides, config_exists
    from dotmaster.prompts import DefaultPrompter, InquirerPrompter
    from dotmaster.wizard import WizardAborted, run_wizard

    output.mkdir(parents=True, exist_ok=True)

    if (
        config_exists(output)
        and not yes
        and not typer.confirm(
            f"dotmaster.yaml already exists in {output}. Overwrite settings?", default=False
        )
    ):
        console.print(
            "  Keeping existing config. Use [bold]dotmaster sync[/bold] to regenerate files."
        )
        raise typer.Exit()

    interactive = not yes and sys.stdin.isatty()
    prompter = InquirerPrompter() if interactive else DefaultPrompter()
    if not interactive and not yes:
        console.print(
            "[yellow]No interactive terminal detected — using defaults. "
            "Pass --yes to silence this message.[/yellow]\n"
        )

    try:
        config = run_wizard(prompter, preset_profile=preset, output_dir=output)
    except WizardAborted:
        console.print("\n[yellow]Aborted.[/yellow]")
        raise typer.Exit() from None
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Aborted.[/yellow]")
        raise typer.Exit() from None

    if set_:
        try:
            config = apply_overrides(config, set_)
        except ConfigError as exc:
            err_console.print(str(exc))
            raise typer.Exit(1) from None

    _run(config, output, dry_run=dry_run, force=force, offline=offline)


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------


@app.command()
def sync(
    output: OutputOption = Path("."),
    dry_run: DryRunOption = False,
    force: ForceOption = False,
    offline: OfflineOption = None,
    only: Annotated[
        str | None,
        typer.Option("--only", help="Comma-separated plugin names to run (default: all active)."),
    ] = None,
) -> None:
    """
    [bold]Sync[/bold]: regenerate dotfiles from [bold]dotmaster.yaml[/bold].

    Safe to run repeatedly — unchanged files are left alone, and files you've
    edited since the last generation are reported, never silently clobbered.
    """
    config = _load_config_or_exit(output)
    console.print(f"\n  [bold magenta]dotmaster sync[/bold magenta]  [dim]{output}[/dim]")

    if only:
        registry = _discover_or_warn(config, output)
        names = [n.strip() for n in only.split(",") if n.strip()]
        plugins, unknown = registry.select(names)
        for name in unknown:
            err_console.print(f"Unknown plugin: '{name}'")
        if unknown:
            raise typer.Exit(1)
        from dotmaster.core.apply import apply_plan
        from dotmaster.core.engine import build_plan

        plan = build_plan(config, output, plugins, force=force, offline=offline)
        console.print()
        _render_plan(plan)
        console.print()
        if not dry_run and plan.writes:
            apply_plan(
                plan, output, backup=config.options.backup, keep_backups=config.options.keep_backups
            )
            from dotmaster.config import save_config

            save_config(config, output / "dotmaster.yaml")
        return

    _run(config, output, dry_run=dry_run, force=force, offline=offline)


# ---------------------------------------------------------------------------
# add / remove
# ---------------------------------------------------------------------------


@app.command(name="add")
def add_plugin(
    plugin_name: Annotated[
        str, typer.Argument(help="Plugin name, e.g. docker, eslint, github_actions.")
    ],
    output: OutputOption = Path("."),
    dry_run: DryRunOption = False,
    force: ForceOption = False,
) -> None:
    """[bold]Add[/bold] or regenerate a single plugin's dotfiles."""
    config = _load_config_or_exit(output)
    console.print(f"\n  [bold magenta]dotmaster add[/bold magenta] [bold]{plugin_name}[/bold]")
    _run(config, output, single_plugin=plugin_name, dry_run=dry_run, force=force)


@app.command(name="remove")
def remove_plugin(
    plugin_name: Annotated[
        str, typer.Argument(help="Plugin whose generated files should be deleted.")
    ],
    output: OutputOption = Path("."),
    yes: YesOption = False,
) -> None:
    """
    [bold]Remove[/bold] a plugin's generated files.

    Only deletes files dotmaster's ledger says this plugin owns and that are
    still byte-identical to what was generated — files you've since edited are
    left in place and reported instead.
    """
    from dotmaster.core.state import load_state, save_state

    state = load_state(output)
    owned = state.paths_for_plugin(plugin_name)
    if not owned:
        console.print(f"[yellow]No tracked files belong to '{plugin_name}'.[/yellow]")
        raise typer.Exit()

    console.print(f"\n  Files owned by [bold]{plugin_name}[/bold]:")
    for path in owned:
        console.print(f"    {path}")
    if not yes and not typer.confirm(f"\nDelete these {len(owned)} file(s)?", default=False):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit()

    from dotmaster.core.engine import safe_target
    from dotmaster.core.plan import sha256

    removed, kept = [], []
    for rel in owned:
        target = safe_target(output, rel)
        if target is None:
            logger.warning("Refusing to remove out-of-tree path from state ledger: %s", rel)
            state.forget(rel)
            continue
        record = state.record_for(rel)
        try:
            current = target.read_text(encoding="utf-8") if target.exists() else None
        except (OSError, UnicodeDecodeError):
            current = None

        if current is None:
            state.forget(rel)
            continue
        if record and sha256(current) == record.generated_sha256:
            target.unlink()
            state.forget(rel)
            removed.append(rel)
        else:
            kept.append(rel)

    save_state(state, output)
    for rel in removed:
        console.print(f"  [green]✓[/green] removed {rel}")
    for rel in kept:
        console.print(f"  [yellow]![/yellow] kept {rel} (modified since it was generated)")


# ---------------------------------------------------------------------------
# diff / check
# ---------------------------------------------------------------------------


@app.command()
def diff(output: OutputOption = Path("."), offline: OfflineOption = None) -> None:
    """[bold]Diff[/bold]: show what `sync` would change, without changing anything."""
    from dotmaster.core.engine import build_plan
    from dotmaster.core.plan import ChangeKind

    config = _load_config_or_exit(output)
    registry = _discover_or_warn(config, output)
    plan = build_plan(config, output, registry.active(config), offline=offline)

    if plan.is_clean:
        console.print("\n  [green]Up to date.[/green] No drift from dotmaster.yaml.\n")
        return

    console.print()
    for change in plan.changes:
        if change.kind in (ChangeKind.UNCHANGED, ChangeKind.SKIP):
            continue
        style, mark = _kind_style(change.kind)
        console.print(f"[{style}]{mark} {change.path}[/{style}]")
        body = change.diff()
        if body:
            for line in body.splitlines():
                color = (
                    "green" if line.startswith("+") else "red" if line.startswith("-") else "dim"
                )
                console.print(f"  [{color}]{line}[/{color}]")
        console.print()
    _render_plan(plan)
    console.print()


@app.command()
def check(
    output: OutputOption = Path("."), quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False
) -> None:
    """
    [bold]Check[/bold] for drift; exits non-zero if the project needs `sync`.

    Designed for CI:  `dotmaster check` in a pipeline fails the build the
    moment generated config falls out of sync with dotmaster.yaml.
    """
    from dotmaster.core.engine import build_plan

    try:
        config = _load_config_or_exit(output)
    except typer.Exit:
        raise
    registry = _discover_or_warn(config, output)
    plan = build_plan(config, output, registry.active(config))

    if plan.is_clean:
        if not quiet:
            console.print("[green]✓ up to date[/green]")
        raise typer.Exit(0)

    if not quiet:
        _render_plan(plan)
        console.print(
            "\n[red]✗ drift detected[/red] — run [bold]dotmaster sync[/bold] to fix, "
            "or [bold]dotmaster diff[/bold] to inspect.\n"
        )
    raise typer.Exit(1)


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------


@app.command()
def restore(
    output: OutputOption = Path("."),
    list_only: Annotated[
        bool, typer.Option("--list", help="List available backups and exit.")
    ] = False,
    at: Annotated[
        str | None, typer.Option("--at", help="Backup filename to restore (see --list).")
    ] = None,
    yes: YesOption = False,
) -> None:
    """[bold]Restore[/bold] files from a pre-generation backup."""
    from dotmaster.core.apply import list_backups, restore_backup

    backups = list_backups(output)
    if not backups:
        console.print("[yellow]No backups found.[/yellow]")
        raise typer.Exit()

    if list_only or at is None:
        console.print("\n  Available backups (newest last):\n")
        for backup in backups:
            console.print(f"    {backup.name}")
        if at is None:
            console.print("\n  Run [bold]dotmaster restore --at <name>[/bold] to restore one.\n")
        if list_only:
            return

    target = next((b for b in backups if b.name == at), None)
    if target is None:
        err_console.print(f"No backup named '{at}'. Run 'dotmaster restore --list'.")
        raise typer.Exit(1)

    if not yes and not typer.confirm(
        f"Restore files from {target.name}? This overwrites the current files.", default=False
    ):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit()

    restored = restore_backup(target, output)
    for path in restored:
        console.print(f"  [green]✓[/green] restored {path}")
    console.print(f"\n  [bold green]Restored {len(restored)} file(s).[/bold green]\n")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@app.command(name="list")
def list_plugins(output: OutputOption = Path(".")) -> None:
    """[bold]List[/bold] all available plugins."""
    from dotmaster.config import config_exists, load_config
    from dotmaster.plugins import discover

    config = load_config(output / "dotmaster.yaml") if config_exists(output) else None
    registry, warnings = discover(config, output)
    for warning in warnings:
        console.print(f"  [yellow]![/yellow] {warning}")
    active_names = {p.name for p in registry.active(config)} if config else set()

    table = Table(
        title="Available plugins", show_header=True, header_style="bold magenta", border_style="dim"
    )
    table.add_column("Plugin", style="bold", min_width=16)
    table.add_column("Source", style="dim", min_width=10)
    table.add_column("Description")
    if config is not None:
        table.add_column("Active", justify="center")

    for plugin in registry.all():
        row = [plugin.name, registry.source_of(plugin.name), plugin.description]
        if config is not None:
            row.append("[green]✓[/green]" if plugin.name in active_names else "[dim]·[/dim]")
        table.add_row(*row)

    console.print()
    console.print(table)
    console.print(
        "\n  Run [bold]dotmaster add <plugin>[/bold] to generate a single plugin's files.\n"
    )


# ---------------------------------------------------------------------------
# profile
# ---------------------------------------------------------------------------


@profile_app.command("list")
def profile_list() -> None:
    """List every preset profile."""
    from dotmaster.profiles import list_profiles

    table = Table(
        title="Preset profiles", show_header=True, header_style="bold magenta", border_style="dim"
    )
    table.add_column("Name", style="bold", min_width=14)
    table.add_column("Description")
    for name, desc in list_profiles():
        table.add_row(name, desc)
    console.print()
    console.print(table)
    console.print("\n  Run [bold]dotmaster profile show <name>[/bold] to inspect one.\n")


@profile_app.command("show")
def profile_show(name: Annotated[str, typer.Argument()]) -> None:
    """Show what a profile would configure."""
    import yaml

    from dotmaster.profiles import get_profile

    data = get_profile(name)
    if data is None:
        err_console.print(f"Unknown profile: '{name}'")
        raise typer.Exit(1)
    console.print(
        Panel(
            yaml.dump(data, default_flow_style=False).strip(),
            title=f"[bold magenta]{name}[/bold magenta] profile",
            border_style="magenta",
            expand=False,
        )
    )


@profile_app.command("apply")
def profile_apply(
    name: Annotated[str, typer.Argument()],
    output: OutputOption = Path("."),
) -> None:
    """Merge a profile's defaults into the existing dotmaster.yaml (your settings win)."""
    from dotmaster.config import save_config
    from dotmaster.profiles import get_profile

    data = get_profile(name)
    if data is None:
        err_console.print(f"Unknown profile: '{name}'")
        raise typer.Exit(1)

    config = _load_config_or_exit(output)
    merged = _merge_profile(config, data)
    merged.profile = name
    save_config(merged, output / "dotmaster.yaml")
    console.print(
        f"\n  [green]✓[/green] Profile [bold]{name}[/bold] merged into dotmaster.yaml.\n"
        "  Run [bold]dotmaster sync[/bold] to regenerate files.\n"
    )


def _merge_profile(config, profile_data: dict):
    """Fill unset fields from *profile_data*; anything the user already set wins."""
    current = config.to_dict()
    for section, defaults in profile_data.items():
        if section not in current or not isinstance(defaults, dict):
            continue
        target = current[section]
        for key, value in defaults.items():
            existing = target.get(key)
            is_unset = existing in (None, "", "none", False, [])
            if is_unset and value not in (None, "", [], False):
                target[key] = value
    from dotmaster.config import DotmasterConfig

    return DotmasterConfig.model_validate(current)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@app.command()
def validate(output: OutputOption = Path(".")) -> None:
    """[bold]Validate[/bold] dotmaster.yaml — schema plus cross-field consistency rules."""
    config = _load_config_or_exit(output)  # schema errors raise here already

    q, s, i = config.quality, config.stack, config.infrastructure
    has_js = any(lang in s.languages for lang in ("javascript", "typescript"))

    rules: list[tuple[bool, str]] = [
        (
            q.linter == "eslint" and not has_js,
            "linter is 'eslint' but no JavaScript/TypeScript language is selected",
        ),
        (
            q.linter == "ruff" and "python" not in s.languages,
            "linter is 'ruff' but 'python' is not selected",
        ),
        (
            q.formatter == "prettier" and not has_js,
            "formatter is 'prettier' but no JavaScript/TypeScript language is selected",
        ),
        (
            q.testing == "pytest" and "python" not in s.languages,
            "testing is 'pytest' but 'python' is not selected",
        ),
        (
            q.testing in ("jest", "vitest") and not has_js,
            f"testing is '{q.testing}' but no JavaScript/TypeScript language is selected",
        ),
        (i.docker_multistage and not i.docker, "docker_multistage is true but docker is false"),
        (
            config.database.migrations == "alembic" and config.database.orm != "sqlalchemy",
            "migrations is 'alembic' but orm is not 'sqlalchemy'",
        ),
        (
            config.database.migrations == "prisma" and config.database.orm != "prisma",
            "migrations is 'prisma' but orm is not 'prisma'",
        ),
    ]
    issues = [message for broken, message in rules if broken]

    console.print()
    if issues:
        console.print(f"  [bold red]Found {len(issues)} issue(s) in dotmaster.yaml:[/bold red]\n")
        for i_, issue in enumerate(issues, 1):
            console.print(f"  {i_}. [yellow]{issue}[/yellow]")
        console.print()
        raise typer.Exit(1)
    console.print("  [bold green]✓ dotmaster.yaml is valid![/bold green]\n")


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@app.command()
def doctor(output: OutputOption = Path(".")) -> None:
    """[bold]Doctor[/bold]: report on the detected stack, plugins and config health."""
    from dotmaster.config import ConfigError, config_exists, load_config
    from dotmaster.plugins import discover
    from dotmaster.runner import command_exists

    console.print(f"\n  [bold magenta]dotmaster doctor[/bold magenta]  [dim]v{__version__}[/dim]\n")

    console.print("  [bold]Config[/bold]")
    config = None
    if not config_exists(output):
        console.print("    [yellow]![/yellow] no dotmaster.yaml — run 'dotmaster init'")
    else:
        try:
            config = load_config(output / "dotmaster.yaml")
            console.print("    [green]✓[/green] dotmaster.yaml is valid")
        except ConfigError as exc:
            console.print(f"    [red]✗[/red] {exc}")

    console.print("\n  [bold]Detected tools on PATH[/bold]")
    for tool in (
        "git",
        "node",
        "npm",
        "pnpm",
        "yarn",
        "python3",
        "poetry",
        "uv",
        "docker",
        "go",
        "cargo",
    ):
        found = command_exists(tool)
        mark = "[green]✓[/green]" if found else "[dim]·[/dim]"
        console.print(f"    {mark} {tool}")

    console.print("\n  [bold]Plugins[/bold]")
    registry, warnings = discover(config, output)
    console.print(
        f"    {len(registry.all())} loaded ({', '.join(sorted({registry.source_of(n) for n in registry.names()}))})"
    )
    for warning in warnings:
        console.print(f"    [yellow]![/yellow] {warning}")

    if config is not None:
        from dotmaster.core.engine import build_plan

        plan = build_plan(config, output, registry.active(config))
        console.print("\n  [bold]Drift[/bold]")
        if plan.is_clean:
            console.print("    [green]✓[/green] up to date")
        else:
            console.print(
                f"    [yellow]![/yellow] {len(plan.writes)} file(s) would change, "
                f"{len(plan.blocked)} conflict(s) — run 'dotmaster diff' for details"
            )
    console.print()


if __name__ == "__main__":
    app()
