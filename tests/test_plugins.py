"""
tests/test_plugins.py
Unit tests for the plugin registry and individual built-in plugins, against
the plan()-based contract (dotmaster.plugins.api.Plugin).
"""

from __future__ import annotations

from dotmaster.config import DotmasterConfig
from dotmaster.plugins import registry
from dotmaster.plugins.api import Context


def _cfg(**overrides) -> DotmasterConfig:
    base = {
        "project": {"name": "test"},
        "stack": {
            "languages": list(overrides.pop("languages", ["python"])),
            "framework": overrides.pop("framework", "fastapi"),
            "package_manager": overrides.pop("pm", "poetry"),
        },
        "quality": {
            "linter": overrides.pop("linter", "ruff"),
            "formatter": overrides.pop("formatter", "black"),
            "testing": overrides.pop("testing", "pytest"),
        },
        "infrastructure": {
            "docker": overrides.pop("docker", True),
            "docker_multistage": True,
            "ci": overrides.pop("ci", "github_actions"),
            "env_file": overrides.pop("env_file", True),
            "editorconfig": overrides.pop("editorconfig", True),
        },
        "database": {
            "enabled": overrides.pop("db_enabled", False),
            "engines": overrides.pop("db_engines", None) or [],
            "orm": overrides.pop("orm", "none"),
            "migrations": overrides.pop("migrations", "none"),
        },
    }
    return DotmasterConfig.model_validate(base)


def _ctx(tmp_path, config, *, offline: bool = True) -> Context:
    return Context(root=tmp_path, config=config, offline=offline)


class TestPluginRegistry:
    def test_all_returns_instances(self):
        assert len(registry.all()) > 0

    def test_get_known_plugin(self):
        p = registry.get("gitignore")
        assert p is not None and p.name == "gitignore"

    def test_get_unknown_returns_none(self):
        assert registry.get("nonexistent_plugin") is None

    def test_suggest_close_match(self):
        assert registry.suggest("eslnt") == "eslint"

    def test_names_includes_builtins(self):
        for expected in ("gitignore", "eslint", "prettier", "docker", "ruff"):
            assert expected in registry.names()

    def test_active_python_config(self):
        active_names = [p.name for p in registry.active(_cfg())]
        for expected in (
            "gitignore",
            "ruff",
            "pyproject",
            "docker",
            "github_actions",
            "dotenv",
            "editorconfig",
        ):
            assert expected in active_names

    def test_active_no_eslint_for_python(self):
        assert "eslint" not in [p.name for p in registry.active(_cfg())]

    def test_active_js_config(self):
        active_names = [
            p.name
            for p in registry.active(
                _cfg(
                    languages=["javascript", "typescript"],
                    framework="nextjs",
                    pm="npm",
                    linter="eslint",
                    formatter="prettier",
                    testing="jest",
                )
            )
        ]
        assert "eslint" in active_names
        assert "prettier" in active_names
        assert "gitignore" in active_names
        assert "ruff" not in active_names


class TestGitignorePlugin:
    def test_offline_uses_bundled_template(self, tmp_path):
        from dotmaster.plugins.builtin.gitignore import GitignorePlugin

        plugin = GitignorePlugin()
        actions = plugin.plan(_cfg(languages=["python"]), _ctx(tmp_path, _cfg(), offline=True))
        assert len(actions) == 1
        assert "pycache" in actions[0].content.lower() or "python" in actions[0].content.lower()

    def test_always_matches(self):
        from dotmaster.plugins.builtin.gitignore import GitignorePlugin

        assert GitignorePlugin().matches(_cfg())


class TestEditorConfigPlugin:
    def test_generates_editorconfig(self, tmp_path):
        from dotmaster.plugins.builtin.editorconfig import EditorConfigPlugin

        actions = EditorConfigPlugin().plan(_cfg(), _ctx(tmp_path, _cfg()))
        assert actions[0].path.name == ".editorconfig"
        assert "root = true" in actions[0].content

    def test_matches_respects_flag(self):
        from dotmaster.plugins.builtin.editorconfig import EditorConfigPlugin

        plugin = EditorConfigPlugin()
        cfg = _cfg()
        cfg.infrastructure.editorconfig = False
        assert not plugin.matches(cfg)


class TestDockerPlugin:
    def test_generates_dockerfile_and_ignore(self, tmp_path):
        from dotmaster.plugins.builtin.docker import DockerPlugin

        cfg = _cfg(docker=True)
        actions = DockerPlugin().plan(cfg, _ctx(tmp_path, cfg))
        names = {a.path.name for a in actions}
        assert "Dockerfile" in names
        assert ".dockerignore" in names

    def test_does_not_match_without_docker(self):
        from dotmaster.plugins.builtin.docker import DockerPlugin

        assert not DockerPlugin().matches(_cfg(docker=False))

    def test_pip_without_requirements_installs_from_pyproject(self, tmp_path):
        from dotmaster.plugins.builtin.docker import DockerPlugin

        cfg = _cfg(pm="pip", docker=True)
        actions = DockerPlugin().plan(cfg, _ctx(tmp_path, cfg))
        dockerfile = next(a for a in actions if a.path.name == "Dockerfile").content
        assert "requirements.txt" not in dockerfile
        assert "pip install --no-cache-dir ." in dockerfile


class TestDotenvPlugin:
    def test_generates_env_example(self, tmp_path):
        from dotmaster.plugins.builtin.dotenv import DotenvPlugin

        cfg = _cfg(env_file=True)
        actions = DotenvPlugin().plan(cfg, _ctx(tmp_path, cfg))
        assert actions[0].path.name == ".env.example"


class TestDatabasePlugin:
    def _db_cfg(self, engines=("postgresql", "redis"), orm="sqlalchemy", mig="alembic"):
        return _cfg(db_enabled=True, db_engines=list(engines), orm=orm, migrations=mig)

    def test_generates_docker_compose(self, tmp_path):
        from dotmaster.plugins.builtin.database import DatabasePlugin

        cfg = self._db_cfg()
        actions = DatabasePlugin().plan(cfg, _ctx(tmp_path, cfg))
        content = actions[0].content
        assert "postgres" in content
        assert "redis" in content

    def test_mysql_excludes_postgres(self, tmp_path):
        from dotmaster.plugins.builtin.database import DatabasePlugin

        cfg = self._db_cfg(engines=["mysql"])
        content = DatabasePlugin().plan(cfg, _ctx(tmp_path, cfg))[0].content
        assert "mysql" in content
        assert "postgres" not in content

    def test_matches_when_enabled(self):
        from dotmaster.plugins.builtin.database import DatabasePlugin

        plugin = DatabasePlugin()
        assert plugin.matches(self._db_cfg())
        assert not plugin.matches(_cfg(db_enabled=False))


class TestAlembicPlugin:
    def _alembic_cfg(self, async_mode=False):
        return _cfg(
            framework="fastapi" if async_mode else "flask",
            db_enabled=True,
            db_engines=["postgresql"],
            orm="sqlalchemy",
            migrations="alembic",
        )

    def test_generates_all_files(self, tmp_path):
        from dotmaster.plugins.builtin.alembic import AlembicPlugin

        cfg = self._alembic_cfg()
        actions = AlembicPlugin().plan(cfg, _ctx(tmp_path, cfg))
        names = {str(a.path) for a in actions}
        assert names == {
            "alembic.ini",
            "alembic/env.py",
            "alembic/script.py.mako",
            "alembic/versions/.gitkeep",
        }

    def test_alembic_ini_has_pg_url(self, tmp_path):
        from dotmaster.plugins.builtin.alembic import AlembicPlugin

        cfg = self._alembic_cfg()
        actions = AlembicPlugin().plan(cfg, _ctx(tmp_path, cfg))
        ini = next(a for a in actions if str(a.path) == "alembic.ini")
        assert "postgresql+psycopg2" in ini.content

    def test_async_for_fastapi(self, tmp_path):
        from dotmaster.plugins.builtin.alembic import AlembicPlugin

        cfg = self._alembic_cfg(async_mode=True)
        actions = AlembicPlugin().plan(cfg, _ctx(tmp_path, cfg))
        env = next(a for a in actions if str(a.path) == "alembic/env.py")
        assert "asyncio" in env.content

    def test_matches_on_alembic_migrations(self):
        from dotmaster.plugins.builtin.alembic import AlembicPlugin

        plugin = AlembicPlugin()
        assert plugin.matches(self._alembic_cfg())
        assert not plugin.matches(_cfg(migrations="none"))


class TestPrismaPlugin:
    def _prisma_cfg(self, engines=("postgresql",)):
        return _cfg(
            languages=["javascript", "typescript"],
            framework="nextjs",
            pm="npm",
            db_enabled=True,
            db_engines=list(engines),
            orm="prisma",
            migrations="prisma",
        )

    def test_generates_schema(self, tmp_path):
        from dotmaster.plugins.builtin.prisma import PrismaPlugin

        cfg = self._prisma_cfg()
        actions = PrismaPlugin().plan(cfg, _ctx(tmp_path, cfg))
        assert str(actions[0].path) == "prisma/schema.prisma"

    def test_mongodb_uses_object_id(self, tmp_path):
        from dotmaster.plugins.builtin.prisma import PrismaPlugin

        cfg = self._prisma_cfg(engines=["mongodb"])
        content = PrismaPlugin().plan(cfg, _ctx(tmp_path, cfg))[0].content
        assert "@db.ObjectId" in content

    def test_matches_on_prisma_orm(self):
        from dotmaster.plugins.builtin.prisma import PrismaPlugin

        plugin = PrismaPlugin()
        assert plugin.matches(self._prisma_cfg())
        assert not plugin.matches(_cfg(orm="sqlalchemy"))


class TestRuffPyprojectNoDuplication:
    """Regression: ruff.toml and pyproject.toml used to both own [tool.ruff]."""

    def test_pyproject_never_emits_ruff_section(self, tmp_path):
        from dotmaster.plugins.builtin.pyproject import PyprojectPlugin

        cfg = _cfg(linter="ruff")
        actions = PyprojectPlugin().plan(cfg, _ctx(tmp_path, cfg))
        assert "[tool.ruff]" not in actions[0].content

    def test_ruff_plugin_owns_ruff_toml(self, tmp_path):
        from dotmaster.plugins.builtin.ruff import RuffPlugin

        cfg = _cfg(linter="ruff")
        actions = RuffPlugin().plan(cfg, _ctx(tmp_path, cfg))
        assert str(actions[0].path) == "ruff.toml"


class TestESLintPlugin:
    def test_flat_config_is_default(self, tmp_path):
        from dotmaster.plugins.builtin.eslint import ESLintPlugin

        cfg = _cfg(languages=["typescript"], linter="eslint")
        actions = ESLintPlugin().plan(cfg, _ctx(tmp_path, cfg))
        assert [str(a.path) for a in actions] == ["eslint.config.mjs"]

    def test_legacy_mode_via_settings(self, tmp_path):
        from dotmaster.plugins.builtin.eslint import ESLintPlugin

        cfg = _cfg(languages=["typescript"], linter="eslint")
        cfg.plugins.settings["eslint"] = {"legacy": True}
        actions = ESLintPlugin().plan(cfg, _ctx(tmp_path, cfg))
        paths = {str(a.path) for a in actions}
        assert paths == {".eslintrc.json", ".eslintignore"}

    def test_legacy_json_is_valid_without_react(self, tmp_path):
        import json

        from dotmaster.plugins.builtin.eslint import ESLintPlugin

        cfg = _cfg(languages=["typescript"], framework="express", linter="eslint")
        cfg.plugins.settings["eslint"] = {"legacy": True}
        actions = ESLintPlugin().plan(cfg, _ctx(tmp_path, cfg))
        eslintrc = next(a for a in actions if str(a.path) == ".eslintrc.json")
        data = json.loads(eslintrc.content)  # must not raise
        assert "@typescript-eslint" in data["plugins"]

    def test_legacy_json_is_valid_with_react_and_jest(self, tmp_path):
        import json

        from dotmaster.plugins.builtin.eslint import ESLintPlugin

        cfg = _cfg(languages=["typescript"], framework="nextjs", linter="eslint", testing="jest")
        cfg.plugins.settings["eslint"] = {"legacy": True}
        actions = ESLintPlugin().plan(cfg, _ctx(tmp_path, cfg))
        eslintrc = next(a for a in actions if str(a.path) == ".eslintrc.json")
        data = json.loads(eslintrc.content)
        assert "react" in data["plugins"]
        assert "jest" in data["plugins"]


class TestGitignorePluginOnline:
    def test_offline_never_calls_fetch(self, tmp_path):
        from dotmaster.plugins.builtin.gitignore import GitignorePlugin

        cfg = _cfg()
        ctx = _ctx(tmp_path, cfg, offline=True)
        assert callable(ctx.fetch)
        calls = []
        object.__setattr__(ctx, "fetch", lambda *a, **k: calls.append(1) or None)
        GitignorePlugin().plan(cfg, ctx)
        assert calls == []

    def test_online_uses_api_response_when_it_looks_sane(self, tmp_path):
        from dotmaster.plugins.builtin.gitignore import GitignorePlugin

        cfg = _cfg()
        ctx = _ctx(tmp_path, cfg, offline=False)
        fake_response = "# comment\n" + "\n".join(f"line{i}/" for i in range(20))
        object.__setattr__(ctx, "fetch", lambda *a, **k: fake_response)
        actions = GitignorePlugin().plan(cfg, ctx)
        assert "line0/" in actions[0].content

    def test_online_falls_back_on_garbage_response(self, tmp_path):
        from dotmaster.plugins.builtin.gitignore import GitignorePlugin

        cfg = _cfg(languages=["python"])
        ctx = _ctx(tmp_path, cfg, offline=False)
        object.__setattr__(ctx, "fetch", lambda *a, **k: "not a real gitignore")
        actions = GitignorePlugin().plan(cfg, ctx)
        assert "pycache" in actions[0].content.lower()

    def test_online_falls_back_when_fetch_returns_none(self, tmp_path):
        from dotmaster.plugins.builtin.gitignore import GitignorePlugin

        cfg = _cfg(languages=["python"])
        ctx = _ctx(tmp_path, cfg, offline=False)
        object.__setattr__(ctx, "fetch", lambda *a, **k: None)
        actions = GitignorePlugin().plan(cfg, ctx)
        assert "pycache" in actions[0].content.lower()


class TestPackageJsonPlugin:
    def test_noop_when_no_package_json(self, tmp_path):
        from dotmaster.plugins.builtin.package_json import PackageJsonPlugin

        cfg = _cfg(languages=["typescript"], linter="eslint")
        actions = PackageJsonPlugin().plan(cfg, _ctx(tmp_path, cfg))
        assert actions == []

    def test_adds_scripts_when_package_json_exists(self, tmp_path):
        from dotmaster.plugins.builtin.package_json import PackageJsonPlugin

        (tmp_path / "package.json").write_text('{"name": "x"}')
        cfg = _cfg(languages=["typescript"], linter="eslint", formatter="prettier", testing="jest")
        actions = PackageJsonPlugin().plan(cfg, _ctx(tmp_path, cfg))
        data = __import__("json").loads(actions[0].content)
        assert data["scripts"]["lint"] == "eslint ."
        assert data["scripts"]["test"] == "jest"
