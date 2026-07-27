"""
dotmaster/core/state.py
The generated-file ledger: ``.dotmaster/state.json``.

``dotmaster.yaml`` records *intent* — it is hand-editable and belongs in git.
This file records *facts*: which files dotmaster generated, what it wrote, and
which plugin owns them.  Keeping them apart is what makes drift detection,
safe overwrites and ``dotmaster remove`` possible, and it stops the answers
file churning on every sync.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

logger = logging.getLogger("dotmaster.state")

STATE_DIR = ".dotmaster"
STATE_FILENAME = "state.json"
STATE_SCHEMA = 1


@dataclass
class FileRecord:
    """What dotmaster last wrote to a given path."""

    plugin: str
    #: Hash of the content dotmaster wrote.  If the file on disk still hashes
    #: to this, we own it outright and may replace it freely.
    generated_sha256: str
    strategy: str
    at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    plugin_version: str = ""


@dataclass
class State:
    """The full ledger for one project."""

    schema: int = STATE_SCHEMA
    dotmaster_version: str = ""
    files: dict[str, FileRecord] = field(default_factory=dict)

    # -- queries ---------------------------------------------------------

    def record_for(self, path: PurePosixPath | str) -> FileRecord | None:
        return self.files.get(str(path))

    def owns(self, path: PurePosixPath | str, content: str) -> bool:
        """True when *content* is byte-identical to what dotmaster generated."""
        from dotmaster.core.plan import sha256

        rec = self.record_for(path)
        return rec is not None and rec.generated_sha256 == sha256(content)

    def is_tracked(self, path: PurePosixPath | str) -> bool:
        return str(path) in self.files

    def paths_for_plugin(self, plugin: str) -> list[PurePosixPath]:
        return [PurePosixPath(p) for p, r in self.files.items() if r.plugin == plugin]

    # -- mutation --------------------------------------------------------

    def record(
        self,
        path: PurePosixPath | str,
        *,
        plugin: str,
        content: str,
        strategy: str,
        plugin_version: str = "",
    ) -> None:
        from dotmaster.core.plan import sha256

        key = str(path)
        previous = self.files.get(key)
        new_hash = sha256(content)
        # Preserve the original timestamp when nothing actually changed, so a
        # no-op sync produces no diff.
        at = (
            previous.at
            if previous is not None and previous.generated_sha256 == new_hash
            else datetime.now(timezone.utc).isoformat(timespec="seconds")
        )
        self.files[key] = FileRecord(
            plugin=plugin,
            generated_sha256=new_hash,
            strategy=strategy,
            at=at,
            plugin_version=plugin_version,
        )

    def forget(self, path: PurePosixPath | str) -> None:
        self.files.pop(str(path), None)

    # -- serialization ---------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "dotmaster_version": self.dotmaster_version,
            "files": {k: asdict(v) for k, v in sorted(self.files.items())},
        }

    @classmethod
    def from_dict(cls, data: dict) -> State:
        files: dict[str, FileRecord] = {}
        for key, raw in (data.get("files") or {}).items():
            if not isinstance(raw, dict):
                continue
            try:
                files[key] = FileRecord(
                    plugin=str(raw.get("plugin", "")),
                    generated_sha256=str(raw.get("generated_sha256", "")),
                    strategy=str(raw.get("strategy", "merge")),
                    at=str(raw.get("at", "")),
                    plugin_version=str(raw.get("plugin_version", "")),
                )
            except Exception:  # pragma: no cover - defensive
                logger.debug("Ignoring malformed state entry for %s", key)
        return cls(
            schema=int(data.get("schema", STATE_SCHEMA)),
            dotmaster_version=str(data.get("dotmaster_version", "")),
            files=files,
        )


def state_path(root: Path) -> Path:
    return root / STATE_DIR / STATE_FILENAME


def load_state(root: Path) -> State:
    """Read the ledger.  A missing or corrupt file is not an error."""
    path = state_path(root)
    if not path.exists():
        return State()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s (%s); treating project as untracked.", path, exc)
        return State()
    if not isinstance(data, dict):
        return State()
    return State.from_dict(data)


def save_state(state: State, root: Path) -> Path:
    from dotmaster import __version__

    state.dotmaster_version = __version__
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_state_dir_ignored(path.parent)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def _ensure_state_dir_ignored(state_dir: Path) -> None:
    """Keep dotmaster's own working files out of the user's commits."""
    marker = state_dir / ".gitignore"
    if not marker.exists():
        marker.write_text(
            "# Created by dotmaster — internal state, do not commit.\n*\n", encoding="utf-8"
        )
