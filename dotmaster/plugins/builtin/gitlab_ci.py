"""
dotmaster/plugins/builtin/gitlab_ci.py
Generates .gitlab-ci.yml for GitLab CI/CD.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, MergeStrategy, Plugin


class GitLabCIPlugin(Plugin):
    name = "gitlab_ci"
    description = "Generates .gitlab-ci.yml"
    provides = ("ci.pipeline",)
    outputs = (".gitlab-ci.yml",)
    triggers = ("infrastructure.ci is gitlab_ci",)

    def matches(self, config) -> bool:
        return config.infrastructure.ci == "gitlab_ci"

    def plan(self, config, ctx: Context) -> list[FileAction]:
        content = ctx.render(
            "gitlab_ci.j2",
            package_manager=config.stack.package_manager,
            linter=config.quality.linter,
            formatter=config.quality.formatter,
            testing=config.quality.testing,
            docker=config.infrastructure.docker,
            has_python=config.has_python,
            has_node=config.has_node,
            has_go=config.has_go,
        )
        return [self.file(".gitlab-ci.yml", content, strategy=MergeStrategy.OVERWRITE)]
