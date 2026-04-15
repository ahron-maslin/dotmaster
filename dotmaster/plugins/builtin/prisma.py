"""
dotmaster/plugins/builtin/prisma.py
Generates a Prisma schema for JS/TS projects.

Produces:
  prisma/schema.prisma
"""
from __future__ import annotations

from pathlib import Path

from dotmaster.plugins.base import BasePlugin
from dotmaster.renderer import render_to_file


# Maps our engine keys to Prisma datasource provider strings
_ENGINE_PROVIDER_MAP = {
    "postgresql": "postgresql",
    "mysql": "mysql",
    "mongodb": "mongodb",
    "sqlite": "sqlite",
}


class PrismaPlugin(BasePlugin):
    name = "prisma"
    description = "Generates prisma/schema.prisma with datasource + example models"
    triggers = ["orm:prisma"]

    def generate(self, config, output_dir: Path) -> list[Path]:
        db = config.database
        stack = config.stack

        # Pick the first non-redis engine as the Prisma datasource provider
        provider = "postgresql"  # sensible default
        for engine in db.engines:
            if engine in _ENGINE_PROVIDER_MAP:
                provider = _ENGINE_PROVIDER_MAP[engine]
                break

        ctx = {
            "project_name": config.project.name or "app",
            "provider": provider,
            "engines": db.engines,
            "framework": stack.framework,
            "has_mongodb": provider == "mongodb",
        }

        prisma_dir = output_dir / "prisma"
        prisma_dir.mkdir(exist_ok=True)

        schema = render_to_file(
            "prisma_schema.j2", ctx, prisma_dir / "schema.prisma"
        )
        return [schema]
