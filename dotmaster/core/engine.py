"""
dotmaster/core/engine.py
Turns a configuration plus a set of plugins into a :class:`Plan`.

Reads the filesystem, never writes to it.  A plugin that raises is reported and
skipped — one bad plugin must not take down the run — and two plugins claiming
the same file or the same capability is an error surfaced to the user rather
than a silent race.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from dotmaster.core.merge import MergeError, merge
from dotmaster.core.plan import (
    Change,
    ChangeKind,
    Conflict,
    FileAction,
    MergeStrategy,
    Plan,
)
from dotmaster.core.state import State, load_state

if TYPE_CHECKING:
    from dotmaster.config import DotmasterConfig
    from dotmaster.plugins.api import Plugin

logger = logging.getLogger("dotmaster.engine")


def build_plan(
    config: DotmasterConfig,
    root: Path,
    plugins: Sequence[Plugin],
    *,
    state: State | None = None,
    force: bool = False,
    offline: bool | None = None,
) -> Plan:
    """
    Compute every change *plugins* would make to *root* under *config*.

    Parameters
    ----------
    force:
        Treat user-modified files as replaceable instead of as conflicts.
    offline:
        Override the config's network setting (``True`` disables all egress).
    """
    from dotmaster.plugins.api import Context

    root = root.resolve()
    state = load_state(root) if state is None else state
    plan = Plan()

    ctx = Context(
        root=root,
        config=config,
        offline=config.options.offline if offline is None else offline,
    )

    actions: list[FileAction] = []
    for plugin in plugins:
        try:
            produced = plugin.plan(config, ctx)
        except Exception as exc:
            logger.exception("Plugin %s failed while planning", plugin.name)
            plan.errors[plugin.name] = f"{type(exc).__name__}: {exc}"
            continue
        if produced is None:
            continue
        if not isinstance(produced, (list, tuple)):
            plan.errors[plugin.name] = (
                f"plan() must return a list of FileAction, got {type(produced).__name__}"
            )
            continue
        for action in produced:
            if not isinstance(action, FileAction):
                plan.errors[plugin.name] = (
                    f"plan() returned {type(action).__name__}, expected FileAction"
                )
                break
            actions.append(action)

    plan.conflicts.extend(_detect_conflicts(actions, plugins))
    contested = {c.subject for c in plan.conflicts if c.detail.startswith("file")}

    for action in actions:
        if str(action.path) in contested:
            continue
        plan.changes.append(_resolve(action, root, state, force=force))

    plan.changes.sort(key=lambda c: str(c.path))
    return plan


def _detect_conflicts(actions: Iterable[FileAction], plugins: Sequence[Plugin]) -> list[Conflict]:
    """Two plugins writing one file, or both providing the same capability."""
    conflicts: list[Conflict] = []

    by_path: dict[str, set[str]] = defaultdict(set)
    for action in actions:
        by_path[str(action.path)].add(action.plugin)
    for path, owners in sorted(by_path.items()):
        if len(owners) > 1:
            conflicts.append(
                Conflict(
                    subject=path,
                    plugins=tuple(sorted(owners)),
                    detail=(
                        f"file is claimed by {len(owners)} plugins: {', '.join(sorted(owners))}"
                    ),
                )
            )

    by_capability: dict[str, set[str]] = defaultdict(set)
    for plugin in plugins:
        for capability in getattr(plugin, "provides", ()):
            by_capability[capability].add(plugin.name)
    for capability, owners in sorted(by_capability.items()):
        if len(owners) > 1:
            conflicts.append(
                Conflict(
                    subject=capability,
                    plugins=tuple(sorted(owners)),
                    detail=(
                        f"capability '{capability}' is provided by "
                        f"{', '.join(sorted(owners))} — enable only one"
                    ),
                )
            )
    return conflicts


def _resolve(action: FileAction, root: Path, state: State, *, force: bool) -> Change:
    """Compare one declared file against the disk and the ownership ledger."""
    target = _safe_target(root, action.path)
    if target is None:
        return Change(
            action=action,
            kind=ChangeKind.CONFLICT,
            reason="path escapes the project directory",
        )

    if not target.exists():
        return Change(action=action, kind=ChangeKind.CREATE, new_content=action.content)

    if target.is_dir():
        return Change(
            action=action,
            kind=ChangeKind.CONFLICT,
            reason="a directory exists at this path",
        )

    try:
        existing = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return Change(
            action=action,
            kind=ChangeKind.CONFLICT,
            reason=f"cannot read existing file: {exc}",
        )

    owned = state.owns(action.path, existing)
    strategy = action.strategy

    if strategy is MergeStrategy.CREATE_ONLY:
        return Change(
            action=action,
            kind=ChangeKind.SKIP,
            old_content=existing,
            reason="file exists and this plugin only creates it once",
        )

    if strategy is MergeStrategy.OVERWRITE:
        if owned or force:
            new_content = action.content
        else:
            return Change(
                action=action,
                kind=ChangeKind.CONFLICT,
                old_content=existing,
                new_content=action.content,
                reason=(
                    "modified since dotmaster generated it"
                    if state.is_tracked(action.path)
                    else "already exists and was not created by dotmaster"
                ),
            )
    elif owned and strategy is MergeStrategy.MERGE:
        # We wrote this file and nobody has touched it: regenerate wholesale so
        # configuration changes actually propagate.
        new_content = action.content
    else:
        try:
            new_content = merge(action.path, existing, action.content, strategy)
        except MergeError as exc:
            if force:
                new_content = action.content
            else:
                return Change(
                    action=action,
                    kind=ChangeKind.CONFLICT,
                    old_content=existing,
                    new_content=action.content,
                    reason=str(exc),
                )

    kind = ChangeKind.UNCHANGED if new_content == existing else ChangeKind.UPDATE
    return Change(action=action, kind=kind, old_content=existing, new_content=new_content)


def safe_target(root: Path, rel: PurePosixPath | str) -> Path | None:
    """
    Resolve *rel* inside *root*, refusing anything that escapes it.

    ``Path.relative_to`` is purely lexical, so containment has to be checked
    against fully resolved paths — including symlinked parents, which would
    otherwise let a crafted repository redirect a write outside the project.

    Used everywhere a path arrives from data dotmaster does not fully
    control — a plugin's declared output, or an entry in the state ledger —
    before that path is read, written or deleted. Public because callers
    outside this module (e.g. ``dotmaster remove``) need the same guarantee.
    """
    candidate = root / Path(str(rel))
    try:
        resolved = candidate.resolve()
    except OSError:  # pragma: no cover - unresolvable path
        return None
    if resolved != root and root not in resolved.parents:
        return None
    return candidate


# Backwards-compatible private alias used within this module.
_safe_target = safe_target
