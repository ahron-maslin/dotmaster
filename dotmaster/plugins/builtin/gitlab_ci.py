"""
dotmaster/plugins/builtin/gitlab_ci.py
Generates .gitlab-ci.yml for GitLab CI/CD.
"""
from __future__ import annotations

from pathlib import Path

from dotmaster.plugins.base import BasePlugin
from dotmaster.renderer import render_to_file


class GitLabCIPlugin(BasePlugin):
    name = "gitlab_ci"
    description = "Generates .gitlab-ci.yml"
    triggers = ["ci:gitlab_ci"]

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
        out = render_to_file(
            "gitlab_ci.j2", ctx, output_dir / ".gitlab-ci.yml"
        )
        return [out]
