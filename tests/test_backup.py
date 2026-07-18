"""
tests/test_backup.py
Unit tests for the pre-generation backup mechanism.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from dotmaster.backup import backup_managed_files
from dotmaster.config import DotmasterConfig


class TestBackupManagedFiles:
    def test_no_generated_entries_skips_backup(self, tmp_path):
        config = DotmasterConfig()
        assert backup_managed_files(config, tmp_path) is None

    def test_missing_files_on_disk_skips_backup(self, tmp_path):
        config = DotmasterConfig()
        config.record_generated(tmp_path / ".gitignore", "gitignore")
        assert backup_managed_files(config, tmp_path) is None

    def test_backs_up_existing_managed_files(self, tmp_path):
        config = DotmasterConfig()
        (tmp_path / ".gitignore").write_text("node_modules/\n")
        config.record_generated(Path(".gitignore"), "gitignore")

        archive = backup_managed_files(config, tmp_path)

        assert archive is not None
        assert archive.exists()
        assert archive.suffix == ".zip"
        with zipfile.ZipFile(archive) as zf:
            assert ".gitignore" in zf.namelist()
            assert zf.read(".gitignore").decode() == "node_modules/\n"

    def test_staging_directory_is_cleaned_up(self, tmp_path):
        config = DotmasterConfig()
        (tmp_path / ".gitignore").write_text("node_modules/\n")
        config.record_generated(Path(".gitignore"), "gitignore")

        backup_managed_files(config, tmp_path)

        staging_dirs = list((tmp_path / ".dotmaster" / "backups").glob("staged_*"))
        assert staging_dirs == []

    def test_nested_paths_preserve_directory_structure(self, tmp_path):
        config = DotmasterConfig()
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("name: CI\n")
        config.record_generated(
            (workflows / "ci.yml").relative_to(tmp_path), "github_actions"
        )

        archive = backup_managed_files(config, tmp_path)

        with zipfile.ZipFile(archive) as zf:
            assert ".github/workflows/ci.yml" in zf.namelist()
