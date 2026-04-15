"""
dotmaster/plugins/builtin/alembic.py
Generates Alembic migration scaffold for SQLAlchemy Python projects.

Produces:
  alembic.ini
  alembic/env.py
  alembic/script.py.mako
  alembic/versions/.gitkeep
"""
from __future__ import annotations

from pathlib import Path

from dotmaster.plugins.base import BasePlugin
from dotmaster.renderer import render_to_file


class AlembicPlugin(BasePlugin):
    name = "alembic"
    description = "Generates Alembic migration scaffold (alembic.ini + alembic/)"
    triggers = ["migrations:alembic"]

    def generate(self, config, output_dir: Path) -> list[Path]:
        db = config.database
        stack = config.stack

        # Determine the default async mode based on framework
        async_mode = config.stack.framework in ("fastapi",)

        ctx = {
            "project_name": config.project.name or "app",
            "engines": db.engines,
            "has_postgres": "postgresql" in db.engines,
            "has_mysql": "mysql" in db.engines,
            "has_sqlite": "sqlite" in db.engines,
            "async_mode": async_mode,
            "framework": stack.framework,
            "package_manager": stack.package_manager,
        }

        alembic_dir = output_dir / "alembic"
        versions_dir = alembic_dir / "versions"
        versions_dir.mkdir(parents=True, exist_ok=True)

        ini = render_to_file("alembic_ini.j2", ctx, output_dir / "alembic.ini")
        env = render_to_file("alembic_env.j2", ctx, alembic_dir / "env.py")
        mako = render_to_file(
            "alembic_mako.j2", ctx, alembic_dir / "script.py.mako"
        )

        gitkeep = versions_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

        return [ini, env, mako, gitkeep]
