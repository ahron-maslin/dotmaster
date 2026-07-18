"""
tests/test_plugin_contract.py
Tests to ensure all plugins adhere to the expected interface and contract.
"""
from __future__ import annotations

import pytest

from dotmaster.plugins import registry

def test_all_plugins_have_required_metadata():
    for plugin in registry.all():
        assert plugin.name, f"Plugin {plugin.__class__.__name__} missing name"
        assert plugin.description, f"Plugin {plugin.__class__.__name__} missing description"
        assert isinstance(plugin.triggers, list), f"Plugin {plugin.__class__.__name__} triggers must be a list"

def test_all_plugins_have_valid_triggers():
    valid_keys = {
        "linter", "formatter", "testing", "ci", "language", "framework", 
        "package_manager", "docker", "env_file", "editorconfig",
        "database", "db_engine", "orm", "migrations"
    }
    for plugin in registry.all():
        for trigger in plugin.triggers:
            assert ":" in trigger, f"Trigger '{trigger}' in {plugin.name} is malformed, expected 'key:value'"
            key, _, _ = trigger.partition(":")
            assert key in valid_keys, f"Invalid trigger key '{key}' in plugin {plugin.name}"

def test_plugin_run_returns_list_of_paths(tmp_path, mocker):
    """
    Ensure every plugin's run() method returns a list of Paths, 
    without crashing on a generic dummy config.
    """
    from dotmaster.config import DotmasterConfig
    
    # We create a dummy config that triggers everything so generate() can run
    config = DotmasterConfig()
    
    for plugin in registry.all():
        # Mock delegate to False so we always test generate()
        mocker.patch.object(plugin, "delegate", return_value=False)
        try:
            result = plugin.run(config, tmp_path)
            assert isinstance(result, list), f"{plugin.name}.run() did not return a list"
            # It's okay if result is empty, but if it has items they must be Paths
            for path in result:
                assert hasattr(path, "exists"), f"{plugin.name} returned a non-Path object: {type(path)}"
        except Exception as e:
            pytest.fail(f"Plugin {plugin.name} crashed during run(): {e}")
