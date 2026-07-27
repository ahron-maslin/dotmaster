"""
dotmaster/plugins/builtin/prisma.py
Generates a Prisma schema for JS/TS projects.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, MergeStrategy, Plugin

_ENGINE_PROVIDER: dict[str, str] = {
    "postgresql": "postgresql",
    "mysql": "mysql",
    "mongodb": "mongodb",
    "sqlite": "sqlite",
}


class PrismaPlugin(Plugin):
    name = "prisma"
    description = "Generates prisma/schema.prisma with datasource + example models"
    provides = ("migrations.javascript",)
    outputs = ("prisma/schema.prisma",)
    triggers = ("database.orm is prisma",)

    def matches(self, config) -> bool:
        return config.database.orm == "prisma"

    def plan(self, config, ctx: Context) -> list[FileAction]:
        db = config.database
        provider = next(
            (_ENGINE_PROVIDER[e] for e in db.engines if e in _ENGINE_PROVIDER),
            "postgresql",
        )
        content = ctx.render(
            "prisma_schema.j2",
            provider=provider,
            has_mongodb=provider == "mongodb",
        )
        return [self.file("prisma/schema.prisma", content, strategy=MergeStrategy.CREATE_ONLY)]
