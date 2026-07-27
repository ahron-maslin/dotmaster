"""
dotmaster/core/apply.py
The only module in dotmaster that writes to the user's project.

Application is transactional: every file that will change is captured first,
writes are atomic (temp file + ``os.replace``), and any failure rolls the whole
project back to the state it was in before the command ran.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from dotmaster.core.plan import Change, ChangeKind, Plan
from dotmaster.core.state import STATE_DIR, State, load_state, save_state

logger = logging.getLogger("dotmaster.apply")

BACKUP_DIR = "backups"
DEFAULT_KEEP_BACKUPS = 10


@dataclass
class ApplyResult:
    """What actually happened, for honest reporting."""

    created: list[PurePosixPath] = field(default_factory=list)
    updated: list[PurePosixPath] = field(default_factory=list)
    unchanged: list[PurePosixPath] = field(default_factory=list)
    skipped: list[PurePosixPath] = field(default_factory=list)
    blocked: list[Change] = field(default_factory=list)
    backup: Path | None = None
    rolled_back: bool = False

    @property
    def written(self) -> int:
        return len(self.created) + len(self.updated)


class ApplyError(Exception):
    """A write failed; the project has been rolled back."""


def apply_plan(
    plan: Plan,
    root: Path,
    *,
    state: State | None = None,
    backup: bool = True,
    keep_backups: int = DEFAULT_KEEP_BACKUPS,
) -> ApplyResult:
    """
    Write every change in *plan* to *root*, atomically and reversibly.

    Conflicts and skips are reported, never written.  On any I/O error the
    entire batch is undone and :class:`ApplyError` is raised.
    """
    root = root.resolve()
    state = load_state(root) if state is None else state
    result = ApplyResult(blocked=list(plan.blocked))

    for change in plan.skipped:
        result.skipped.append(change.path)
    for change in plan.unchanged:
        result.unchanged.append(change.path)
        _record(state, change)

    writes = plan.writes
    if not writes:
        save_state(state, root)
        return result

    if backup:
        result.backup = _archive(
            root, [c.path for c in writes if c.old_content is not None], keep_backups
        )

    undo: list[tuple[Path, str | None]] = []
    try:
        for change in writes:
            target = root / Path(str(change.path))
            undo.append((target, change.old_content))
            _atomic_write(target, change.new_content or "", executable=change.action.executable)
            if change.kind is ChangeKind.CREATE:
                result.created.append(change.path)
            else:
                result.updated.append(change.path)
            _record(state, change)
    except OSError as exc:
        _rollback(undo)
        result.rolled_back = True
        raise ApplyError(f"failed writing {exc.filename or 'file'}: {exc}") from exc

    save_state(state, root)
    return result


def _record(state: State, change: Change) -> None:
    from dotmaster.plugins import registry

    plugin = registry.get(change.plugin)
    state.record(
        change.path,
        plugin=change.plugin,
        content=change.new_content
        if change.new_content is not None
        else (change.old_content or ""),
        strategy=change.action.strategy.value,
        plugin_version=getattr(plugin, "version", "") if plugin else "",
    )


def _atomic_write(target: Path, content: str, *, executable: bool = False) -> None:
    """Write via a sibling temp file so a crash can never truncate the original."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.dotmaster.tmp")
    try:
        tmp.write_text(content, encoding="utf-8", newline="\n")
        if executable:
            mode = tmp.stat().st_mode
            tmp.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(tmp, target)
    finally:
        if tmp.exists():  # pragma: no cover - only on a failed replace
            tmp.unlink(missing_ok=True)


def _rollback(undo: list[tuple[Path, str | None]]) -> None:
    """Restore originals; delete anything we created."""
    for target, original in reversed(undo):
        try:
            if original is None:
                target.unlink(missing_ok=True)
            else:
                target.write_text(original, encoding="utf-8", newline="\n")
        except OSError:  # pragma: no cover - best effort
            logger.exception("Rollback failed for %s", target)


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------


def backups_dir(root: Path) -> Path:
    return root / STATE_DIR / BACKUP_DIR


def _archive(root: Path, paths: list[PurePosixPath], keep: int) -> Path | None:
    """
    Zip the current contents of *paths* before they are overwritten.

    Callers are expected to only ever pass paths already validated by
    :func:`dotmaster.core.engine._safe_target`, but containment is re-checked
    here too — cheap insurance against a future caller forgetting to.
    """
    existing: list[tuple[PurePosixPath, Path]] = []
    for rel in paths:
        abs_ = (root / Path(str(rel))).resolve()
        if abs_ != root and root not in abs_.parents:
            logger.warning("Refusing to back up out-of-tree path: %s", rel)
            continue
        if abs_.is_file():
            existing.append((rel, abs_))
    if not existing:
        return None

    directory = backups_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive = directory / f"backup_{stamp}.zip"
    # Guard against two runs inside the same second.
    counter = 1
    while archive.exists():
        archive = directory / f"backup_{stamp}_{counter}.zip"
        counter += 1

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, abs_ in existing:
            zf.write(abs_, arcname=str(rel))

    _prune_backups(directory, keep)
    return archive


def _prune_backups(directory: Path, keep: int) -> None:
    if keep <= 0:
        return
    archives = sorted(directory.glob("backup_*.zip"))
    for stale in archives[:-keep]:
        stale.unlink(missing_ok=True)


def list_backups(root: Path) -> list[Path]:
    directory = backups_dir(root)
    if not directory.exists():
        return []
    return sorted(directory.glob("backup_*.zip"))


def restore_backup(
    archive: Path, root: Path, *, only: list[str] | None = None
) -> list[PurePosixPath]:
    """
    Restore files from *archive* into *root*.

    Entries that would land outside the project are refused, so a hand-crafted
    zip cannot be used to write elsewhere on the filesystem.
    """
    root = root.resolve()
    restored: list[PurePosixPath] = []
    with zipfile.ZipFile(archive) as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            if only and name not in only:
                continue
            target = (root / name).resolve()
            if target != root and root not in target.parents:
                logger.warning("Refusing to restore out-of-tree entry: %s", name)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            restored.append(PurePosixPath(name))
    return restored
