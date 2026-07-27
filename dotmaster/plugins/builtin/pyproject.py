"""
dotmaster/plugins/builtin/pyproject.py
Generates pyproject.toml for Python projects.

Ruff configuration lives only in ``ruff.toml`` when the ruff plugin is also
active (see RuffPlugin) — Ruff resolves ``ruff.toml`` first, so duplicating
``[tool.ruff]`` here would be dead configuration that silently drifts.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, MergeStrategy, Plugin


class PyprojectPlugin(Plugin):
    name = "pyproject"
    description = "Generates pyproject.toml for Python projects"
    provides = ("packaging.python",)
    outputs = ("pyproject.toml",)
    triggers = ("language includes python",)

    def matches(self, config) -> bool:
        return config.has_python

    def plan(self, config, ctx: Context) -> list[FileAction]:
        content = ctx.render(
            "pyproject_toml.j2",
            project_name=config.project.name,
            slug=config.slug,
            description=config.project.description,
            author=config.project.author,
            license=config.project.license,
            package_manager=config.stack.package_manager,
            framework=config.stack.framework,
            use_black=config.quality.formatter == "black",
            use_pytest=config.quality.testing == "pytest",
        )
        return [self.file("pyproject.toml", content, strategy=MergeStrategy.MERGE)]
