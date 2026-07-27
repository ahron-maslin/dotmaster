"""
dotmaster/plugins/builtin/docker.py
Generates Dockerfile and .dockerignore.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, MergeStrategy, Plugin


class DockerPlugin(Plugin):
    name = "docker"
    description = "Generates Dockerfile and .dockerignore"
    provides = ("container.dockerfile",)
    outputs = ("Dockerfile", ".dockerignore")
    triggers = ("infrastructure.docker is true",)

    def matches(self, config) -> bool:
        return config.infrastructure.docker

    def plan(self, config, ctx: Context) -> list[FileAction]:
        content = ctx.render(
            "dockerfile.j2",
            project_name=config.project.name,
            languages=config.stack.languages,
            framework=config.stack.framework,
            package_manager=config.stack.package_manager,
            multistage=config.infrastructure.docker_multistage,
            has_python=config.has_python,
            has_node=config.has_node,
            has_go=config.has_go,
            has_poetry_lock=ctx.exists("poetry.lock"),
            has_uv_lock=ctx.exists("uv.lock"),
            has_requirements=ctx.exists("requirements.txt"),
            standalone_next=ctx.exists("next.config.js") or ctx.exists("next.config.mjs"),
        )
        ignore = ctx.render(
            "dockerignore.j2",
            has_python=config.has_python,
            has_node=config.has_node,
            has_go=config.has_go,
        )
        return [
            self.file("Dockerfile", content, strategy=MergeStrategy.OVERWRITE),
            self.block_file(".dockerignore", ignore),
        ]
