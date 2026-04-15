"""
dotmaster/plugins/__init__.py
Global plugin registry — collects and manages all available plugins.
"""
from __future__ import annotations

from dotmaster.plugins.base import BasePlugin
from dotmaster.plugins.builtin import BUILTIN_PLUGINS


class PluginRegistry:
    """
    Central registry of dotmaster plugins.

    Built-in plugins are registered automatically.  Third-party plugins can
    be added via ``registry.register(MyPlugin)``.
    """

    def __init__(
        self, plugins: list[type[BasePlugin]] | None = None
    ) -> None:
        self._plugins: dict[str, type[BasePlugin]] = {}
        for cls in plugins or BUILTIN_PLUGINS:
            self.register(cls)

    def register(self, plugin_cls: type[BasePlugin]) -> None:
        """Register a plugin class."""
        if not plugin_cls.name:
            raise ValueError(f"Plugin {plugin_cls} has no name set.")
        self._plugins[plugin_cls.name] = plugin_cls

    def get(self, name: str) -> BasePlugin | None:
        """Return an instance of the plugin with the given *name*, or None."""
        cls = self._plugins.get(name)
        return cls() if cls else None

    def all(self) -> list[BasePlugin]:
        """Return instances of all registered plugins."""
        return [cls() for cls in self._plugins.values()]

    def names(self) -> list[str]:
        """Return all registered plugin names."""
        return list(self._plugins.keys())

    def active(self, config) -> list[BasePlugin]:
        """
        Return instances of plugins that ``should_run`` for *config*.
        The list is deterministic (insertion order).
        """
        return [p for p in self.all() if p.should_run(config)]


# Module-level singleton — import and use this directly.
registry = PluginRegistry()

__all__ = ["registry", "PluginRegistry"]
