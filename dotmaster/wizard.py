"""
dotmaster/wizard.py
The guided Q&A that produces a DotmasterConfig.

All actual I/O goes through a :class:`~dotmaster.prompts.Prompter`, so the
wizard itself is pure and testable: swap in a ``ScriptedPrompter`` for tests,
or a ``DefaultPrompter`` for ``dotmaster init --yes`` / CI, with no branching
in this module at all.
"""

from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from dotmaster import __version__
from dotmaster.config import DotmasterConfig
from dotmaster.profiles import get_profile
from dotmaster.prompts import Choice, Prompter

console = Console()


class WizardAborted(Exception):  # noqa: N818 - a deliberate stop, not an error
    """The user declined to proceed — not an error, just a stop."""


# ---------------------------------------------------------------------------
# Dynamic choice helpers
# ---------------------------------------------------------------------------


def _framework_choices(languages: list[str]) -> list[Choice]:
    choices: list[Choice] = []
    if any(lang in languages for lang in ("javascript", "typescript")):
        choices += [
            Choice("nextjs", "Next.js"),
            Choice("react", "React (Vite)"),
            Choice("vue", "Vue 3"),
            Choice("angular", "Angular"),
            Choice("express", "Express"),
            Choice("fastify", "Fastify"),
        ]
    if "python" in languages:
        choices += [
            Choice("fastapi", "FastAPI"),
            Choice("django", "Django"),
            Choice("flask", "Flask"),
        ]
    if "go" in languages:
        choices += [Choice("gin", "Gin"), Choice("echo", "Echo"), Choice("fiber", "Fiber")]
    choices.append(Choice("none", "None / plain"))
    return choices


def _pm_choices(languages: list[str]) -> list[Choice]:
    choices: list[Choice] = []
    if any(lang in languages for lang in ("javascript", "typescript")):
        choices += [
            Choice("npm", "npm"),
            Choice("pnpm", "pnpm (fast, disk-efficient)"),
            Choice("yarn", "Yarn"),
        ]
    if "python" in languages:
        choices += [
            Choice("poetry", "Poetry"),
            Choice("uv", "uv (ultra-fast)"),
            Choice("pip", "pip / requirements.txt"),
        ]
    if "go" in languages:
        choices.append(Choice("go_mod", "go mod"))
    if "rust" in languages:
        choices.append(Choice("cargo", "Cargo"))
    return choices or [Choice("none", "None")]


def _linter_choices(languages: list[str]) -> list[Choice]:
    choices: list[Choice] = []
    if any(lang in languages for lang in ("javascript", "typescript")):
        choices.append(Choice("eslint", "ESLint"))
    if "python" in languages:
        choices += [Choice("ruff", "Ruff"), Choice("flake8", "Flake8")]
    if "go" in languages:
        choices.append(Choice("golangci-lint", "golangci-lint"))
    choices.append(Choice("none", "None"))
    return choices


def _formatter_choices(languages: list[str]) -> list[Choice]:
    choices: list[Choice] = []
    if any(lang in languages for lang in ("javascript", "typescript")):
        choices.append(Choice("prettier", "Prettier"))
    if "python" in languages:
        choices += [Choice("black", "Black"), Choice("ruff", "Ruff (formatter mode)")]
    if "go" in languages:
        choices.append(Choice("gofmt", "gofmt"))
    choices.append(Choice("none", "None"))
    return choices


def _testing_choices(languages: list[str]) -> list[Choice]:
    choices: list[Choice] = []
    if any(lang in languages for lang in ("javascript", "typescript")):
        choices += [Choice("jest", "Jest"), Choice("vitest", "Vitest")]
    if "python" in languages:
        choices.append(Choice("pytest", "pytest"))
    if "go" in languages:
        choices.append(Choice("go_test", "go test (built-in)"))
    choices.append(Choice("none", "None"))
    return choices


def _orm_choices(languages: list[str]) -> list[Choice]:
    choices: list[Choice] = []
    if any(lang in languages for lang in ("javascript", "typescript")):
        choices += [
            Choice("prisma", "Prisma"),
            Choice("drizzle", "Drizzle"),
            Choice("typeorm", "TypeORM"),
            Choice("mongoose", "Mongoose"),
        ]
    if "python" in languages:
        choices += [
            Choice("sqlalchemy", "SQLAlchemy"),
            Choice("django_orm", "Django ORM"),
            Choice("tortoise", "Tortoise ORM"),
        ]
    choices.append(Choice("none", "None"))
    return choices


def _migration_choices(orm: str) -> list[Choice]:
    choices: list[Choice] = []
    if orm == "prisma":
        choices.append(Choice("prisma", "Prisma Migrate"))
    elif orm == "sqlalchemy":
        choices.append(Choice("alembic", "Alembic"))
    elif orm == "django_orm":
        choices.append(Choice("django", "Django Migrations"))
    elif orm == "tortoise":
        choices.append(Choice("aerich", "Aerich"))
    choices.append(Choice("none", "None"))
    return choices


def _default_value(choices: list[Choice], fallback: str) -> str:
    return choices[0].value if choices else fallback


def _with_preselection(choices: list[Choice], preselected: list[str]) -> list[Choice]:
    """
    Mark choices already in *preselected* as enabled.

    This is what a profile's answers actually pre-fill: InquirerPy's checkbox
    only positions the cursor from ``default``, it never pre-checks boxes —
    the ``enabled`` flag on each ``Choice`` is what does that.
    """
    wanted = set(preselected)
    return [Choice(c.value, c.label, enabled=c.value in wanted) for c in choices]


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------


def run_wizard(
    prompter: Prompter,
    *,
    preset_profile: str | None = None,
    output_dir: Path | None = None,
    show_banner: bool = True,
) -> DotmasterConfig:
    """
    Run the full guided Q&A and return a populated :class:`DotmasterConfig`.

    Every answer is asked through *prompter* — pass an ``InquirerPrompter``
    for a real terminal, a ``DefaultPrompter`` to accept every default
    silently, or a ``ScriptedPrompter`` in tests.
    """
    output_dir = output_dir or Path.cwd()

    if show_banner:
        banner = Text()
        banner.append("  dotmaster ", style="bold magenta")
        banner.append(f"v{__version__}", style="dim")
        banner.append("  ·  dotfile generator", style="dim")
        console.print(Panel(banner, border_style="magenta", expand=False, padding=(0, 2)))
        console.print()

    profile_data: dict = {}
    if preset_profile is None and prompter.confirm("Start from a preset profile?", default=False):
        profile_name = prompter.select(
            "Select a profile:",
            [
                Choice("web_app", "🌐  Web App — React/Next.js + ESLint + Docker + CI"),
                Choice("library", "📦  Library — ESLint + Jest, no Docker"),
                Choice("backend_api", "⚙️  Backend API — Python + Docker + CI"),
                Choice("monorepo", "🗂️  Monorepo — pnpm + ESLint + CI"),
                Choice("none", "✏️  Custom — answer everything manually"),
            ],
            default="none",
        )
        if profile_name != "none":
            preset_profile = profile_name
    if preset_profile:
        data = get_profile(preset_profile)
        if data:
            profile_data = data
            console.print(
                f"  [dim]Loaded profile:[/dim] [bold magenta]{preset_profile}[/bold magenta]"
                "  [dim](you can still change anything below)[/dim]\n"
            )
        else:
            console.print(
                f"  [yellow]Unknown profile '{preset_profile}'; starting blank.[/yellow]\n"
            )
            preset_profile = None

    def pd(section: str, key: str, fallback):
        return profile_data.get(section, {}).get(key, fallback)

    # ── Project ──────────────────────────────────────────────────────────
    console.print("[bold]  📁  Project[/bold]")
    default_name = output_dir.name
    name = prompter.text("Project name:", default=default_name) or default_name
    description = prompter.text("Description:", default="")
    default_author = os.environ.get("GIT_AUTHOR_NAME") or os.environ.get("USER") or ""
    author = prompter.text("Author:", default=default_author)
    console.print()

    # ── Stack ────────────────────────────────────────────────────────────
    console.print("[bold]  🛠️   Stack[/bold]")
    language_choices = _with_preselection(
        [
            Choice("javascript", "JavaScript"),
            Choice("typescript", "TypeScript"),
            Choice("python", "Python"),
            Choice("go", "Go"),
            Choice("rust", "Rust"),
            Choice("java", "Java"),
        ],
        pd("stack", "languages", []),
    )
    languages = prompter.checkbox("Language(s):", language_choices, required=True)

    fw_choices = _framework_choices(languages)
    framework = prompter.select(
        "Framework:",
        fw_choices,
        default=pd("stack", "framework", _default_value(fw_choices, "none")),
    )

    pm_choices = _pm_choices(languages)
    package_manager = prompter.select(
        "Package manager:",
        pm_choices,
        default=pd("stack", "package_manager", _default_value(pm_choices, "none")),
    )
    console.print()

    # ── Code quality ─────────────────────────────────────────────────────
    console.print("[bold]  ✅  Code Quality[/bold]")
    linter_choices = _linter_choices(languages)
    linter = prompter.select(
        "Linter:",
        linter_choices,
        default=pd("quality", "linter", _default_value(linter_choices, "none")),
    )
    formatter_choices = _formatter_choices(languages)
    formatter = prompter.select(
        "Formatter:",
        formatter_choices,
        default=pd("quality", "formatter", _default_value(formatter_choices, "none")),
    )
    testing_choices = _testing_choices(languages)
    testing = prompter.select(
        "Testing:",
        testing_choices,
        default=pd("quality", "testing", _default_value(testing_choices, "none")),
    )
    console.print()

    # ── Database ─────────────────────────────────────────────────────────
    console.print("[bold]  🗄️   Database[/bold]")
    db_enabled = prompter.confirm("Configure a database?", default=pd("database", "enabled", False))
    db_engines: list[str] = []
    orm = "none"
    migrations = "none"
    if db_enabled:
        engine_choices = _with_preselection(
            [
                Choice("postgresql", "PostgreSQL"),
                Choice("mysql", "MySQL / MariaDB"),
                Choice("mongodb", "MongoDB"),
                Choice("redis", "Redis"),
                Choice("sqlite", "SQLite"),
            ],
            pd("database", "engines", []),
        )
        db_engines = prompter.checkbox("Database engines:", engine_choices, required=True)
        orm_choices = _orm_choices(languages)
        orm = prompter.select(
            "ORM / ODM:",
            orm_choices,
            default=pd("database", "orm", _default_value(orm_choices, "none")),
        )
        mig_choices = _migration_choices(orm)
        migrations = prompter.select(
            "Migrations tooling:",
            mig_choices,
            default=pd("database", "migrations", _default_value(mig_choices, "none")),
        )
    console.print()

    # ── Infrastructure ───────────────────────────────────────────────────
    console.print("[bold]  🐳  Infrastructure[/bold]")
    docker = prompter.confirm("Docker?", default=pd("infrastructure", "docker", False))
    docker_multistage = False
    if docker:
        docker_multistage = prompter.confirm(
            "Multi-stage Dockerfile?", default=pd("infrastructure", "docker_multistage", True)
        )
    ci = prompter.select(
        "CI/CD:",
        [
            Choice("github_actions", "GitHub Actions"),
            Choice("gitlab_ci", "GitLab CI"),
            Choice("none", "None"),
        ],
        default=pd("infrastructure", "ci", "none"),
    )
    env_file = prompter.confirm(
        ".env file? (generates .env.example)", default=pd("infrastructure", "env_file", False)
    )
    editorconfig = prompter.confirm(
        ".editorconfig?", default=pd("infrastructure", "editorconfig", True)
    )
    pre_commit = prompter.confirm(
        "pre-commit hooks?", default=pd("infrastructure", "pre_commit", False)
    )
    console.print()

    config = DotmasterConfig.model_validate(
        {
            "project": {"name": name, "description": description, "author": author},
            "stack": {
                "languages": languages,
                "framework": framework,
                "package_manager": package_manager,
            },
            "quality": {"linter": linter, "formatter": formatter, "testing": testing},
            "infrastructure": {
                "docker": docker,
                "docker_multistage": docker_multistage,
                "ci": ci,
                "env_file": env_file,
                "editorconfig": editorconfig,
                "pre_commit": pre_commit,
            },
            "database": {
                "enabled": db_enabled,
                "engines": db_engines,
                "orm": orm,
                "migrations": migrations,
            },
            "profile": preset_profile or "none",
        }
    )

    _print_summary(config)
    if not prompter.confirm("Generate dotfiles with these settings?", default=True):
        raise WizardAborted()

    return config


def _print_summary(config: DotmasterConfig) -> None:
    from rich.table import Table

    table = Table(title="Summary", show_header=False, border_style="dim", box=None, padding=(0, 2))
    table.add_column(style="bold dim", min_width=18)
    table.add_column(style="bold")

    table.add_row("Project", config.project.name)
    if config.project.description:
        table.add_row("Description", config.project.description)
    if config.project.author:
        table.add_row("Author", config.project.author)
    table.add_row("Languages", ", ".join(config.stack.languages))
    table.add_row("Framework", config.stack.framework)
    table.add_row("Package manager", config.stack.package_manager)
    table.add_row("Linter", config.quality.linter)
    table.add_row("Formatter", config.quality.formatter)
    table.add_row("Testing", config.quality.testing)
    if config.database.enabled:
        table.add_row("Database(s)", ", ".join(config.database.engines))
        table.add_row("ORM", config.database.orm)
        table.add_row("Migrations", config.database.migrations)
    table.add_row("Docker", "✓" if config.infrastructure.docker else "✗")
    if config.infrastructure.docker:
        table.add_row("  Multi-stage", "✓" if config.infrastructure.docker_multistage else "✗")
    table.add_row("CI/CD", config.infrastructure.ci)
    table.add_row(".env.example", "✓" if config.infrastructure.env_file else "✗")
    table.add_row(".editorconfig", "✓" if config.infrastructure.editorconfig else "✗")
    table.add_row("pre-commit", "✓" if config.infrastructure.pre_commit else "✗")
    if config.profile != "none":
        table.add_row("Profile", config.profile)

    console.print()
    console.print(table)
    console.print()
