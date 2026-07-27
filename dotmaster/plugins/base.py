"""
dotmaster/plugins/base.py
Backwards-compatible alias for the plugin contract.

The public API moved to :mod:`dotmaster.plugins.api` in 0.3.0, where it is
versioned and documented.  Import from there:

    from dotmaster.plugins.api import Plugin, Context, FileAction
"""

from __future__ import annotations

from dotmaster.plugins.api import API_VERSION, Context, FileAction, MergeStrategy, Plugin

#: Historical name for :class:`dotmaster.plugins.api.Plugin`.
BasePlugin = Plugin

__all__ = [
    "API_VERSION",
    "BasePlugin",
    "Context",
    "FileAction",
    "MergeStrategy",
    "Plugin",
]
