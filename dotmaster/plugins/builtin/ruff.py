"""
dotmaster/plugins/builtin/ruff.py
Generates ruff.toml for Python projects using the Ruff linter/formatter.
"""
from __future__ import annotations

from pathlib import Path

from dotmaster.plugins.base import BasePlugin
from dotmaster.renderer import render_to_file


class RuffPlugin(BasePlugin):
    name = "ruff"
    description = "Generates ruff.toml configuration"
    triggers = ["linter:ruff", "formatter:ruff"]

    def should_run(self, config) -> bool:
        return (
            config.quality.linter == "ruff"
            or config.quality.formatter == "ruff"
        )

    def generate(self, config, output_dir: Path) -> list[Path]:
        ctx = {
            "project_name": config.project.name,
            "use_as_formatter": config.quality.formatter == "ruff",
            "testing": config.quality.testing,
        }
        out = render_to_file("ruff_toml.j2", ctx, output_dir / "ruff.toml")
        return [out]
