"""
dotmaster/config.py
Read/write the dotmaster.yaml configuration file and define the Config schema.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

CONFIG_FILENAME = "dotmaster.yaml"
CONFIG_VERSION = "1"


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ProjectConfig:
    """Basic project metadata."""

    name: str = ""
    description: str = ""
    author: str = ""


@dataclass
class StackConfig:
    """Language, framework, and package manager selection."""

    languages: list[str] = field(default_factory=list)
    framework: str = "none"
    package_manager: str = "none"


@dataclass
class QualityConfig:
    """Code-quality tooling: linter, formatter, testing."""

    linter: str = "none"      # eslint | ruff | golangci-lint | none
    formatter: str = "none"   # prettier | black | gofmt | none
    testing: str = "none"     # jest | vitest | pytest | go_test | none


@dataclass
class InfraConfig:
    """Infrastructure / DevOps options."""

    docker: bool = False
    docker_multistage: bool = False
    ci: str = "none"          # github_actions | gitlab_ci | none
    env_file: bool = False
    editorconfig: bool = True


@dataclass
class GeneratedEntry:
    """Records a single generated file (used by the regeneration engine)."""

    path: str
    plugin: str
    at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class DatabaseConfig:
    """
    Database tooling configuration.

    Engines:    postgresql | mysql | mongodb | redis | sqlite
    ORM/ODM:    sqlalchemy | prisma | drizzle | typeorm | mongoose
                | django_orm | tortoise | none
    Migrations: alembic | prisma | django | aerich | none
    """

    enabled: bool = False
    engines: list[str] = field(default_factory=list)
    orm: str = "none"
    migrations: str = "none"


@dataclass
class DotmasterConfig:
    """Root configuration object that maps directly to dotmaster.yaml."""

    version: str = CONFIG_VERSION
    project: ProjectConfig = field(default_factory=ProjectConfig)
    stack: StackConfig = field(default_factory=StackConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    infrastructure: InfraConfig = field(default_factory=InfraConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    profile: str = "none"
    generated: list[GeneratedEntry] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DotmasterConfig":
        cfg = cls()
        if "project" in data:
            cfg.project = ProjectConfig(**data["project"])
        if "stack" in data:
            cfg.stack = StackConfig(**data["stack"])
        if "quality" in data:
            cfg.quality = QualityConfig(**data["quality"])
        if "infrastructure" in data:
            cfg.infrastructure = InfraConfig(**data["infrastructure"])
        if "database" in data:
            cfg.database = DatabaseConfig(**data["database"])
        cfg.profile = data.get("profile", "none")
        cfg.version = data.get("version", CONFIG_VERSION)
        cfg.generated = [
            GeneratedEntry(**e) for e in data.get("generated", [])
        ]
        return cfg

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def has_language(self, lang: str) -> bool:
        return lang in self.stack.languages

    def has_any_language(self, *langs: str) -> bool:
        return any(self.has_language(l) for l in langs)

    def record_generated(self, path: Path, plugin_name: str) -> None:
        """Add or update a generated entry."""
        rel = str(path)
        # Replace existing entry for the same path
        self.generated = [e for e in self.generated if e.path != rel]
        self.generated.append(GeneratedEntry(path=rel, plugin=plugin_name))


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------


def load_config(path: Path | None = None) -> DotmasterConfig:
    """Load dotmaster.yaml from the given path or current directory."""
    if path is None:
        path = Path.cwd() / CONFIG_FILENAME
    if not path.exists():
        raise FileNotFoundError(
            f"No {CONFIG_FILENAME} found at {path}.\n"
            "Run 'dotmaster init' to create one."
        )
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return DotmasterConfig.from_dict(data)


def save_config(config: DotmasterConfig, path: Path | None = None) -> Path:
    """Serialize and write config to dotmaster.yaml. Returns the written path."""
    if path is None:
        path = Path.cwd() / CONFIG_FILENAME
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            config.to_dict(),
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
    return path


def config_exists(directory: Path | None = None) -> bool:
    """Return True if dotmaster.yaml exists in *directory* (or cwd)."""
    if directory is None:
        directory = Path.cwd()
    return (directory / CONFIG_FILENAME).exists()
