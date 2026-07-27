"""
dotmaster/plugins/builtin/editorconfig.py
Generates .editorconfig for consistent editor behaviour across IDEs.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, MergeStrategy, Plugin


class EditorConfigPlugin(Plugin):
    name = "editorconfig"
    description = "Generates .editorconfig"
    outputs = (".editorconfig",)
    triggers = ("infrastructure.editorconfig is true",)

    def matches(self, config) -> bool:
        return config.infrastructure.editorconfig

    def plan(self, config, ctx: Context) -> list[FileAction]:
        content = ctx.render(
            "editorconfig.j2",
            languages=config.stack.languages,
            framework=config.stack.framework,
        )
        return [self.file(".editorconfig", content, strategy=MergeStrategy.OVERWRITE)]
