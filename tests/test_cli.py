"""
tests/test_cli.py
Integration tests for the `dotmaster` CLI commands, via Typer's CliRunner.
"""

from __future__ import annotations

from typer.testing import CliRunner

from dotmaster.cli import app
from dotmaster.config import DotmasterConfig, load_config, save_config

runner = CliRunner()


def _make(tmp_path, **overrides) -> None:
    config = DotmasterConfig.model_validate(
        {
            "project": {"name": "app"},
            "stack": {"languages": ["python"], "framework": "fastapi", "package_manager": "poetry"},
            "quality": {"linter": "ruff"},
            **overrides,
        }
    )
    save_config(config, tmp_path / "dotmaster.yaml")


class TestInitNonInteractive:
    def test_yes_flag_never_blocks(self, tmp_path):
        result = runner.invoke(
            app, ["init", "--output", str(tmp_path), "--preset", "backend_api", "--yes"]
        )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "dotmaster.yaml").exists()
        assert (tmp_path / "Dockerfile").exists()

    def test_set_overrides_apply(self, tmp_path):
        result = runner.invoke(
            app,
            [
                "init",
                "--output",
                str(tmp_path),
                "--preset",
                "backend_api",
                "--yes",
                "--set",
                "infrastructure.docker=false",
            ],
        )
        assert result.exit_code == 0, result.output
        loaded = load_config(tmp_path / "dotmaster.yaml")
        assert loaded.infrastructure.docker is False
        assert not (tmp_path / "Dockerfile").exists()

    def test_dry_run_writes_nothing(self, tmp_path):
        result = runner.invoke(
            app,
            ["init", "--output", str(tmp_path), "--preset", "backend_api", "--yes", "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        assert not (tmp_path / "Dockerfile").exists()
        assert not (tmp_path / "dotmaster.yaml").exists()


class TestSync:
    def test_sync_is_idempotent(self, tmp_path):
        _make(tmp_path, infrastructure={"docker": True})
        first = runner.invoke(app, ["sync", "--output", str(tmp_path)])
        assert first.exit_code == 0, first.output
        second = runner.invoke(app, ["sync", "--output", str(tmp_path)])
        assert second.exit_code == 0
        assert "Already up to date" in second.output

    def test_sync_missing_config_exits_nonzero(self, tmp_path):
        result = runner.invoke(app, ["sync", "--output", str(tmp_path)])
        assert result.exit_code == 1

    def test_sync_only_runs_named_plugins(self, tmp_path):
        _make(tmp_path, infrastructure={"docker": True})
        result = runner.invoke(app, ["sync", "--output", str(tmp_path), "--only", "docker"])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "Dockerfile").exists()
        assert not (tmp_path / "pyproject.toml").exists()


class TestAddRemove:
    def test_add_unknown_plugin_suggests_a_match(self, tmp_path):
        _make(tmp_path)
        result = runner.invoke(app, ["add", "eslnt", "--output", str(tmp_path)])
        assert result.exit_code == 1
        assert "eslint" in result.output

    def test_remove_deletes_owned_files(self, tmp_path):
        _make(tmp_path, infrastructure={"docker": True})
        runner.invoke(app, ["sync", "--output", str(tmp_path)])
        assert (tmp_path / "Dockerfile").exists()
        result = runner.invoke(app, ["remove", "docker", "--output", str(tmp_path), "--yes"])
        assert result.exit_code == 0, result.output
        assert not (tmp_path / "Dockerfile").exists()

    def test_remove_keeps_user_modified_files(self, tmp_path):
        _make(tmp_path, infrastructure={"docker": True})
        runner.invoke(app, ["sync", "--output", str(tmp_path)])
        (tmp_path / "Dockerfile").write_text("# hand edited\n")
        result = runner.invoke(app, ["remove", "docker", "--output", str(tmp_path), "--yes"])
        assert result.exit_code == 0
        assert (tmp_path / "Dockerfile").exists()


class TestDiffCheck:
    def test_check_passes_on_clean_project(self, tmp_path):
        _make(tmp_path)
        runner.invoke(app, ["sync", "--output", str(tmp_path)])
        result = runner.invoke(app, ["check", "--output", str(tmp_path)])
        assert result.exit_code == 0

    def test_check_fails_on_drift(self, tmp_path):
        _make(tmp_path)
        runner.invoke(app, ["sync", "--output", str(tmp_path)])
        save_config(
            DotmasterConfig.model_validate(
                {
                    "project": {"name": "app"},
                    "stack": {"languages": ["python"]},
                    "infrastructure": {"docker": True},
                }
            ),
            tmp_path / "dotmaster.yaml",
        )
        result = runner.invoke(app, ["check", "--output", str(tmp_path)])
        assert result.exit_code == 1

    def test_diff_reports_conflicts_without_writing(self, tmp_path):
        _make(tmp_path, infrastructure={"docker": True})
        runner.invoke(app, ["sync", "--output", str(tmp_path)])
        (tmp_path / "Dockerfile").write_text("mutated\n")
        result = runner.invoke(app, ["diff", "--output", str(tmp_path)])
        assert result.exit_code == 0
        assert "Dockerfile" in result.output
        assert (tmp_path / "Dockerfile").read_text() == "mutated\n"


class TestProfile:
    def test_apply_fills_unset_infrastructure_settings(self, tmp_path):
        """
        Regression: `profile apply` used to compute infrastructure settings
        but never merge them, so applying a profile silently dropped that
        whole section.
        """
        save_config(DotmasterConfig(), tmp_path / "dotmaster.yaml")
        result = runner.invoke(app, ["profile", "apply", "backend_api", "--output", str(tmp_path)])
        assert result.exit_code == 0, result.output
        loaded = load_config(tmp_path / "dotmaster.yaml")
        assert loaded.infrastructure.docker is True
        assert loaded.infrastructure.docker_multistage is True
        assert loaded.infrastructure.ci == "github_actions"
        assert loaded.infrastructure.env_file is True

    def test_apply_does_not_override_existing_setting(self, tmp_path):
        config = DotmasterConfig()
        config.infrastructure.ci = "gitlab_ci"
        save_config(config, tmp_path / "dotmaster.yaml")
        result = runner.invoke(app, ["profile", "apply", "backend_api", "--output", str(tmp_path)])
        assert result.exit_code == 0, result.output
        loaded = load_config(tmp_path / "dotmaster.yaml")
        assert loaded.infrastructure.ci == "gitlab_ci"

    def test_apply_unknown_profile_exits_nonzero(self, tmp_path):
        save_config(DotmasterConfig(), tmp_path / "dotmaster.yaml")
        result = runner.invoke(
            app, ["profile", "apply", "not-a-real-profile", "--output", str(tmp_path)]
        )
        assert result.exit_code == 1

    def test_list_and_show(self):
        assert runner.invoke(app, ["profile", "list"]).exit_code == 0
        assert runner.invoke(app, ["profile", "show", "web_app"]).exit_code == 0
        assert runner.invoke(app, ["profile", "show", "nonexistent"]).exit_code == 1


class TestValidate:
    def test_valid_config_passes(self, tmp_path):
        _make(tmp_path)
        result = runner.invoke(app, ["validate", "--output", str(tmp_path)])
        assert result.exit_code == 0

    def test_cross_field_inconsistency_fails(self, tmp_path):
        save_config(
            DotmasterConfig.model_validate(
                {
                    "project": {"name": "x"},
                    "stack": {"languages": ["python"]},
                    "quality": {"linter": "eslint"},
                }
            ),
            tmp_path / "dotmaster.yaml",
        )
        result = runner.invoke(app, ["validate", "--output", str(tmp_path)])
        assert result.exit_code == 1
        assert "eslint" in result.output

    def test_malformed_yaml_reports_cleanly_not_a_traceback(self, tmp_path):
        (tmp_path / "dotmaster.yaml").write_text("project: [1,2\n")
        result = runner.invoke(app, ["validate", "--output", str(tmp_path)])
        assert result.exit_code == 1
        assert "Traceback" not in result.output


class TestVersionAndLogging:
    def test_version_creates_no_log_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert not (tmp_path / ".dotmaster.log").exists()


class TestDoctor:
    def test_runs_without_a_config(self, tmp_path):
        result = runner.invoke(app, ["doctor", "--output", str(tmp_path)])
        assert result.exit_code == 0
        assert "no dotmaster.yaml" in result.output

    def test_runs_with_a_config(self, tmp_path):
        _make(tmp_path)
        result = runner.invoke(app, ["doctor", "--output", str(tmp_path)])
        assert result.exit_code == 0
        assert "valid" in result.output
