"""
dotmaster/plugins/builtin/alembic.py
Generates an Alembic migration scaffold for SQLAlchemy Python projects.

Produces alembic.ini, alembic/env.py, alembic/script.py.mako and
alembic/versions/.gitkeep.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, MergeStrategy, Plugin


class AlembicPlugin(Plugin):
    name = "alembic"
    description = "Generates an Alembic migration scaffold (alembic.ini + alembic/)"
    provides = ("migrations.python",)
    outputs = (
        "alembic.ini",
        "alembic/env.py",
        "alembic/script.py.mako",
        "alembic/versions/.gitkeep",
    )
    triggers = ("database.migrations is alembic",)

    def matches(self, config) -> bool:
        return config.database.migrations == "alembic"

    def plan(self, config, ctx: Context) -> list[FileAction]:
        db = config.database
        async_mode = config.stack.framework == "fastapi"
        variables = {
            "slug": config.snake_slug,
            "has_postgres": "postgresql" in db.engines,
            "has_mysql": "mysql" in db.engines,
            "has_sqlite": "sqlite" in db.engines,
            "async_mode": async_mode,
            "framework": config.stack.framework,
        }
        return [
            self.file(
                "alembic.ini",
                ctx.render("alembic_ini.j2", **variables),
                strategy=MergeStrategy.MERGE,
            ),
            self.file(
                "alembic/env.py",
                ctx.render("alembic_env.j2", **variables),
                strategy=MergeStrategy.CREATE_ONLY,
                description="edit freely after first generation",
            ),
            self.file(
                "alembic/script.py.mako",
                ctx.render("alembic_mako.j2", **variables),
                strategy=MergeStrategy.CREATE_ONLY,
            ),
            self.file(
                "alembic/versions/.gitkeep",
                "",
                strategy=MergeStrategy.CREATE_ONLY,
            ),
        ]
