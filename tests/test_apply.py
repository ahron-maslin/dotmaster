"""
tests/test_apply.py
Unit tests for dotmaster.core.apply — writing, backing up and restoring.
"""

from __future__ import annotations

import zipfile
from pathlib import PurePosixPath

import pytest

from dotmaster.config import DotmasterConfig
from dotmaster.core.apply import apply_plan, list_backups, restore_backup
from dotmaster.core.engine import build_plan
from dotmaster.plugins.api import FileAction


def _cfg() -> DotmasterConfig:
    return DotmasterConfig(
        project={"name": "app"},
        stack={"languages": ["python"], "framework": "fastapi", "package_manager": "poetry"},
        quality={"linter": "ruff"},
        infrastructure={"docker": True},
    )


class TestApplyPlan:
    def test_creates_files(self, tmp_path):
        registry_plugins = __import__("dotmaster.plugins", fromlist=["registry"]).registry
        plan = build_plan(_cfg(), tmp_path, registry_plugins.active(_cfg()))
        result = apply_plan(plan, tmp_path)
        assert result.written > 0
        assert (tmp_path / "Dockerfile").exists()

    def test_second_apply_is_noop(self, tmp_path):
        from dotmaster.plugins import registry

        cfg = _cfg()
        active = registry.active(cfg)
        apply_plan(build_plan(cfg, tmp_path, active), tmp_path)
        result2 = apply_plan(build_plan(cfg, tmp_path, active), tmp_path)
        assert result2.written == 0

    def test_conflicting_file_is_not_written(self, tmp_path):
        from dotmaster.plugins import registry

        cfg = _cfg()
        active = registry.active(cfg)
        apply_plan(build_plan(cfg, tmp_path, active), tmp_path)
        (tmp_path / "Dockerfile").write_text("FROM scratch\n# user edit\n")

        plan = build_plan(cfg, tmp_path, active)
        result = apply_plan(plan, tmp_path)
        assert any(str(p) == "Dockerfile" for p in [c.path for c in result.blocked])
        assert (tmp_path / "Dockerfile").read_text() == "FROM scratch\n# user edit\n"

    def test_force_overwrites_conflicts(self, tmp_path):
        from dotmaster.plugins import registry

        cfg = _cfg()
        active = registry.active(cfg)
        apply_plan(build_plan(cfg, tmp_path, active), tmp_path)
        (tmp_path / "Dockerfile").write_text("FROM scratch\n")

        plan = build_plan(cfg, tmp_path, active, force=True)
        result = apply_plan(plan, tmp_path)
        assert any(str(p) == "Dockerfile" for p in result.updated)
        assert "FROM scratch" not in (tmp_path / "Dockerfile").read_text()

    def test_backup_created_before_overwrite(self, tmp_path):
        from dotmaster.plugins import registry

        cfg = _cfg()
        active = registry.active(cfg)
        apply_plan(build_plan(cfg, tmp_path, active), tmp_path)
        (tmp_path / "Dockerfile").write_text("FROM scratch\n")
        result = apply_plan(build_plan(cfg, tmp_path, active, force=True), tmp_path)
        assert result.backup is not None
        with zipfile.ZipFile(result.backup) as zf:
            assert "Dockerfile" in zf.namelist()

    def test_no_backup_when_nothing_existed(self, tmp_path):
        from dotmaster.plugins import registry

        cfg = _cfg()
        result = apply_plan(build_plan(cfg, tmp_path, registry.active(cfg)), tmp_path)
        assert result.backup is None

    def test_atomic_write_uses_no_leftover_tmp_files(self, tmp_path):
        from dotmaster.plugins import registry

        cfg = _cfg()
        apply_plan(build_plan(cfg, tmp_path, registry.active(cfg)), tmp_path)
        leftovers = list(tmp_path.rglob("*.dotmaster.tmp"))
        assert leftovers == []


class TestBackupRestore:
    def test_restore_round_trips_content(self, tmp_path):
        from dotmaster.plugins import registry

        cfg = _cfg()
        active = registry.active(cfg)
        apply_plan(build_plan(cfg, tmp_path, active), tmp_path)
        original = (tmp_path / "Dockerfile").read_text()

        (tmp_path / "Dockerfile").write_text("mutated\n")
        apply_plan(build_plan(cfg, tmp_path, active, force=True), tmp_path)
        # force regenerates from the (unchanged) config, so it lands back on
        # the original generated content rather than staying "mutated".
        assert (tmp_path / "Dockerfile").read_text() == original

        backups = list_backups(tmp_path)
        assert backups
        restore_backup(backups[-1], tmp_path)
        assert (tmp_path / "Dockerfile").read_text() == "mutated\n"

    def test_restore_refuses_path_traversal(self, tmp_path):
        outside = tmp_path.parent / "outside_secret.txt"
        archive = tmp_path / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../outside_secret.txt", "pwned")

        project = tmp_path / "proj"
        project.mkdir()
        restore_backup(archive, project)
        assert not outside.exists()


class TestFileActionSafety:
    def test_rejects_parent_traversal(self):
        with pytest.raises(ValueError):
            FileAction(path=PurePosixPath("../evil.txt"), content="x", plugin="p")

    def test_rejects_absolute_path(self):
        with pytest.raises(ValueError):
            FileAction(path=PurePosixPath("/etc/passwd"), content="x", plugin="p")
