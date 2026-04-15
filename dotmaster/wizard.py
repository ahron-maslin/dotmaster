"""
dotmaster/wizard.py
Interactive Q&A wizard powered by InquirerPy.

Returns a fully populated DotmasterConfig after asking the user a structured
series of questions about their project stack and tooling preferences.
"""
from __future__ import annotations

import os
from pathlib import Path

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from dotmaster import __version__
from dotmaster.config import (
    DotmasterConfig,
    InfraConfig,
    ProjectConfig,
    QualityConfig,
    StackConfig,
    DatabaseConfig,
)
from dotmaster.profiles import get_profile, list_profiles

console = Console()


# ---------------------------------------------------------------------------
# Dynamic choice helpers
# ---------------------------------------------------------------------------


def _framework_choices(languages: list[str]) -> list[Choice | Separator]:
    choices: list[Choice | Separator] = []
    if any(l in languages for l in ("javascript", "typescript")):
        choices += [
            Separator("── JavaScript / TypeScript ──"),
            Choice("nextjs", "Next.js"),
            Choice("react", "React (Vite)"),
            Choice("vue", "Vue 3"),
            Choice("angular", "Angular"),
            Choice("express", "Express"),
            Choice("fastify", "Fastify"),
        ]
    if "python" in languages:
        choices += [
            Separator("── Python ──"),
            Choice("fastapi", "FastAPI"),
            Choice("django", "Django"),
            Choice("flask", "Flask"),
        ]
    if "go" in languages:
        choices += [
            Separator("── Go ──"),
            Choice("gin", "Gin"),
            Choice("echo", "Echo"),
            Choice("fiber", "Fiber"),
        ]
    choices.append(Separator("──────────────────────"))
    choices.append(Choice("none", "None / plain"))
    return choices


def _pm_choices(languages: list[str]) -> list[Choice | Separator]:
    choices: list[Choice | Separator] = []
    if any(l in languages for l in ("javascript", "typescript")):
        choices += [
            Separator("── Node.js ──"),
            Choice("npm", "npm"),
            Choice("pnpm", "pnpm (fast, disk-efficient)"),
            Choice("yarn", "Yarn"),
        ]
    if "python" in languages:
        choices += [
            Separator("── Python ──"),
            Choice("poetry", "Poetry"),
            Choice("uv", "uv (ultra-fast)"),
            Choice("pip", "pip / requirements.txt"),
        ]
    if "go" in languages:
        choices += [
            Separator("── Go ──"),
            Choice("go_mod", "go mod"),
        ]
    if "rust" in languages:
        choices += [
            Separator("── Rust ──"),
            Choice("cargo", "Cargo"),
        ]
    return choices or [Choice("none", "None")]


def _linter_choices(languages: list[str]) -> list[Choice]:
    choices: list[Choice] = []
    if any(l in languages for l in ("javascript", "typescript")):
        choices.append(Choice("eslint", "ESLint"))
    if "python" in languages:
        choices.append(Choice("ruff", "Ruff"))
        choices.append(Choice("flake8", "Flake8"))
    if "go" in languages:
        choices.append(Choice("golangci-lint", "golangci-lint"))
    choices.append(Choice("none", "None"))
    return choices


def _formatter_choices(languages: list[str]) -> list[Choice]:
    choices: list[Choice] = []
    if any(l in languages for l in ("javascript", "typescript")):
        choices.append(Choice("prettier", "Prettier"))
    if "python" in languages:
        choices.append(Choice("black", "Black"))
        choices.append(Choice("ruff", "Ruff (formatter mode)"))
    if "go" in languages:
        choices.append(Choice("gofmt", "gofmt"))
    choices.append(Choice("none", "None"))
    return choices


def _testing_choices(languages: list[str]) -> list[Choice]:
    choices: list[Choice] = []
    if any(l in languages for l in ("javascript", "typescript")):
        choices.append(Choice("jest", "Jest"))
        choices.append(Choice("vitest", "Vitest"))
    if "python" in languages:
        choices.append(Choice("pytest", "pytest"))
    if "go" in languages:
        choices.append(Choice("go_test", "go test (built-in)"))
    choices.append(Choice("none", "None"))
    return choices


def _orm_choices(languages: list[str]) -> list[Choice]:
    choices: list[Choice] = []
    if any(l in languages for l in ("javascript", "typescript")):
        choices.append(Choice("prisma", "Prisma"))
        choices.append(Choice("drizzle", "Drizzle"))
        choices.append(Choice("typeorm", "TypeORM"))
        choices.append(Choice("mongoose", "Mongoose"))
    if "python" in languages:
        choices.append(Choice("sqlalchemy", "SQLAlchemy"))
        choices.append(Choice("django_orm", "Django ORM"))
        choices.append(Choice("tortoise", "Tortoise ORM"))
    choices.append(Choice("none", "None"))
    return choices


def _migration_choices(languages: list[str], orm: str) -> list[Choice]:
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


def _default(choices: list[Choice | Separator], fallback: str) -> str:
    """Return the value of the first non-Separator choice, or *fallback*."""
    for c in choices:
        if isinstance(c, Choice):
            return c.value
    return fallback


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------


def run_wizard(
    preset_profile: str | None = None,
    output_dir: Path | None = None,
) -> DotmasterConfig:
    """
    Run the full interactive wizard.

    Parameters
    ----------
    preset_profile : str | None
        If given, pre-fill answers from this profile name (user can still
        override individual values).
    output_dir : Path | None
        Target directory; used to compute a default project name.

    Returns
    -------
    DotmasterConfig
        Fully populated configuration ready to generate dotfiles from.
    """
    if output_dir is None:
        output_dir = Path.cwd()

    # ── Banner ────────────────────────────────────────────────────────────────
    banner = Text()
    banner.append("  dotmaster ", style="bold magenta")
    banner.append(f"v{__version__}", style="dim")
    banner.append("  ·  dotfile generator", style="dim")
    console.print(
        Panel(banner, border_style="magenta", expand=False, padding=(0, 2))
    )
    console.print()

    # ── Load profile defaults ─────────────────────────────────────────────────
    profile_data: dict = {}
    if preset_profile is None:
        use_preset = inquirer.confirm(
            message="Start from a preset profile?",
            default=False,
        ).execute()
        if use_preset:
            profile_names = [p[0] for p in list_profiles()]
            profile_name = inquirer.select(
                message="Select a profile:",
                choices=[
                    Choice("web_app",      "🌐  Web App — React/Next.js + ESLint + Docker + CI"),
                    Choice("library",      "📦  Library — ESLint + Jest, no Docker"),
                    Choice("backend_api",  "⚙️   Backend API — Python + Docker + CI"),
                    Choice("monorepo",     "🗂️   Monorepo — pnpm + ESLint + CI"),
                    Choice("none",         "✏️   Custom — answer everything manually"),
                ],
                default="none",
            ).execute()
            if profile_name != "none":
                preset_profile = profile_name
                data = get_profile(profile_name)
                if data:
                    profile_data = data
                    console.print(
                        f"  [dim]Loaded profile:[/dim] [bold magenta]{profile_name}[/bold magenta]"
                        "  [dim](you can still override any setting below)[/dim]\n"
                    )
    else:
        data = get_profile(preset_profile)
        if data:
            profile_data = data

    def pd(section: str, key: str, fallback):
        """Safe accessor for profile_data nested values."""
        return profile_data.get(section, {}).get(key, fallback)

    # ── Phase 1: Project meta ─────────────────────────────────────────────────
    console.print("[bold]  📁  Project[/bold]")

    default_name = output_dir.name
    name = inquirer.text(
        message="Project name:",
        default=default_name,
    ).execute().strip() or default_name

    description = inquirer.text(
        message="Description:",
        default="",
    ).execute().strip()

    default_author = (
        os.environ.get("GIT_AUTHOR_NAME")
        or os.environ.get("USER")
        or ""
    )
    author = inquirer.text(
        message="Author:",
        default=default_author,
    ).execute().strip()

    console.print()

    # ── Phase 2: Language & Framework ────────────────────────────────────────
    console.print("[bold]  🛠️   Stack[/bold]")

    languages: list[str] = inquirer.checkbox(
        message="Language(s):",
        choices=[
            Choice("javascript", "JavaScript"),
            Choice("typescript", "TypeScript"),
            Choice("python", "Python"),
            Choice("go", "Go"),
            Choice("rust", "Rust"),
            Choice("java", "Java"),
        ],
        default=pd("stack", "languages", []),
        validate=lambda result: len(result) > 0,
        invalid_message="Please select at least one language.",
        instruction="(space to select, enter to confirm)",
    ).execute()

    fw_choices = _framework_choices(languages)
    framework: str = inquirer.select(
        message="Framework:",
        choices=fw_choices,
        default=pd("stack", "framework", _default(fw_choices, "none")),
    ).execute()

    pm_choices = _pm_choices(languages)
    package_manager: str = inquirer.select(
        message="Package manager:",
        choices=pm_choices,
        default=pd("stack", "package_manager", _default(pm_choices, "none")),
    ).execute()

    console.print()

    # ── Phase 3: Code quality ────────────────────────────────────────────────
    console.print("[bold]  ✅  Code Quality[/bold]")

    linter_choices = _linter_choices(languages)
    linter: str = inquirer.select(
        message="Linter:",
        choices=linter_choices,
        default=pd("quality", "linter", _default(linter_choices, "none")),
    ).execute()

    formatter_choices = _formatter_choices(languages)
    formatter: str = inquirer.select(
        message="Formatter:",
        choices=formatter_choices,
        default=pd("quality", "formatter", _default(formatter_choices, "none")),
    ).execute()

    testing_choices = _testing_choices(languages)
    testing: str = inquirer.select(
        message="Testing:",
        choices=testing_choices,
        default=pd("quality", "testing", _default(testing_choices, "none")),
    ).execute()

    console.print()

    # ── Phase 4: Database ────────────────────────────────────────────────────
    console.print("[bold]  🗄️   Database[/bold]")

    db_enabled: bool = inquirer.confirm(
        message="Configure a database?",
        default=pd("database", "enabled", False),
    ).execute()

    db_engines: list[str] = []
    orm: str = "none"
    migrations: str = "none"

    if db_enabled:
        db_engines = inquirer.checkbox(
            message="Database Engines:",
            choices=[
                Choice("postgresql", "PostgreSQL"),
                Choice("mysql", "MySQL / MariaDB"),
                Choice("mongodb", "MongoDB"),
                Choice("redis", "Redis"),
                Choice("sqlite", "SQLite"),
            ],
            default=pd("database", "engines", []),
            validate=lambda result: len(result) > 0,
            invalid_message="Please select at least one database engine.",
            instruction="(space to select, enter to confirm)",
        ).execute()

        orm_choices = _orm_choices(languages)
        orm = inquirer.select(
            message="ORM / ODM:",
            choices=orm_choices,
            default=pd("database", "orm", _default(orm_choices, "none")),
        ).execute()

        mig_choices = _migration_choices(languages, orm)
        migrations = inquirer.select(
            message="Migrations tooling:",
            choices=mig_choices,
            default=pd("database", "migrations", _default(mig_choices, "none")),
        ).execute()

    console.print()

    # ── Phase 5: Infrastructure ───────────────────────────────────────────────
    console.print("[bold]  🐳  Infrastructure[/bold]")

    docker: bool = inquirer.confirm(
        message="Docker?",
        default=pd("infrastructure", "docker", False),
    ).execute()

    docker_multistage: bool = False
    if docker:
        docker_multistage = inquirer.confirm(
            message="Multi-stage Dockerfile?",
            default=pd("infrastructure", "docker_multistage", True),
        ).execute()

    ci: str = inquirer.select(
        message="CI/CD:",
        choices=[
            Choice("github_actions", "GitHub Actions"),
            Choice("gitlab_ci",      "GitLab CI"),
            Choice("none",           "None"),
        ],
        default=pd("infrastructure", "ci", "none"),
    ).execute()

    env_file: bool = inquirer.confirm(
        message=".env file? (generates .env.example)",
        default=pd("infrastructure", "env_file", False),
    ).execute()

    editorconfig: bool = inquirer.confirm(
        message=".editorconfig?",
        default=pd("infrastructure", "editorconfig", True),
    ).execute()

    console.print()

    # ── Build config ─────────────────────────────────────────────────────────
    config = DotmasterConfig(
        project=ProjectConfig(
            name=name,
            description=description,
            author=author,
        ),
        stack=StackConfig(
            languages=languages,
            framework=framework,
            package_manager=package_manager,
        ),
        quality=QualityConfig(
            linter=linter,
            formatter=formatter,
            testing=testing,
        ),
        infrastructure=InfraConfig(
            docker=docker,
            docker_multistage=docker_multistage,
            ci=ci,
            env_file=env_file,
            editorconfig=editorconfig,
        ),
        database=DatabaseConfig(
            enabled=db_enabled,
            engines=db_engines,
            orm=orm,
            migrations=migrations,
        ),
        profile=preset_profile or "none",
    )

    # ── Summary confirmation ──────────────────────────────────────────────────
    _print_summary(config)
    confirmed: bool = inquirer.confirm(
        message="Generate dotfiles with these settings?",
        default=True,
    ).execute()

    if not confirmed:
        console.print("\n[yellow]Aborted.[/yellow]")
        raise SystemExit(0)

    return config


def _print_summary(config: DotmasterConfig) -> None:
    """Print a human-readable summary of what will be generated."""
    from rich.table import Table

    table = Table(
        title="Summary",
        show_header=False,
        border_style="dim",
        box=None,
        padding=(0, 2),
    )
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
        table.add_row(
            "  Multi-stage",
            "✓" if config.infrastructure.docker_multistage else "✗",
        )
    table.add_row("CI/CD", config.infrastructure.ci)
    table.add_row(".env.example", "✓" if config.infrastructure.env_file else "✗")
    table.add_row(".editorconfig", "✓" if config.infrastructure.editorconfig else "✗")
    if config.profile != "none":
        table.add_row("Profile", config.profile)

    console.print()
    console.print(table)
    console.print()
