"""
dotmaster.core — the pure, I/O-free heart of dotmaster.

The only module in this package permitted to touch the filesystem is
:mod:`dotmaster.core.apply`.  Everything else takes data in and returns data
out, which is what makes ``--dry-run``, ``diff``, ``check`` and rollback
possible at all.

Flow::

    config + plugins ──▶ engine.build_plan() ──▶ Plan ──▶ apply.apply_plan()
                                                  │
                                                  └──▶ diff / check (read-only)
"""

from __future__ import annotations

from dotmaster.core.plan import (
    Change,
    ChangeKind,
    Conflict,
    FileAction,
    MergeStrategy,
    Plan,
)

__all__ = [
    "Change",
    "ChangeKind",
    "Conflict",
    "FileAction",
    "MergeStrategy",
    "Plan",
]
