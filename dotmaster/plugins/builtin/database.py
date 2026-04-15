"""
dotmaster/plugins/builtin/database.py
Generates docker-compose.yml with selected database services:
PostgreSQL, MySQL, MongoDB, Redis, and/or SQLite.
"""
from __future__ import annotations

from pathlib import Path

from dotmaster.plugins.base import BasePlugin
from dotmaster.renderer import render_to_file


class DatabasePlugin(BasePlugin):
    name = "database"
    description = (
        "Generates docker-compose.yml with selected database services "
        "(PostgreSQL, MySQL, MongoDB, Redis)"
    )
    triggers = ["database:true"]

    def generate(self, config, output_dir: Path) -> list[Path]:
        db = config.database
        infra = config.infrastructure
        stack = config.stack

        ctx = {
            "project_name": config.project.name or "app",
            "engines": db.engines,
            "orm": db.orm,
            "migrations": db.migrations,
            # App service (include when Docker is also enabled)
            "include_app_service": infra.docker,
            "multistage": infra.docker_multistage,
            "app_port": 8000 if "python" in stack.languages else 3000,
            # Engine flags
            "has_postgres": "postgresql" in db.engines,
            "has_mysql": "mysql" in db.engines,
            "has_mongo": "mongodb" in db.engines,
            "has_redis": "redis" in db.engines,
            "has_sqlite": "sqlite" in db.engines,
            # Language context for app service image
            "has_python": "python" in stack.languages,
            "has_node": any(
                l in stack.languages for l in ("javascript", "typescript")
            ),
        }
        out = render_to_file(
            "docker_compose.j2", ctx, output_dir / "docker-compose.yml"
        )
        return [out]
