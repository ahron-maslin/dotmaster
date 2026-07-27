"""
tests/test_discovery.py
Third-party plugin discovery: entry points, project-local plugins, and the
trust allowlist that gates them.

This is the fix for the plugin system's core gap — previously
`PluginRegistry` only ever loaded a hardcoded BUILTIN_PLUGINS list, so the
README's "subclass BasePlugin" advice had no way to actually take effect.
"""

from __future__ import annotations

from dotmaster.config import DotmasterConfig
from dotmaster.plugins import PluginLoadError, PluginRegistry, discover
from dotmaster.plugins.api import Plugin


class _EchoPlugin(Plugin):
    name = "echo"
    description = "test plugin"

    def matches(self, config):
        return True

    def plan(self, config, ctx):
        return [self.file("echo.txt", "hello\n")]


def _cfg(**plugins_kwargs) -> DotmasterConfig:
    return DotmasterConfig.model_validate({"project": {"name": "x"}, "plugins": plugins_kwargs})


class TestRegistryRegistration:
    def test_register_rejects_missing_name(self):
        class NoName(Plugin):
            name = ""

            def matches(self, config):
                return True

            def plan(self, config, ctx):
                return []

        registry = PluginRegistry(plugins=[])
        try:
            registry.register(NoName)
            raise AssertionError("expected PluginLoadError")
        except PluginLoadError:
            pass

    def test_register_rejects_non_plugin_subclass(self):
        registry = PluginRegistry(plugins=[])

        class NotAPlugin:
            name = "fake"

        try:
            registry.register(NotAPlugin)
            raise AssertionError("expected PluginLoadError")
        except PluginLoadError:
            pass

    def test_register_rejects_future_api_version(self):
        class FutureApi(_EchoPlugin):
            name = "future"
            requires_api = 999

        registry = PluginRegistry(plugins=[])
        try:
            registry.register(FutureApi)
            raise AssertionError("expected PluginLoadError")
        except PluginLoadError as exc:
            assert "999" in str(exc)


class TestDiscoverTrustModel:
    def test_local_plugin_untrusted_by_default(self, tmp_path):
        plugin_dir = tmp_path / ".dotmaster" / "plugins"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "echo.py").write_text(
            "from dotmaster.plugins.api import Plugin\n"
            "class EchoPlugin(Plugin):\n"
            "    name = 'echo'\n"
            "    description = 'x'\n"
            "    def matches(self, config): return True\n"
            "    def plan(self, config, ctx): return []\n"
        )
        registry, warnings = discover(_cfg(allow=[]), tmp_path)
        assert registry.get("echo") is None
        assert any("not trusted" in w for w in warnings)

    def test_local_plugin_loads_when_named_in_allow(self, tmp_path):
        plugin_dir = tmp_path / ".dotmaster" / "plugins"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "echo.py").write_text(
            "from dotmaster.plugins.api import Plugin\n"
            "class EchoPlugin(Plugin):\n"
            "    name = 'echo'\n"
            "    description = 'x'\n"
            "    def matches(self, config): return True\n"
            "    def plan(self, config, ctx): return []\n"
        )
        registry, _warnings = discover(_cfg(allow=["echo"]), tmp_path)
        assert registry.get("echo") is not None
        assert registry.source_of("echo") == "local"

    def test_wildcard_allow_trusts_everything(self, tmp_path):
        plugin_dir = tmp_path / ".dotmaster" / "plugins"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "echo.py").write_text(
            "from dotmaster.plugins.api import Plugin\n"
            "class EchoPlugin(Plugin):\n"
            "    name = 'echo'\n"
            "    description = 'x'\n"
            "    def matches(self, config): return True\n"
            "    def plan(self, config, ctx): return []\n"
        )
        registry, _ = discover(_cfg(allow=["*"]), tmp_path)
        assert registry.get("echo") is not None

    def test_builtins_always_present_regardless_of_allowlist(self, tmp_path):
        registry, _ = discover(_cfg(allow=[]), tmp_path)
        assert registry.get("gitignore") is not None

    def test_broken_local_plugin_reports_a_warning_not_a_crash(self, tmp_path):
        plugin_dir = tmp_path / ".dotmaster" / "plugins"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "broken.py").write_text("this is not valid python (((\n")
        registry, warnings = discover(_cfg(allow=["*"]), tmp_path)
        assert any("broken" in w for w in warnings)
        # built-ins still work despite the broken plugin
        assert registry.get("gitignore") is not None


class TestDisablePlugin:
    def test_disabled_plugin_never_activates(self):
        registry = PluginRegistry()
        cfg = DotmasterConfig.model_validate(
            {"project": {"name": "x"}, "plugins": {"disable": ["gitignore"]}}
        )
        assert "gitignore" not in [p.name for p in registry.active(cfg)]
