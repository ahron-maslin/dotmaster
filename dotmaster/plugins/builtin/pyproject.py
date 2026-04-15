"""
dotmaster/plugins/builtin/pyproject.py
Generates pyproject.toml for Python projects.

Delegates to `poetry init` when Poetry is the selected package manager
and the binary is available; otherwise renders a template.
"""
from __future__ import annotations

from pathlib import Path

from dotmaster.plugins.base import BasePlugin
from dotmaster.renderer import render_to_file
from dotmaster.runner import command_exists, run


class PyprojectPlugin(BasePlugin):
    name = "pyproject"
    description = "Generates pyproject.toml for Python projects"
    triggers = ["language:python"]

    def delegate(self, config, output_dir: Path) -> bool:
        """Delegate to `poetry init` when poetry is the package manager."""
        if config.stack.package_manager != "poetry":
            return False
        if not command_exists("poetry"):
            return False
        existing = output_dir / "pyproject.toml"
        if existing.exists():
            return True  # already managed by poetry, skip
        try:
            run(
                [
                    "poetry", "init",
                    "--name", config.project.name or "my-project",
                    "--description", config.project.description or "",
                    "--author", config.project.author or "anonymous",
                    "--no-interaction",
                ],
                cwd=output_dir,
            )
            return True
        except Exception:
            return False

    def generate(self, config, output_dir: Path) -> list[Path]:
        ctx = {
            "project_name": config.project.name,
            "description": config.project.description,
            "author": config.project.author,
            "package_manager": config.stack.package_manager,
            "framework": config.stack.framework,
            "linter": config.quality.linter,
            "formatter": config.quality.formatter,
            "testing": config.quality.testing,
            "use_ruff": config.quality.linter == "ruff",
            "use_black": config.quality.formatter == "black",
            "use_pytest": config.quality.testing == "pytest",
        }
        out = render_to_file(
            "pyproject_toml.j2", ctx, output_dir / "pyproject.toml"
        )
        return [out]
