"""
dotmaster/plugins/builtin/dotenv.py
Generates .env.example with sensible starter variables.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, Plugin


class DotenvPlugin(Plugin):
    name = "dotenv"
    description = "Generates .env.example with starter environment variables"
    outputs = (".env.example",)
    triggers = ("infrastructure.env_file is true",)

    def matches(self, config) -> bool:
        return config.infrastructure.env_file

    def plan(self, config, ctx: Context) -> list[FileAction]:
        content = ctx.render(
            "env_example.j2",
            project_name=config.project.name,
            slug=config.slug,
            framework=config.stack.framework,
            has_python=config.has_python,
            has_node=config.has_node,
            db_engines=config.database.engines,
        )
        return [self.block_file(".env.example", content)]
