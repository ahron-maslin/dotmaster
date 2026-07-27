"""
tests/test_wizard.py
Wizard tests via ScriptedPrompter — no terminal needed.

This module used to be 0% covered because it drove InquirerPy directly.
Routing every question through the Prompter protocol (dotmaster.prompts)
makes it a pure function of its answers, so it's testable like anything else.
"""

from __future__ import annotations

import pytest

from dotmaster.prompts import DefaultPrompter, ScriptedPrompter
from dotmaster.wizard import WizardAborted, run_wizard


def _answers_custom_python():
    """Answers for: no preset, Python + FastAPI + Poetry + ruff/black/pytest,
    no database, Docker with multistage, GitHub Actions, env file, editorconfig,
    no pre-commit, confirm generate."""
    return ScriptedPrompter(
        [
            False,  # start from preset? no
            "myapp",  # project name
            "a test app",  # description
            "me",  # author
            ["python"],  # languages
            "fastapi",  # framework
            "poetry",  # package manager
            "ruff",  # linter
            "black",  # formatter
            "pytest",  # testing
            False,  # database?
            True,  # docker?
            True,  # multistage?
            "github_actions",  # ci
            True,  # env file
            True,  # editorconfig
            False,  # pre-commit
            True,  # confirm generate
        ]
    )


class TestWizardScripted:
    def test_produces_expected_config(self, tmp_path):
        config = run_wizard(_answers_custom_python(), output_dir=tmp_path, show_banner=False)
        assert config.project.name == "myapp"
        assert config.stack.languages == ["python"]
        assert config.stack.framework == "fastapi"
        assert config.quality.linter == "ruff"
        assert config.infrastructure.docker is True
        assert config.infrastructure.docker_multistage is True
        assert config.database.enabled is False

    def test_declining_the_summary_aborts(self, tmp_path):
        answers = ScriptedPrompter(
            [
                False,
                "myapp",
                "",
                "",
                ["python"],
                "fastapi",
                "poetry",
                "ruff",
                "black",
                "pytest",
                False,
                False,
                "none",
                False,
                True,
                False,
                False,  # decline the final confirmation
            ]
        )
        with pytest.raises(WizardAborted):
            run_wizard(answers, output_dir=tmp_path, show_banner=False)

    def test_preset_prefills_and_preselects_languages(self, tmp_path):
        """
        Regression: profile defaults used to only move the checkbox cursor,
        never actually pre-check anything, so `--preset web_app` produced an
        empty language selection. With DefaultPrompter, every checkbox
        resolves to its preselected values with no interaction at all.
        """
        config = run_wizard(
            DefaultPrompter(), preset_profile="web_app", output_dir=tmp_path, show_banner=False
        )
        assert set(config.stack.languages) == {"javascript", "typescript"}
        assert config.stack.framework == "nextjs"
        assert config.quality.linter == "eslint"
        assert config.infrastructure.docker is True
        assert config.profile == "web_app"

    def test_unknown_preset_falls_back_to_blank(self, tmp_path):
        config = run_wizard(
            DefaultPrompter(),
            preset_profile="not-a-real-profile",
            output_dir=tmp_path,
            show_banner=False,
        )
        assert config.profile == "none"


class TestDefaultPrompterNeverBlocks:
    def test_every_question_resolves_without_input(self, tmp_path):
        # DefaultPrompter must complete the entire wizard with zero scripted
        # answers — this is what makes `dotmaster init --yes` and CI usage work.
        config = run_wizard(DefaultPrompter(), output_dir=tmp_path, show_banner=False)
        assert config.project.name  # falls back to the directory name
        assert config.stack.languages  # `required=True` checkbox still yields something
