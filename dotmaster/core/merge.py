"""
dotmaster/core/merge.py
Reconciling generated content with a file the user may have edited.

Guiding rule, applied consistently everywhere: **the user's edits win.**
Generated content fills gaps and adds new keys; it never silently replaces a
value a human typed.  When dotmaster still owns a file byte-for-byte (verified
via the hash ledger in :mod:`dotmaster.core.state`) the engine bypasses merging
entirely and rewrites it, so configuration changes still propagate.
"""

from __future__ import annotations

import json
import logging
from pathlib import PurePosixPath
from typing import Any

import tomlkit
import yaml

from dotmaster.core.plan import MergeStrategy

logger = logging.getLogger("dotmaster.merge")

BLOCK_START = "dotmaster:start"
BLOCK_END = "dotmaster:end"

#: Files without a useful suffix whose format we know by name.
_FILENAME_FORMATS: dict[str, str] = {
    ".eslintrc": "json",
    ".prettierrc": "json",
    ".babelrc": "json",
    ".stylelintrc": "json",
    ".markdownlintrc": "json",
    "dotmaster.yaml": "yaml",
}

_SUFFIX_FORMATS: dict[str, str] = {
    ".json": "json",
    ".jsonc": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}


class MergeError(Exception):
    """Raised when two files genuinely cannot be reconciled."""


def detect_format(path: PurePosixPath | str) -> str | None:
    """Return ``"json"`` / ``"yaml"`` / ``"toml"``, or None for plain text."""
    p = PurePosixPath(str(path))
    if p.name in _FILENAME_FORMATS:
        return _FILENAME_FORMATS[p.name]
    return _SUFFIX_FORMATS.get(p.suffix.lower())


def default_strategy(path: PurePosixPath | str) -> MergeStrategy:
    """The sensible reconciliation strategy for a path, used by plugins."""
    p = PurePosixPath(str(path))
    if detect_format(p):
        return MergeStrategy.MERGE
    if p.name.endswith("ignore") or p.name == ".editorconfig":
        return MergeStrategy.MANAGED_BLOCK
    # Whole-program files (Dockerfile, env templates, source) cannot be
    # meaningfully merged; the engine treats user edits as conflicts.
    return MergeStrategy.OVERWRITE


def comment_prefix(path: PurePosixPath | str) -> str:
    p = PurePosixPath(str(path))
    if p.suffix.lower() in (".js", ".mjs", ".cjs", ".ts", ".prisma", ".java", ".go", ".rs"):
        return "//"
    return "#"


# ---------------------------------------------------------------------------
# Structured merges — existing values win
# ---------------------------------------------------------------------------


def _deep_merge(base: Any, incoming: Any) -> Any:
    """
    Merge *incoming* into *base* without overwriting anything already set.

    - dicts recurse
    - lists become an order-preserving union
    - scalars keep the *base* (user) value
    """
    if isinstance(base, dict) and isinstance(incoming, dict):
        for key, value in incoming.items():
            if key in base:
                base[key] = _deep_merge(base[key], value)
            else:
                base[key] = value
        return base
    if isinstance(base, list) and isinstance(incoming, list):
        merged = list(base)
        for item in incoming:
            if item not in merged:
                merged.append(item)
        return merged
    return base


def merge_json(existing: str, incoming: str) -> str:
    try:
        base = json.loads(existing)
    except json.JSONDecodeError as exc:
        raise MergeError(f"existing file is not valid JSON: {exc}") from exc
    try:
        new = json.loads(incoming)
    except json.JSONDecodeError as exc:  # pragma: no cover - our own output
        raise MergeError(f"generated content is not valid JSON: {exc}") from exc
    if not isinstance(base, dict) or not isinstance(new, dict):
        raise MergeError("can only merge JSON objects")
    return json.dumps(_deep_merge(base, new), indent=2) + "\n"


def merge_yaml(existing: str, incoming: str) -> str:
    try:
        base = yaml.safe_load(existing)
    except yaml.YAMLError as exc:
        raise MergeError(f"existing file is not valid YAML: {exc}") from exc
    try:
        new = yaml.safe_load(incoming)
    except yaml.YAMLError as exc:  # pragma: no cover - our own output
        raise MergeError(f"generated content is not valid YAML: {exc}") from exc
    base = {} if base is None else base
    new = {} if new is None else new
    if not isinstance(base, dict) or not isinstance(new, dict):
        raise MergeError("can only merge YAML mappings")
    return yaml.dump(
        _deep_merge(base, new), default_flow_style=False, sort_keys=False, allow_unicode=True
    )


def _merge_toml_table(base: Any, incoming: Any) -> None:
    for key, value in incoming.items():
        if key not in base:
            base[key] = value
        elif isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_toml_table(base[key], value)
        # else: the user's value stands.


def merge_toml(existing: str, incoming: str) -> str:
    """Merge TOML while preserving the user's comments and formatting."""
    try:
        base = tomlkit.parse(existing)
    except Exception as exc:
        raise MergeError(f"existing file is not valid TOML: {exc}") from exc
    try:
        new = tomlkit.parse(incoming)
    except Exception as exc:  # pragma: no cover - our own output
        raise MergeError(f"generated content is not valid TOML: {exc}") from exc
    _merge_toml_table(base, new)
    return tomlkit.dumps(base)


# ---------------------------------------------------------------------------
# Managed block — for files with no structure but line semantics
# ---------------------------------------------------------------------------


def wrap_managed_block(content: str, *, prefix: str = "#") -> str:
    """
    Surround generated content with markers so it can be replaced later.

    Idempotent: content that already carries markers is returned unchanged, so
    the same helper is safe on both the first write and every merge after it.
    """
    body = content.strip("\n")
    if body.startswith(f"{prefix} {BLOCK_START}"):
        return body + "\n"
    return (
        f"{prefix} {BLOCK_START} — managed by dotmaster, edits here are overwritten\n"
        f"{body}\n"
        f"{prefix} {BLOCK_END}\n"
    )


def merge_managed_block(existing: str, incoming: str, *, prefix: str = "#") -> str:
    """
    Replace the dotmaster-managed region of *existing* with *incoming*.

    Everything the user wrote outside the markers is preserved verbatim.  When
    no markers are present the block is appended, which is also the first-run
    behaviour for a file that already existed.
    """
    block = wrap_managed_block(incoming, prefix=prefix)
    start_marker = f"{prefix} {BLOCK_START}"
    end_marker = f"{prefix} {BLOCK_END}"

    lines = existing.splitlines(keepends=True)
    start = end = None
    for i, line in enumerate(lines):
        if start is None and line.startswith(start_marker):
            start = i
        elif start is not None and line.startswith(end_marker):
            end = i
            break

    if start is not None and end is not None:
        return "".join(lines[:start]) + block + "".join(lines[end + 1 :])

    if start is not None:  # truncated/corrupted block — replace to the end
        return "".join(lines[:start]) + block

    head = existing.rstrip("\n")
    return f"{head}\n\n{block}" if head else block


def merge_line_union(existing: str, incoming: str) -> str:
    """Append any lines of *incoming* not already present in *existing*."""
    have = {line.strip() for line in existing.splitlines() if line.strip()}
    additions = [
        line
        for line in incoming.splitlines()
        if line.strip() and line.strip() not in have and not line.strip().startswith("#")
    ]
    if not additions:
        return existing
    head = existing.rstrip("\n")
    return head + "\n" + "\n".join(additions) + "\n"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def merge(
    path: PurePosixPath | str,
    existing: str,
    incoming: str,
    strategy: MergeStrategy,
) -> str:
    """
    Reconcile *incoming* generated content with the *existing* file.

    Raises :class:`MergeError` when the two cannot be combined — the engine
    turns that into a reported conflict rather than clobbering the file.
    """
    if strategy is MergeStrategy.CREATE_ONLY:
        return existing
    if strategy is MergeStrategy.OVERWRITE:
        return incoming
    if strategy is MergeStrategy.MANAGED_BLOCK:
        return merge_managed_block(existing, incoming, prefix=comment_prefix(path))
    if strategy is MergeStrategy.LINE_UNION:
        return merge_line_union(existing, incoming)

    fmt = detect_format(path)
    if fmt == "json":
        return merge_json(existing, incoming)
    if fmt == "yaml":
        return merge_yaml(existing, incoming)
    if fmt == "toml":
        return merge_toml(existing, incoming)

    # No structure to merge into: refuse rather than corrupt the file.
    raise MergeError(
        f"{path} has no mergeable structure; re-run with --force to overwrite it or edit it by hand"
    )
