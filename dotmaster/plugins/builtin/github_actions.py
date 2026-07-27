"""
dotmaster/plugins/builtin/github_actions.py
Generates .github/workflows/ci.yml for GitHub Actions.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, MergeStrategy, Plugin


class GitHubActionsPlugin(Plugin):
    name = "github_actions"
    description = "Generates .github/workflows/ci.yml"
    provides = ("ci.pipeline",)
    outputs = (".github/workflows/ci.yml",)
    triggers = ("infrastructure.ci is github_actions",)

    def matches(self, config) -> bool:
        return config.infrastructure.ci == "github_actions"

    def plan(self, config, ctx: Context) -> list[FileAction]:
        content = ctx.render(
            "github_ci.j2",
            project_name=config.project.name,
            package_manager=config.stack.package_manager,
            framework=config.stack.framework,
            linter=config.quality.linter,
            formatter=config.quality.formatter,
            testing=config.quality.testing,
            docker=config.infrastructure.docker,
            has_python=config.has_python,
            has_node=config.has_node,
            has_go=config.has_go,
            has_package_json_scripts=ctx.exists("package.json"),
        )
        return [self.file(".github/workflows/ci.yml", content, strategy=MergeStrategy.OVERWRITE)]
