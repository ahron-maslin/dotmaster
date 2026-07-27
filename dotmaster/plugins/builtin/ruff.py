"""
dotmaster/plugins/builtin/ruff.py
Generates ruff.toml for Python projects using the Ruff linter/formatter.

This is the single owner of Ruff configuration: PyprojectPlugin skips
``[tool.ruff]`` whenever this plugin is also active, so the two never emit
competing configs for the same tool.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, MergeStrategy, Plugin


class RuffPlugin(Plugin):
    name = "ruff"
    description = "Generates ruff.toml configuration"
    provides = ("lint.python", "format.python")
    outputs = ("ruff.toml",)
    triggers = ("linter or formatter is ruff",)

    def matches(self, config) -> bool:
        return config.quality.linter == "ruff" or config.quality.formatter == "ruff"

    def plan(self, config, ctx: Context) -> list[FileAction]:
        content = ctx.render(
            "ruff_toml.j2",
            slug=config.snake_slug,
            use_as_formatter=config.quality.formatter == "ruff",
        )
        return [self.file("ruff.toml", content, strategy=MergeStrategy.MERGE)]
