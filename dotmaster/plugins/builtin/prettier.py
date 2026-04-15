"""
dotmaster/plugins/builtin/prettier.py
Generates .prettierrc and .prettierignore configuration files.
"""
from __future__ import annotations

from pathlib import Path

from dotmaster.plugins.base import BasePlugin
from dotmaster.renderer import render_to_file


class PrettierPlugin(BasePlugin):
    name = "prettier"
    description = "Generates .prettierrc and .prettierignore"
    triggers = ["formatter:prettier"]

    def generate(self, config, output_dir: Path) -> list[Path]:
        ctx = {
            "framework": config.stack.framework,
            "has_typescript": "typescript" in config.stack.languages,
        }
        prettierrc = render_to_file(
            "prettierrc.j2", ctx, output_dir / ".prettierrc"
        )
        prettierignore = render_to_file(
            "prettierignore.j2", ctx, output_dir / ".prettierignore"
        )
        return [prettierrc, prettierignore]
