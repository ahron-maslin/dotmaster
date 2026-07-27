"""
dotmaster/plugins/__init__.py
Plugin registry and discovery.

Built-in plugins are always available.  Third-party plugins are discovered from
``dotmaster.plugins`` entry points and from ``.dotmaster/plugins/*.py`` inside
the project, but — because loading a plugin means executing its code — nothing
outside the built-ins loads unless the project's ``dotmaster.yaml`` names it in
``plugins.allow`` (or opts in wholesale with ``allow: ["*"]``).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from dotmaster.plugins.api import API_VERSION, Context, FileAction, Plugin

if TYPE_CHECKING:
    from dotmaster.config import DotmasterConfig

logger = logging.getLogger("dotmaster.plugins")

ENTRY_POINT_GROUP = "dotmaster.plugins"
LOCAL_PLUGIN_DIR = ".dotmaster/plugins"


class PluginLoadError(Exception):
    """A plugin could not be loaded."""


class PluginRegistry:
    """Ordered collection of plugin instances, keyed by name."""

    def __init__(self, plugins: Iterable[type[Plugin] | Plugin] | None = None) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._sources: dict[str, str] = {}
        if plugins is None:
            from dotmaster.plugins.builtin import BUILTIN_PLUGINS

            plugins = BUILTIN_PLUGINS
        for plugin in plugins:
            self.register(plugin, source="builtin")

    # -- registration ----------------------------------------------------

    def register(self, plugin: type[Plugin] | Plugin, *, source: str = "external") -> Plugin:
        instance = plugin() if isinstance(plugin, type) else plugin
        if not getattr(instance, "name", ""):
            raise PluginLoadError(f"{type(instance).__name__} does not set a name")
        if not isinstance(instance, Plugin):
            raise PluginLoadError(
                f"{type(instance).__name__} does not subclass dotmaster.plugins.api.Plugin"
            )
        requires = getattr(instance, "requires_api", API_VERSION)
        if requires > API_VERSION:
            raise PluginLoadError(
                f"plugin '{instance.name}' needs plugin API v{requires} but this "
                f"dotmaster provides v{API_VERSION}; upgrade dotmaster"
            )
        existing = self._plugins.get(instance.name)
        if existing is not None and self._sources.get(instance.name) != source:
            logger.warning(
                "Plugin '%s' from %s overrides the %s implementation.",
                instance.name,
                source,
                self._sources.get(instance.name),
            )
        self._plugins[instance.name] = instance
        self._sources[instance.name] = source
        return instance

    # -- queries ---------------------------------------------------------

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def all(self) -> list[Plugin]:
        return list(self._plugins.values())

    def names(self) -> list[str]:
        return list(self._plugins)

    def source_of(self, name: str) -> str:
        return self._sources.get(name, "unknown")

    def active(self, config: DotmasterConfig) -> list[Plugin]:
        """Plugins that apply to *config*, honouring ``plugins.disable``."""
        disabled = set(config.plugins.disable)
        active: list[Plugin] = []
        for plugin in self._plugins.values():
            if plugin.name in disabled:
                continue
            try:
                if plugin.matches(config):
                    active.append(plugin)
            except Exception:
                logger.exception("Plugin %s raised in matches()", plugin.name)
        return active

    def select(self, names: Sequence[str]) -> tuple[list[Plugin], list[str]]:
        """Resolve explicit plugin names; returns (found, unknown)."""
        found: list[Plugin] = []
        unknown: list[str] = []
        for name in names:
            plugin = self.get(name)
            if plugin is None:
                unknown.append(name)
            else:
                found.append(plugin)
        return found, unknown

    def suggest(self, name: str) -> str | None:
        import difflib

        matches = difflib.get_close_matches(name, self.names(), n=1)
        return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _allowed(name: str, allow: Sequence[str]) -> bool:
    return "*" in allow or name in allow


def discover(
    config: DotmasterConfig | None = None,
    root: Path | None = None,
    *,
    registry: PluginRegistry | None = None,
) -> tuple[PluginRegistry, list[str]]:
    """
    Build a registry of built-in plus permitted third-party plugins.

    Returns the registry and a list of human-readable warnings (plugins that
    were found but not trusted, or that failed to load).
    """
    reg = registry or PluginRegistry()
    warnings: list[str] = []
    allow = list(config.plugins.allow) if config else []

    for name, loader, origin in _candidates(root):
        if not _allowed(name, allow):
            warnings.append(
                f"plugin '{name}' ({origin}) is installed but not trusted; "
                f"add it to plugins.allow in dotmaster.yaml to enable it"
            )
            continue
        try:
            obj = loader()
        except Exception as exc:
            warnings.append(f"plugin '{name}' ({origin}) failed to load: {exc}")
            continue
        try:
            reg.register(obj, source=origin)
        except PluginLoadError as exc:
            warnings.append(str(exc))
    return reg, warnings


def _candidates(root: Path | None):
    """Yield ``(name, loader, origin)`` for every discoverable plugin."""
    from importlib.metadata import entry_points

    try:
        points: Iterable = entry_points(group=ENTRY_POINT_GROUP)
    except Exception:  # pragma: no cover - very old importlib backports
        points = ()
    for point in points:
        yield point.name, point.load, "entry-point"

    if root is None:
        return
    local_dir = root / LOCAL_PLUGIN_DIR
    if not local_dir.is_dir():
        return
    for path in sorted(local_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        yield path.stem, _make_path_loader(path), "local"


def _make_path_loader(path: Path):
    def loader():
        import importlib.util

        spec = importlib.util.spec_from_file_location(f"dotmaster_local_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"cannot import {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, Plugin)
                and value is not Plugin
                and value.name
            ):
                return value
        raise PluginLoadError(f"{path} defines no Plugin subclass with a name")

    return loader


#: Built-in registry.  Commands call :func:`discover` to extend it per project.
registry = PluginRegistry()

__all__ = [
    "API_VERSION",
    "Context",
    "FileAction",
    "Plugin",
    "PluginLoadError",
    "PluginRegistry",
    "discover",
    "registry",
]
