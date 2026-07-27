"""
tests/test_plugin_contract.py
Every registered plugin must obey dotmaster.plugins.api.Plugin's contract:
plan() is pure (no filesystem writes) and returns FileActions only.
"""

from __future__ import annotations

import pytest

from dotmaster.config import DotmasterConfig
from dotmaster.plugins import registry
from dotmaster.plugins.api import Context, FileAction


def test_all_plugins_have_required_metadata():
    for plugin in registry.all():
        assert plugin.name, f"{plugin.__class__.__name__} missing name"
        assert plugin.description, f"{plugin.__class__.__name__} missing description"
        assert isinstance(plugin.provides, tuple)
        assert isinstance(plugin.outputs, tuple)


def test_plan_returns_only_file_actions_and_writes_nothing(tmp_path):
    """
    Every plugin's plan() must be pure: run it against a config that makes it
    active, then assert the plugin touched nothing on disk.
    """
    config = DotmasterConfig.model_validate(
        {
            "project": {"name": "contract-test"},
            "stack": {
                "languages": ["python", "javascript", "typescript", "go"],
                "framework": "fastapi",
                "package_manager": "poetry",
            },
            "quality": {"linter": "ruff", "formatter": "black", "testing": "pytest"},
            "infrastructure": {
                "docker": True,
                "docker_multistage": True,
                "ci": "github_actions",
                "env_file": True,
                "pre_commit": True,
            },
            "database": {
                "enabled": True,
                "engines": ["postgresql"],
                "orm": "sqlalchemy",
                "migrations": "alembic",
            },
        }
    )
    ctx = Context(root=tmp_path, config=config, offline=True)

    for plugin in registry.all():
        if not plugin.matches(config):
            continue
        before = sorted(tmp_path.rglob("*"))
        try:
            result = plugin.plan(config, ctx)
        except Exception as exc:
            pytest.fail(f"{plugin.name}.plan() raised: {exc}")
        after = sorted(tmp_path.rglob("*"))
        assert before == after, f"{plugin.name}.plan() wrote to disk — plan() must be pure"

        assert isinstance(result, list), f"{plugin.name}.plan() did not return a list"
        for action in result:
            assert isinstance(action, FileAction), (
                f"{plugin.name} returned {type(action)}, not FileAction"
            )
            assert action.plugin == plugin.name, (
                f"{plugin.name} produced a FileAction owned by {action.plugin}"
            )


def test_declared_outputs_are_a_reasonable_hint():
    """outputs should be non-empty for any plugin that writes files."""
    for plugin in registry.all():
        if plugin.name == "package_json":
            continue  # conditionally writes nothing; outputs still documents intent
        assert plugin.outputs, f"{plugin.name} declares no outputs"
