"""
tests/test_config.py
Unit tests for the pydantic-based config: validation, migrations, overrides.
"""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from dotmaster.config import (
    ConfigError,
    DotmasterConfig,
    apply_overrides,
    load_config,
    save_config,
)


def make_config(**overrides) -> DotmasterConfig:
    return DotmasterConfig.model_validate(
        {
            "project": {"name": "test-app", "description": "A test", "author": "Tester"},
            "stack": {
                "languages": overrides.pop("languages", ["python"]),
                "framework": overrides.pop("framework", "fastapi"),
                "package_manager": overrides.pop("package_manager", "poetry"),
            },
            "quality": {
                "linter": overrides.pop("linter", "ruff"),
                "formatter": overrides.pop("formatter", "black"),
                "testing": overrides.pop("testing", "pytest"),
            },
            "infrastructure": {
                "docker": overrides.pop("docker", True),
                "docker_multistage": overrides.pop("docker_multistage", True),
                "ci": overrides.pop("ci", "github_actions"),
                "env_file": overrides.pop("env_file", True),
                "editorconfig": overrides.pop("editorconfig", True),
            },
        }
    )


class TestConfigRoundTrip:
    def test_to_dict_is_yaml_serializable(self):
        yaml.dump(make_config().to_dict())

    def test_from_dict_round_trip(self):
        config = make_config()
        restored = DotmasterConfig.from_dict(config.to_dict())
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

    def test_save_includes_schema_hint(self, tmp_path):
        path = save_config(make_config(), tmp_path / "dotmaster.yaml")
        assert "yaml-language-server" in path.read_text()

    def test_load_missing_raises_config_error(self, tmp_path):
        with pytest.raises(ConfigError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_load_malformed_yaml_raises_config_error_not_traceback(self, tmp_path):
        path = tmp_path / "dotmaster.yaml"
        path.write_text("project: [1,2\n")
        with pytest.raises(ConfigError, match="not valid YAML"):
            load_config(path)


class TestValidation:
    def test_unknown_top_level_key_rejected(self):
        with pytest.raises(ValidationError):
            DotmasterConfig.model_validate({"project": {"name": "x"}, "bogus_section": {}})

    def test_unknown_nested_key_rejected(self):
        with pytest.raises(ValidationError):
            DotmasterConfig.model_validate({"project": {"name": "x", "homepage": "y"}})

    def test_unknown_linter_value_rejected_with_suggestion(self):
        with pytest.raises(ValidationError) as exc_info:
            DotmasterConfig.model_validate({"quality": {"linter": "eslintt"}})
        assert "eslint" in str(exc_info.value)

    def test_null_section_does_not_crash(self):
        # pydantic coerces None -> default for an optional nested model in
        # some configs; here it must raise a clean ValidationError, never a
        # raw TypeError as it did before pydantic was introduced.
        with pytest.raises(ValidationError):
            DotmasterConfig.model_validate({"project": None})

    def test_scalar_for_section_rejected(self):
        with pytest.raises(ValidationError):
            DotmasterConfig.model_validate({"stack": "python"})

    def test_load_config_reports_friendly_error(self, tmp_path):
        path = tmp_path / "dotmaster.yaml"
        path.write_text("quality:\n  linter: eslintt\n")
        with pytest.raises(ConfigError, match="Did you mean"):
            load_config(path)


class TestMigration:
    def test_v1_generated_list_is_dropped_not_kept(self, tmp_path):
        path = tmp_path / "dotmaster.yaml"
        path.write_text(
            "version: '1'\nproject:\n  name: legacy\n"
            "generated:\n  - path: .gitignore\n    plugin: gitignore\n"
        )
        config = load_config(path, adopt_state=False)
        assert config.version == "2"
        assert config.project.name == "legacy"

    def test_v1_generated_files_are_adopted_into_state(self, tmp_path):
        (tmp_path / ".gitignore").write_text("node_modules/\n")
        path = tmp_path / "dotmaster.yaml"
        path.write_text(
            "version: '1'\nproject:\n  name: legacy\n"
            "generated:\n  - path: .gitignore\n    plugin: gitignore\n"
        )
        load_config(path)
        from dotmaster.core.state import load_state

        state = load_state(tmp_path)
        assert state.is_tracked(".gitignore")

    def test_future_version_is_refused(self, tmp_path):
        path = tmp_path / "dotmaster.yaml"
        path.write_text("version: '99'\nproject:\n  name: x\n")
        with pytest.raises(ConfigError, match="upgrade"):
            load_config(path)


class TestOverrides:
    def test_set_scalar_field(self):
        config = apply_overrides(make_config(), ["stack.framework=nextjs"])
        assert config.stack.framework == "nextjs"

    def test_set_boolean_field(self):
        config = apply_overrides(make_config(), ["infrastructure.docker=false"])
        assert config.infrastructure.docker is False

    def test_set_list_field(self):
        config = apply_overrides(make_config(), ["stack.languages=python,go"])
        assert config.stack.languages == ["python", "go"]

    def test_set_unknown_key_raises(self):
        with pytest.raises(ConfigError):
            apply_overrides(make_config(), ["stack.nonexistent=x"])

    def test_set_invalid_value_raises(self):
        with pytest.raises(ConfigError):
            apply_overrides(make_config(), ["quality.linter=not-a-real-linter"])


class TestConfigHelpers:
    def test_has_language(self):
        config = make_config(languages=["python", "javascript"])
        assert config.has_language("python")
        assert not config.has_language("go")

    def test_has_node_property(self):
        assert make_config(languages=["typescript"]).has_node
        assert not make_config(languages=["python"]).has_node

    def test_slug_normalization(self):
        config = make_config()
        config.project.name = "My Cool App!!"
        assert config.slug == "my-cool-app"

    def test_app_port_by_language(self):
        assert make_config(languages=["python"]).app_port == 8000
        assert make_config(languages=["javascript"]).app_port == 3000
