"""
dotmaster/plugins/builtin/dotenv.py
Generates .env.example with sensible starter variables.
"""
from __future__ import annotations

from pathlib import Path

from dotmaster.plugins.base import BasePlugin
from dotmaster.renderer import render_to_file


class DotenvPlugin(BasePlugin):
    name = "dotenv"
    description = "Generates .env.example with starter environment variables"
    triggers = ["env_file:true"]

    def generate(self, config, output_dir: Path) -> list[Path]:
        ctx = {
            "project_name": config.project.name,
            "framework": config.stack.framework,
            "has_python": "python" in config.stack.languages,
            "has_node": any(
                l in config.stack.languages
                for l in ("javascript", "typescript")
            ),
            "db_engines": config.database.engines,
        }
        out = render_to_file(
            "env_example.j2", ctx, output_dir / ".env.example"
        )
        return [out]
