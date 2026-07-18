"""
tests/test_cli.py
Integration tests for the `dotmaster` CLI commands.
"""
from __future__ import annotations

from typer.testing import CliRunner

from dotmaster.cli import app
from dotmaster.config import DotmasterConfig, load_config, save_config

runner = CliRunner()


class TestProfileApply:
    def test_apply_merges_infrastructure_settings(self, tmp_path):
        """
        Regression test: `profile --apply` used to compute the profile's
        infrastructure settings (docker, ci, env_file, ...) but never merge
        them into the config, so applying a profile silently dropped that
        section entirely.
        """
        save_config(DotmasterConfig(), tmp_path / "dotmaster.yaml")

        result = runner.invoke(
            app, ["profile", "backend_api", "--apply", "--output", str(tmp_path)]
        )
        assert result.exit_code == 0, result.output

        loaded = load_config(tmp_path / "dotmaster.yaml")
        assert loaded.infrastructure.docker is True
        assert loaded.infrastructure.docker_multistage is True
        assert loaded.infrastructure.ci == "github_actions"
        assert loaded.infrastructure.env_file is True

    def test_apply_does_not_override_existing_ci(self, tmp_path):
        """Existing explicit settings should win over the profile's defaults."""
        config = DotmasterConfig()
        config.infrastructure.ci = "gitlab_ci"
        save_config(config, tmp_path / "dotmaster.yaml")

        result = runner.invoke(
            app, ["profile", "backend_api", "--apply", "--output", str(tmp_path)]
        )
        assert result.exit_code == 0, result.output

        loaded = load_config(tmp_path / "dotmaster.yaml")
        assert loaded.infrastructure.ci == "gitlab_ci"

    def test_apply_unknown_profile_exits_nonzero(self, tmp_path):
        result = runner.invoke(app, ["profile", "not-a-real-profile"])
        assert result.exit_code == 1
