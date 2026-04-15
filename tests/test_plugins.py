"""
tests/test_plugins.py
Unit tests for the plugin registry and individual built-in plugins.
"""
from __future__ import annotations

import pytest

from dotmaster.config import (
    DatabaseConfig,
    DotmasterConfig,
    InfraConfig,
    ProjectConfig,
    QualityConfig,
    StackConfig,
)
from dotmaster.plugins import PluginRegistry, registry


def _cfg(
    languages=("python",),
    framework="fastapi",
    pm="poetry",
    linter="ruff",
    formatter="black",
    testing="pytest",
    docker=True,
    ci="github_actions",
    env_file=True,
    editorconfig=True,
    db_enabled=False,
    db_engines=None,
    orm="none",
    migrations="none",
) -> DotmasterConfig:
    return DotmasterConfig(
        project=ProjectConfig(name="test", description="", author=""),
        stack=StackConfig(
            languages=list(languages),
            framework=framework,
            package_manager=pm,
        ),
        quality=QualityConfig(linter=linter, formatter=formatter, testing=testing),
        infrastructure=InfraConfig(
            docker=docker,
            docker_multistage=True,
            ci=ci,
            env_file=env_file,
            editorconfig=editorconfig,
        ),
        database=DatabaseConfig(
            enabled=db_enabled,
            engines=db_engines or [],
            orm=orm,
            migrations=migrations,
        ),
    )


class TestPluginRegistry:
    def test_all_returns_instances(self):
        plugins = registry.all()
        assert len(plugins) > 0

    def test_get_known_plugin(self):
        p = registry.get("gitignore")
        assert p is not None
        assert p.name == "gitignore"

    def test_get_unknown_returns_none(self):
        assert registry.get("nonexistent_plugin") is None

    def test_names_includes_builtins(self):
        names = registry.names()
        for expected in ("gitignore", "eslint", "prettier", "docker", "ruff"):
            assert expected in names

    def test_active_python_config(self):
        config = _cfg()
        active_names = [p.name for p in registry.active(config)]
        assert "gitignore" in active_names
        assert "ruff" in active_names
        assert "pyproject" in active_names
        assert "docker" in active_names
        assert "github_actions" in active_names
        assert "dotenv" in active_names
        assert "editorconfig" in active_names

    def test_active_no_eslint_for_python(self):
        config = _cfg()
        active_names = [p.name for p in registry.active(config)]
        assert "eslint" not in active_names

    def test_active_js_config(self):
        config = _cfg(
            languages=("javascript", "typescript"),
            framework="nextjs",
            pm="npm",
            linter="eslint",
            formatter="prettier",
            testing="jest",
        )
        active_names = [p.name for p in registry.active(config)]
        assert "eslint" in active_names
        assert "prettier" in active_names
        assert "gitignore" in active_names
        assert "ruff" not in active_names


class TestGitignorePlugin:
    def test_generate_fallback(self, tmp_path):
        from dotmaster.plugins.builtin.gitignore import GitignorePlugin

        plugin = GitignorePlugin()
        config = _cfg(languages=("python",))
        paths = plugin.generate(config, tmp_path)
        assert len(paths) == 1
        assert (tmp_path / ".gitignore").exists()
        content = (tmp_path / ".gitignore").read_text()
        assert "pycache" in content or "Python" in content


class TestEditorConfigPlugin:
    def test_generates_editorconfig(self, tmp_path):
        from dotmaster.plugins.builtin.editorconfig import EditorConfigPlugin

        plugin = EditorConfigPlugin()
        config = _cfg()
        paths = plugin.generate(config, tmp_path)
        assert (tmp_path / ".editorconfig").exists()
        content = (tmp_path / ".editorconfig").read_text()
        assert "root = true" in content

    def test_should_run_when_enabled(self):
        from dotmaster.plugins.builtin.editorconfig import EditorConfigPlugin

        plugin = EditorConfigPlugin()
        assert plugin.should_run(_cfg(editorconfig=True))
        assert not plugin.should_run(_cfg(editorconfig=False))


class TestDockerPlugin:
    def test_generates_dockerfile_and_ignore(self, tmp_path):
        from dotmaster.plugins.builtin.docker import DockerPlugin

        plugin = DockerPlugin()
        config = _cfg(docker=True)
        paths = plugin.generate(config, tmp_path)
        files = {p.name for p in paths}
        assert "Dockerfile" in files
        assert ".dockerignore" in files

    def test_should_not_run_without_docker(self):
        from dotmaster.plugins.builtin.docker import DockerPlugin

        plugin = DockerPlugin()
        assert not plugin.should_run(_cfg(docker=False))


class TestDotenvPlugin:
    def test_generates_env_example(self, tmp_path):
        from dotmaster.plugins.builtin.dotenv import DotenvPlugin

        plugin = DotenvPlugin()
        config = _cfg(env_file=True)
        paths = plugin.generate(config, tmp_path)
        assert (tmp_path / ".env.example").exists()


class TestDatabasePlugin:
    def _db_cfg(self, engines=("postgresql", "redis"), orm="sqlalchemy", mig="alembic"):
        return _cfg(
            db_enabled=True,
            db_engines=list(engines),
            orm=orm,
            migrations=mig,
        )

    def test_generates_docker_compose(self, tmp_path):
        from dotmaster.plugins.builtin.database import DatabasePlugin

        plugin = DatabasePlugin()
        config = self._db_cfg()
        paths = plugin.generate(config, tmp_path)
        assert (tmp_path / "docker-compose.yml").exists()
        content = (tmp_path / "docker-compose.yml").read_text()
        assert "postgres" in content
        assert "redis" in content

    def test_docker_compose_has_healthchecks(self, tmp_path):
        from dotmaster.plugins.builtin.database import DatabasePlugin

        plugin = DatabasePlugin()
        config = self._db_cfg(engines=["postgresql"])
        plugin.generate(config, tmp_path)
        content = (tmp_path / "docker-compose.yml").read_text()
        assert "healthcheck" in content

    def test_docker_compose_mysql(self, tmp_path):
        from dotmaster.plugins.builtin.database import DatabasePlugin

        plugin = DatabasePlugin()
        config = self._db_cfg(engines=["mysql"])
        plugin.generate(config, tmp_path)
        content = (tmp_path / "docker-compose.yml").read_text()
        assert "mysql" in content
        assert "postgres" not in content

    def test_docker_compose_mongodb(self, tmp_path):
        from dotmaster.plugins.builtin.database import DatabasePlugin

        plugin = DatabasePlugin()
        config = self._db_cfg(engines=["mongodb"])
        plugin.generate(config, tmp_path)
        content = (tmp_path / "docker-compose.yml").read_text()
        assert "mongo" in content

    def test_should_run_when_enabled(self):
        from dotmaster.plugins.builtin.database import DatabasePlugin

        plugin = DatabasePlugin()
        assert plugin.should_run(self._db_cfg())
        assert not plugin.should_run(_cfg(db_enabled=False))

    def test_trigger_key_db_engine(self):
        """Test the db_engine: trigger key works for list matching."""
        from dotmaster.plugins.base import BasePlugin

        config = self._db_cfg(engines=["postgresql"])
        # The _eval_trigger should find 'postgresql' in the engines list
        class _DummyPlugin(BasePlugin):
            name = "dummy"
            description = ""
            triggers = ["db_engine:postgresql"]
            def generate(self, config, output_dir): return []

        assert _DummyPlugin().should_run(config)


class TestAlembicPlugin:
    def _alembic_cfg(self, async_mode=False):
        framework = "fastapi" if async_mode else "flask"
        return _cfg(
            framework=framework,
            db_enabled=True,
            db_engines=["postgresql"],
            orm="sqlalchemy",
            migrations="alembic",
        )

    def test_generates_all_files(self, tmp_path):
        from dotmaster.plugins.builtin.alembic import AlembicPlugin

        plugin = AlembicPlugin()
        paths = plugin.generate(self._alembic_cfg(), tmp_path)
        names = {p.relative_to(tmp_path).as_posix() for p in paths}
        assert "alembic.ini" in names
        assert "alembic/env.py" in names
        assert "alembic/script.py.mako" in names
        assert "alembic/versions/.gitkeep" in names

    def test_alembic_ini_has_pg_url(self, tmp_path):
        from dotmaster.plugins.builtin.alembic import AlembicPlugin

        plugin = AlembicPlugin()
        plugin.generate(self._alembic_cfg(), tmp_path)
        content = (tmp_path / "alembic.ini").read_text()
        assert "postgresql+psycopg2" in content

    def test_alembic_env_has_override_comment(self, tmp_path):
        from dotmaster.plugins.builtin.alembic import AlembicPlugin

        plugin = AlembicPlugin()
        plugin.generate(self._alembic_cfg(), tmp_path)
        content = (tmp_path / "alembic" / "env.py").read_text()
        assert "DATABASE_URL" in content
        assert "target_metadata" in content

    def test_alembic_env_async_for_fastapi(self, tmp_path):
        from dotmaster.plugins.builtin.alembic import AlembicPlugin

        plugin = AlembicPlugin()
        plugin.generate(self._alembic_cfg(async_mode=True), tmp_path)
        content = (tmp_path / "alembic" / "env.py").read_text()
        assert "asyncio" in content

    def test_should_run_on_alembic_migrations(self):
        from dotmaster.plugins.builtin.alembic import AlembicPlugin

        plugin = AlembicPlugin()
        assert plugin.should_run(self._alembic_cfg())
        assert not plugin.should_run(_cfg(migrations="none"))


class TestPrismaPlugin:
    def _prisma_cfg(self, engines=("postgresql",)):
        return _cfg(
            languages=("javascript", "typescript"),
            framework="nextjs",
            pm="npm",
            db_enabled=True,
            db_engines=list(engines),
            orm="prisma",
            migrations="prisma",
        )

    def test_generates_schema_prisma(self, tmp_path):
        from dotmaster.plugins.builtin.prisma import PrismaPlugin

        plugin = PrismaPlugin()
        paths = plugin.generate(self._prisma_cfg(), tmp_path)
        assert (tmp_path / "prisma" / "schema.prisma").exists()

    def test_prisma_schema_uses_correct_provider(self, tmp_path):
        from dotmaster.plugins.builtin.prisma import PrismaPlugin

        plugin = PrismaPlugin()
        plugin.generate(self._prisma_cfg(engines=["postgresql"]), tmp_path)
        content = (tmp_path / "prisma" / "schema.prisma").read_text()
        assert 'provider = "postgresql"' in content

    def test_prisma_mysql_provider(self, tmp_path):
        from dotmaster.plugins.builtin.prisma import PrismaPlugin

        plugin = PrismaPlugin()
        plugin.generate(self._prisma_cfg(engines=["mysql"]), tmp_path)
        content = (tmp_path / "prisma" / "schema.prisma").read_text()
        assert 'provider = "mysql"' in content

    def test_prisma_mongodb_uses_objectid(self, tmp_path):
        from dotmaster.plugins.builtin.prisma import PrismaPlugin

        plugin = PrismaPlugin()
        plugin.generate(self._prisma_cfg(engines=["mongodb"]), tmp_path)
        content = (tmp_path / "prisma" / "schema.prisma").read_text()
        assert "@db.ObjectId" in content

    def test_should_run_on_prisma_orm(self):
        from dotmaster.plugins.builtin.prisma import PrismaPlugin

        plugin = PrismaPlugin()
        assert plugin.should_run(self._prisma_cfg())
        assert not plugin.should_run(_cfg(orm="sqlalchemy"))
