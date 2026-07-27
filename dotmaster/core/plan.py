"""
dotmaster/core/plan.py
The data model that separates *deciding what to write* from *writing it*.

A plugin returns :class:`FileAction` objects — a declaration of intent.  The
engine turns those into :class:`Change` objects by comparing them with what is
already on disk and what dotmaster last generated.  Only then does
:mod:`dotmaster.core.apply` touch the filesystem.

This split is what makes ``--dry-run``, ``dotmaster diff``, ``dotmaster check``,
conflict detection and transactional rollback possible.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath


def sha256(content: str) -> str:
    """Stable content hash used for ownership and drift detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class MergeStrategy(str, Enum):
    """How a :class:`FileAction` should be reconciled with an existing file."""

    #: Write only if the file does not exist; never touch it again.
    CREATE_ONLY = "create_only"
    #: Always replace the whole file (conflicts if the user edited it).
    OVERWRITE = "overwrite"
    #: Structure-aware merge (JSON / YAML / TOML), preserving user keys.
    MERGE = "merge"
    #: Replace only the region between dotmaster markers, keep the rest.
    MANAGED_BLOCK = "managed_block"
    #: Union of lines, order-preserving — for ignore files.
    LINE_UNION = "line_union"


class ChangeKind(str, Enum):
    """What applying a :class:`Change` would actually do."""

    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"
    #: The file was modified by the user since dotmaster generated it and the
    #: strategy cannot merge safely.  Skipped unless forced.
    CONFLICT = "conflict"
    #: Deliberately not written (CREATE_ONLY on an existing file).
    SKIP = "skip"

    @property
    def writes(self) -> bool:
        return self in (ChangeKind.CREATE, ChangeKind.UPDATE)


@dataclass(frozen=True)
class FileAction:
    """
    A plugin's declaration that a file should exist with this content.

    ``path`` is always relative to the project root and always POSIX-style so
    that a ``dotmaster.yaml`` written on Windows works on Linux.
    """

    path: PurePosixPath
    content: str
    plugin: str
    strategy: MergeStrategy = MergeStrategy.MERGE
    #: Set the executable bit (hooks, scripts).
    executable: bool = False
    #: Shown next to the file in ``diff`` / ``--dry-run`` output.
    description: str = ""

    def __post_init__(self) -> None:
        # Normalise str → PurePosixPath so plugins can pass either.
        if not isinstance(self.path, PurePosixPath):
            object.__setattr__(self, "path", PurePosixPath(str(self.path).replace("\\", "/")))
        if self.path.is_absolute() or ".." in self.path.parts:
            raise ValueError(f"Plugin '{self.plugin}' declared an out-of-tree path: {self.path}")

    @property
    def content_hash(self) -> str:
        return sha256(self.content)


@dataclass(frozen=True)
class Conflict:
    """Two plugins claiming the same file, or the same capability."""

    subject: str
    plugins: tuple[str, ...]
    detail: str


@dataclass
class Change:
    """A :class:`FileAction` resolved against the current state of the disk."""

    action: FileAction
    kind: ChangeKind
    #: Content currently on disk (None when the file does not exist).
    old_content: str | None = None
    #: Content that would be written after merging (None when nothing is written).
    new_content: str | None = None
    #: Why this change is a conflict or a skip.
    reason: str = ""

    @property
    def path(self) -> PurePosixPath:
        return self.action.path

    @property
    def plugin(self) -> str:
        return self.action.plugin

    def diff(self, *, context: int = 3) -> str:
        """Unified diff between what is on disk and what would be written."""
        import difflib

        old = (self.old_content or "").splitlines(keepends=True)
        new = self.new_content if self.new_content is not None else self.old_content or ""
        return "".join(
            difflib.unified_diff(
                old,
                new.splitlines(keepends=True),
                fromfile=f"a/{self.path}",
                tofile=f"b/{self.path}",
                n=context,
            )
        )

    @property
    def stat(self) -> tuple[int, int]:
        """(lines added, lines removed) — for compact summaries."""
        added = removed = 0
        for line in self.diff(context=0).splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        return added, removed


@dataclass
class Plan:
    """The complete set of changes a command would make."""

    changes: list[Change] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Plugins that raised while planning — the run continues without them.
    errors: dict[str, str] = field(default_factory=dict)

    def of_kind(self, *kinds: ChangeKind) -> list[Change]:
        return [c for c in self.changes if c.kind in kinds]

    @property
    def creates(self) -> list[Change]:
        return self.of_kind(ChangeKind.CREATE)

    @property
    def updates(self) -> list[Change]:
        return self.of_kind(ChangeKind.UPDATE)

    @property
    def unchanged(self) -> list[Change]:
        return self.of_kind(ChangeKind.UNCHANGED)

    @property
    def blocked(self) -> list[Change]:
        return self.of_kind(ChangeKind.CONFLICT)

    @property
    def skipped(self) -> list[Change]:
        return self.of_kind(ChangeKind.SKIP)

    @property
    def writes(self) -> list[Change]:
        return [c for c in self.changes if c.kind.writes]

    @property
    def is_noop(self) -> bool:
        return not self.writes

    @property
    def is_clean(self) -> bool:
        """True when the project already matches its configuration."""
        return not self.writes and not self.blocked and not self.errors
