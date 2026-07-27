"""
dotmaster/config.py
The schema for ``dotmaster.yaml`` — the file that records what a project's
configuration is *meant* to be.

``dotmaster.yaml`` is intended to be hand-edited and committed, so it is
validated properly: unknown keys, wrong types and misspelled values produce a
pointed error message instead of a traceback.  Facts about what was actually
generated live in ``.dotmaster/state.json`` (see :mod:`dotmaster.core.state`).
"""

from __future__ import annotations

import difflib
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

logger = logging.getLogger("dotmaster.config")

CONFIG_FILENAME = "dotmaster.yaml"
CONFIG_VERSION = "2"

SCHEMA_URL = (
    "https://raw.githubusercontent.com/ahron-maslin/dotmaster/main/schema/dotmaster.schema.json"
)


# ---------------------------------------------------------------------------
# Known values
#
# Kept as open, registerable sets rather than hard-coded enums so a plugin can
# introduce a new language or tool without a change to core.
# ---------------------------------------------------------------------------

KNOWN_VALUES: dict[str, set[str]] = {
    "language": {"javascript", "typescript", "python", "go", "rust", "java"},
    "framework": {
        "none",
        "nextjs",
        "react",
        "vue",
        "angular",
        "express",
        "fastify",
        "fastapi",
        "django",
        "flask",
        "gin",
        "echo",
        "fiber",
    },
    "package_manager": {
        "none",
        "npm",
        "pnpm",
        "yarn",
        "bun",
        "poetry",
        "uv",
        "pip",
        "go_mod",
        "cargo",
        "maven",
        "gradle",
    },
    "linter": {"none", "eslint", "biome", "ruff", "flake8", "golangci-lint", "clippy"},
    "formatter": {"none", "prettier", "biome", "black", "ruff", "gofmt", "rustfmt"},
    "testing": {"none", "jest", "vitest", "pytest", "go_test", "cargo_test"},
    "ci": {"none", "github_actions", "gitlab_ci"},
    "db_engine": {"postgresql", "mysql", "mongodb", "redis", "sqlite"},
    "orm": {
        "none",
        "sqlalchemy",
        "prisma",
        "drizzle",
        "typeorm",
        "mongoose",
        "django_orm",
        "tortoise",
    },
    "migrations": {"none", "alembic", "prisma", "django", "aerich", "drizzle"},
}


def register_values(dimension: str, *values: str) -> None:
    """Let a plugin extend an existing dimension with new accepted values."""
    KNOWN_VALUES.setdefault(dimension, set()).update(values)


class ConfigError(Exception):
    """A user-facing problem with dotmaster.yaml."""


def _check(dimension: str, value: str, *, field: str) -> str:
    known = KNOWN_VALUES.get(dimension, set())
    if not known or value in known:
        return value
    hint = difflib.get_close_matches(value, sorted(known), n=1)
    suggestion = f" Did you mean '{hint[0]}'?" if hint else ""
    raise ValueError(
        f"unknown {field} '{value}'.{suggestion} Valid values: {', '.join(sorted(known))}"
    )


class _Section(BaseModel):
    """Base for every config section: reject typos rather than ignore them."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


class ProjectConfig(_Section):
    """Basic project metadata."""

    name: str = ""
    description: str = ""
    author: str = ""
    license: str = "MIT"


class StackConfig(_Section):
    """Language, framework and package manager selection."""

    languages: list[str] = Field(default_factory=list)
    framework: str = "none"
    package_manager: str = "none"

    @field_validator("languages")
    @classmethod
    def _langs(cls, v: list[str]) -> list[str]:
        seen: list[str] = []
        for lang in v:
            _check("language", lang, field="language")
            if lang not in seen:
                seen.append(lang)
        return seen

    @field_validator("framework")
    @classmethod
    def _framework(cls, v: str) -> str:
        return _check("framework", v, field="framework")

    @field_validator("package_manager")
    @classmethod
    def _pm(cls, v: str) -> str:
        return _check("package_manager", v, field="package manager")


class QualityConfig(_Section):
    """Linter, formatter and test runner."""

    linter: str = "none"
    formatter: str = "none"
    testing: str = "none"

    @field_validator("linter")
    @classmethod
    def _linter(cls, v: str) -> str:
        return _check("linter", v, field="linter")

    @field_validator("formatter")
    @classmethod
    def _formatter(cls, v: str) -> str:
        return _check("formatter", v, field="formatter")

    @field_validator("testing")
    @classmethod
    def _testing(cls, v: str) -> str:
        return _check("testing", v, field="test runner")


class InfraConfig(_Section):
    """Infrastructure and DevOps options."""

    docker: bool = False
    docker_multistage: bool = False
    ci: str = "none"
    env_file: bool = False
    editorconfig: bool = True
    pre_commit: bool = False

    @field_validator("ci")
    @classmethod
    def _ci(cls, v: str) -> str:
        return _check("ci", v, field="CI provider")


class DatabaseConfig(_Section):
    """Database engines and data-access tooling."""

    enabled: bool = False
    engines: list[str] = Field(default_factory=list)
    orm: str = "none"
    migrations: str = "none"

    @field_validator("engines")
    @classmethod
    def _engines(cls, v: list[str]) -> list[str]:
        seen: list[str] = []
        for engine in v:
            _check("db_engine", engine, field="database engine")
            if engine not in seen:
                seen.append(engine)
        return seen

    @field_validator("orm")
    @classmethod
    def _orm(cls, v: str) -> str:
        return _check("orm", v, field="ORM")

    @field_validator("migrations")
    @classmethod
    def _migrations(cls, v: str) -> str:
        return _check("migrations", v, field="migrations tool")


class OptionsConfig(_Section):
    """Behavioural switches for dotmaster itself."""

    #: When true dotmaster makes no network requests at all.
    offline: bool = True
    #: Archive files before overwriting them.
    backup: bool = True
    #: How many backup archives to retain.
    keep_backups: int = Field(default=10, ge=0)


class PluginsConfig(_Section):
    """Third-party plugin control."""

    #: Plugin ids allowed to load.  ``["*"]`` trusts every installed plugin.
    allow: list[str] = Field(default_factory=list)
    #: Plugin ids to disable even when they would otherwise activate.
    disable: list[str] = Field(default_factory=list)
    #: Per-plugin settings, surfaced to the plugin as ``ctx.settings``.
    settings: dict[str, dict[str, Any]] = Field(default_factory=dict)


class DotmasterConfig(BaseModel):
    """Root configuration object; maps one-to-one to dotmaster.yaml."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    version: str = CONFIG_VERSION
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    stack: StackConfig = Field(default_factory=StackConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)
    infrastructure: InfraConfig = Field(default_factory=InfraConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    options: OptionsConfig = Field(default_factory=OptionsConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    profile: str = "none"

    # -- convenience accessors ------------------------------------------

    def has_language(self, lang: str) -> bool:
        return lang in self.stack.languages

    def has_any_language(self, *langs: str) -> bool:
        return any(self.has_language(lang) for lang in langs)

    @property
    def has_node(self) -> bool:
        return self.has_any_language("javascript", "typescript")

    @property
    def has_typescript(self) -> bool:
        return self.has_language("typescript")

    @property
    def has_python(self) -> bool:
        return self.has_language("python")

    @property
    def has_go(self) -> bool:
        return self.has_language("go")

    @property
    def has_rust(self) -> bool:
        return self.has_language("rust")

    @property
    def has_react(self) -> bool:
        return self.stack.framework in ("react", "nextjs")

    @property
    def app_port(self) -> int:
        return 8000 if self.has_python else 3000

    @property
    def slug(self) -> str:
        """Project name normalised for use in identifiers and image tags."""
        name = (self.project.name or "app").strip().lower()
        out = "".join(ch if ch.isalnum() else "-" for ch in name).strip("-")
        while "--" in out:
            out = out.replace("--", "-")
        return out or "app"

    @property
    def snake_slug(self) -> str:
        return self.slug.replace("-", "_")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DotmasterConfig:
        return cls.model_validate(migrate(data))


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


def migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Bring a config dict written by an older dotmaster up to date."""
    if not isinstance(data, dict):
        raise ConfigError(
            f"{CONFIG_FILENAME} must contain a mapping at the top level, got {type(data).__name__}"
        )
    data = dict(data)
    version = str(data.get("version", "1"))

    if version == "1":
        # v1 stored the generated-file inventory inline; it now lives in
        # .dotmaster/state.json.  It is lifted out by `adopt_legacy_state`.
        data.pop("generated", None)
        data["version"] = "2"
        version = "2"

    if version != CONFIG_VERSION:
        raise ConfigError(
            f"{CONFIG_FILENAME} declares version '{version}', but this dotmaster "
            f"understands up to version '{CONFIG_VERSION}'.\n"
            "Upgrade with:  pipx upgrade dotmaster"
        )
    return data


def adopt_legacy_state(raw: dict[str, Any], root: Path) -> None:
    """
    Carry a v1 ``generated:`` list into the state ledger.

    Files previously recorded by dotmaster are adopted with the hash of their
    *current* contents, i.e. "dotmaster owns this as it stands".  That keeps
    upgrades quiet — those files regenerate exactly as they did before — while
    everything written from now on is drift-tracked properly.
    """
    from dotmaster.core.state import load_state, save_state, state_path

    entries = raw.get("generated")
    if not entries or state_path(root).exists():
        return

    from dotmaster.core.engine import safe_target

    state = load_state(root)
    adopted = 0
    for entry in entries:
        if not isinstance(entry, dict) or "path" not in entry:
            continue
        rel = str(entry["path"]).replace("\\", "/")
        target = safe_target(root, rel)
        if target is None or not target.is_file():
            continue
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        state.record(
            rel,
            plugin=str(entry.get("plugin", "unknown")),
            content=content,
            strategy="merge",
        )
        adopted += 1
    if adopted:
        logger.info("Adopted %d file(s) from the v1 config into the state ledger.", adopted)
        save_state(state, root)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def _format_validation_error(exc: ValidationError, path: Path) -> str:
    lines = [f"{path.name} is not valid:"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        msg = err["msg"].removeprefix("Value error, ")
        if err["type"] == "extra_forbidden":
            section = ".".join(str(p) for p in err["loc"][:-1]) or "top level"
            msg = f"unknown key (not recognised in {section})"
        lines.append(f"  {loc}: {msg}")
    return "\n".join(lines)


def load_config(path: Path | None = None, *, adopt_state: bool = True) -> DotmasterConfig:
    """Load and validate dotmaster.yaml."""
    if path is None:
        path = Path.cwd() / CONFIG_FILENAME
    if not path.exists():
        raise ConfigError(
            f"No {CONFIG_FILENAME} found at {path}.\nRun 'dotmaster init' to create one."
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        detail = getattr(exc, "problem_mark", None)
        where = f" (line {detail.line + 1}, column {detail.column + 1})" if detail else ""
        raise ConfigError(
            f"{path.name} is not valid YAML{where}: {getattr(exc, 'problem', exc)}"
        ) from exc
    except OSError as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(
            f"{path.name} must contain a mapping at the top level, got {type(raw).__name__}."
        )

    try:
        config = DotmasterConfig.from_dict(raw)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc, path)) from exc

    if adopt_state:
        adopt_legacy_state(raw, path.parent)
    return config


def save_config(config: DotmasterConfig, path: Path | None = None) -> Path:
    """Serialise config to dotmaster.yaml with a schema hint for editors."""
    if path is None:
        path = Path.cwd() / CONFIG_FILENAME
    body = yaml.dump(
        config.to_dict(),
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    header = (
        f"# yaml-language-server: $schema={SCHEMA_URL}\n"
        "# dotmaster configuration — edit freely, then run `dotmaster sync`.\n"
        "# Docs: https://github.com/ahron-maslin/dotmaster\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + body, encoding="utf-8")
    return path


def config_exists(directory: Path | None = None) -> bool:
    if directory is None:
        directory = Path.cwd()
    return (directory / CONFIG_FILENAME).exists()


def apply_overrides(config: DotmasterConfig, overrides: Iterable[str]) -> DotmasterConfig:
    """
    Apply ``--set section.field=value`` overrides, with validation.

    Booleans accept true/false/yes/no/1/0; list fields accept comma-separated
    values.  This is what makes dotmaster usable non-interactively.
    """
    data = config.to_dict()
    for raw in overrides:
        if "=" not in raw:
            raise ConfigError(f"--set expects key=value, got '{raw}'")
        key, _, value = raw.partition("=")
        parts = [p for p in key.strip().split(".") if p]
        if not parts:
            raise ConfigError(f"--set expects key=value, got '{raw}'")

        cursor: Any = data
        for part in parts[:-1]:
            if not isinstance(cursor, dict) or part not in cursor:
                raise ConfigError(f"--set: unknown section '{'.'.join(parts[:-1])}'")
            cursor = cursor[part]
        leaf = parts[-1]
        if not isinstance(cursor, dict) or leaf not in cursor:
            raise ConfigError(f"--set: unknown setting '{key.strip()}'")

        current = cursor[leaf]
        cursor[leaf] = _coerce(value.strip(), current, key.strip())

    try:
        return DotmasterConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(
            _format_validation_error(exc, Path(CONFIG_FILENAME)).replace(
                f"{CONFIG_FILENAME} is not valid:", "invalid --set value:"
            )
        ) from exc


def _coerce(value: str, current: Any, key: str) -> Any:
    if isinstance(current, bool):
        lowered = value.lower()
        if lowered in ("true", "yes", "y", "1", "on"):
            return True
        if lowered in ("false", "no", "n", "0", "off"):
            return False
        raise ConfigError(f"--set {key}: expected a boolean, got '{value}'")
    if isinstance(current, list):
        return [v.strip() for v in value.split(",") if v.strip()]
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(value)
        except ValueError as exc:
            raise ConfigError(f"--set {key}: expected a number, got '{value}'") from exc
    return value
