"""
dotmaster/plugins/builtin/database.py
Generates docker-compose.yml with selected database services.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, MergeStrategy, Plugin


class DatabasePlugin(Plugin):
    name = "database"
    description = "Generates docker-compose.yml with selected database services"
    provides = ("infra.compose",)
    outputs = ("docker-compose.yml",)
    triggers = ("database.enabled is true",)

    def matches(self, config) -> bool:
        return config.database.enabled

    def plan(self, config, ctx: Context) -> list[FileAction]:
        db = config.database
        content = ctx.render(
            "docker_compose.j2",
            slug=config.slug,
            snake_slug=config.snake_slug,
            engines=db.engines,
            include_app_service=config.infrastructure.docker,
            multistage=config.infrastructure.docker_multistage,
            app_port=config.app_port,
            has_postgres="postgresql" in db.engines,
            has_mysql="mysql" in db.engines,
            has_mongo="mongodb" in db.engines,
            has_redis="redis" in db.engines,
            has_python=config.has_python,
            has_node=config.has_node,
        )
        return [self.file("docker-compose.yml", content, strategy=MergeStrategy.OVERWRITE)]
