"""
tests/test_config.py
Unit tests for the config module (serialization round-trips, helpers).
"""
from __future__ import annotations

import pytest
import yaml

from dotmaster.config import (
    DotmasterConfig,
    InfraConfig,
    ProjectConfig,
    QualityConfig,
    StackConfig,
    load_config,
    save_config,
)


def make_config(**overrides) -> DotmasterConfig:
    """Build a minimal valid config for tests."""
    return DotmasterConfig(
        project=ProjectConfig(name="test-app", description="A test", author="Tester"),
        stack=StackConfig(
            languages=overrides.pop("languages", ["python"]),
            framework=overrides.pop("framework", "fastapi"),
            package_manager=overrides.pop("package_manager", "poetry"),
        ),
        quality=QualityConfig(
            linter=overrides.pop("linter", "ruff"),
            formatter=overrides.pop("formatter", "black"),
            testing=overrides.pop("testing", "pytest"),
        ),
        infrastructure=InfraConfig(
            docker=overrides.pop("docker", True),
            docker_multistage=overrides.pop("docker_multistage", True),
            ci=overrides.pop("ci", "github_actions"),
            env_file=overrides.pop("env_file", True),
            editorconfig=overrides.pop("editorconfig", True),
        ),
    )


class TestConfigRoundTrip:
    def test_to_dict_is_serializable(self):
        config = make_config()
        d = config.to_dict()
        # Must be YAML-serializable without error
        yaml.dump(d)

    def test_from_dict_round_trip(self):
        config = make_config()
        d = config.to_dict()
        restored = DotmasterConfig.from_dict(d)

        assert restored.project.name == config.project.name
        assert restored.stack.languages == config.stack.languages
        assert restored.quality.linter == config.quality.linter
        assert restored.infrastructure.docker == config.infrastructure.docker

    def test_save_and_load(self, tmp_path):
        config = make_config()
        path = tmp_path / "dotmaster.yaml"
        save_config(config, path)
        assert path.exists()

        loaded = load_config(path)
        assert loaded.project.name == config.project.name
        assert loaded.stack.framework == config.stack.framework

    def test_load_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")


class TestConfigHelpers:
    def test_has_language(self):
        config = make_config(languages=["python", "javascript"])
        assert config.has_language("python")
        assert config.has_language("javascript")
        assert not config.has_language("go")

    def test_has_any_language(self):
        config = make_config(languages=["python"])
        assert config.has_any_language("python", "go")
        assert not config.has_any_language("javascript", "go")

    def test_record_generated(self, tmp_path):
        config = make_config()
        p = tmp_path / ".gitignore"
        config.record_generated(p, "gitignore")
        assert len(config.generated) == 1
        assert config.generated[0].plugin == "gitignore"

        # Re-recording the same path should replace, not duplicate
        config.record_generated(p, "gitignore")
        assert len(config.generated) == 1
