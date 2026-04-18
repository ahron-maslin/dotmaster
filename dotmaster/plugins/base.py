"""
dotmaster/plugins/base.py
Abstract base class that every dotmaster plugin must implement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dotmaster.config import DotmasterConfig


class BasePlugin(ABC):
    """
    Base class for dotmaster plugins.

    Lifecycle
    ---------
    1. ``should_run(config)`` is called to decide whether this plugin is active.
    2. ``run(config, output_dir)`` is called by the engine.
       - It first tries ``delegate()`` (hand off to an official CLI tool).
       - On failure it falls back to ``generate()`` (Jinja2 template).
    3. The engine records every returned ``Path`` in ``dotmaster.yaml``.

    Authoring a new plugin
    -----------------------
    Subclass this, set ``name``, ``description``, and ``triggers``, then
    implement ``generate()``.  Override ``delegate()`` if an official tool
    can do the heavy lifting.
    """

    #: Unique, slug-style identifier used in CLI commands (e.g. ``"eslint"``).
    name: str = ""

    #: One-liner shown in ``dotmaster list``.
    description: str = ""

    #: Trigger expressions evaluated by ``should_run``.
    #: Format: ``"<key>:<value>"`` where key is one of:
    #:   linter, formatter, testing, ci, language, framework, package_manager,
    #:   docker, env_file, editorconfig,
    #:   database, db_engine, orm, migrations
    #: Example: ``["linter:eslint", "language:typescript"]``
    triggers: list[str] = []

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def should_run(self, config: "DotmasterConfig") -> bool:
        """Return True if any trigger condition matches *config*."""
        for trigger in self.triggers:
            key, _, value = trigger.partition(":")
            if self._eval_trigger(config, key, value):
                return True
        return False

    def _eval_trigger(
        self, config: "DotmasterConfig", key: str, value: str
    ) -> bool:
        """Evaluate a single ``key:value`` trigger against *config*."""
        mapping: dict[str, Any] = {
            "linter": config.quality.linter,
            "formatter": config.quality.formatter,
            "testing": config.quality.testing,
            "ci": config.infrastructure.ci,
            "language": config.stack.languages,
            "framework": config.stack.framework,
            "package_manager": config.stack.package_manager,
            "docker": str(config.infrastructure.docker).lower(),
            "env_file": str(config.infrastructure.env_file).lower(),
            "editorconfig": str(config.infrastructure.editorconfig).lower(),
            # Database triggers
            "database": str(config.database.enabled).lower(),
            "db_engine": config.database.engines,
            "orm": config.database.orm,
            "migrations": config.database.migrations,
        }
        actual = mapping.get(key)
        if actual is None:
            return False
        if isinstance(actual, list):
            return value in actual
        return actual == value

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def delegate(self, config: "DotmasterConfig", output_dir: Path) -> bool:
        """
        Attempt to hand off to an official CLI tool.

        Return True if the delegation succeeded (``generate()`` is skipped),
        False to fall through to template-based generation.
        """
        return False

    @abstractmethod
    def generate(
        self, config: "DotmasterConfig", output_dir: Path
    ) -> list[Path]:
        """
        Generate dotfiles for this plugin.

        Returns
        -------
        list[Path]
            Paths of files that were created or modified.
        """
        ...

    def run(
        self, config: "DotmasterConfig", output_dir: Path
    ) -> list[Path]:
        """
        Engine entry point.

        Tries ``delegate()`` first.  If it returns False, calls ``generate()``.
        Returns the list of created/modified paths.
        """
        if self.delegate(config, output_dir):
            return []
        return self.generate(config, output_dir)


    def post_run(
        self, config: "DotmasterConfig", output_dir: Path
    ) -> None:
        """
        Lifecycle hook invoked after all plugins have finished generating files.
        Can be overridden to run shell commands, install deps, format files, etc.
        """
        pass

# Suppress NameError for the type hint inside _eval_trigger at runtime
from typing import Any  # noqa: E402 (below the class is intentional)
