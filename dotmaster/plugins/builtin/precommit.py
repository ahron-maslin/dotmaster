"""
dotmaster/plugins/builtin/precommit.py
Generates .pre-commit-config.yaml from the same linter/formatter answers
already collected — the natural counterpart to the CI plugins, and one of the
highest-value/lowest-effort additions in the plugin catalogue.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, MergeStrategy, Plugin


class PreCommitPlugin(Plugin):
    name = "pre_commit"
    description = "Generates .pre-commit-config.yaml for the selected linters/formatters"
    provides = ("hooks.pre_commit",)
    outputs = (".pre-commit-config.yaml",)
    triggers = ("infrastructure.pre_commit is true",)

    def matches(self, config) -> bool:
        return config.infrastructure.pre_commit

    def plan(self, config, ctx: Context) -> list[FileAction]:
        content = ctx.render(
            "precommit_config.j2",
            linter=config.quality.linter,
            formatter=config.quality.formatter,
            has_python=config.has_python,
            has_node=config.has_node,
        )
        return [self.file(".pre-commit-config.yaml", content, strategy=MergeStrategy.MERGE)]
