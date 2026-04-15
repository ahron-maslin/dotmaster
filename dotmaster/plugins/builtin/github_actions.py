"""
dotmaster/plugins/builtin/github_actions.py
Generates .github/workflows/ci.yml for GitHub Actions.
"""
from __future__ import annotations

from pathlib import Path

from dotmaster.plugins.base import BasePlugin
from dotmaster.renderer import render_to_file


class GitHubActionsPlugin(BasePlugin):
    name = "github_actions"
    description = "Generates .github/workflows/ci.yml"
    triggers = ["ci:github_actions"]

    def generate(self, config, output_dir: Path) -> list[Path]:
        ctx = {
            "project_name": config.project.name,
            "languages": config.stack.languages,
            "framework": config.stack.framework,
            "package_manager": config.stack.package_manager,
            "linter": config.quality.linter,
            "formatter": config.quality.formatter,
            "testing": config.quality.testing,
            "docker": config.infrastructure.docker,
            "has_python": "python" in config.stack.languages,
            "has_node": any(
                l in config.stack.languages
                for l in ("javascript", "typescript")
            ),
            "has_go": "go" in config.stack.languages,
        }
        workflows_dir = output_dir / ".github" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        out = render_to_file(
            "github_ci.j2", ctx, workflows_dir / "ci.yml"
        )
        return [out]
