"""
tests/test_backwards_compat.py
`dotmaster.plugins.base` is a 0.2-era import path kept alive as an alias so
existing third-party plugin code (written against the old BasePlugin name)
doesn't break outright on upgrade — it still needs to be rewritten against
the plan()-based contract, but at least the import succeeds.
"""

from __future__ import annotations


def test_base_plugin_alias_points_at_the_real_contract():
    from dotmaster.plugins.api import Plugin
    from dotmaster.plugins.base import BasePlugin

    assert BasePlugin is Plugin


def test_base_module_reexports_context_and_file_action():
    from dotmaster.plugins.base import Context, FileAction

    assert Context is not None
    assert FileAction is not None
