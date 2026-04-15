"""
dotmaster/plugins/builtin/docker.py
Generates Dockerfile and .dockerignore.
"""
from __future__ import annotations

from pathlib import Path

from dotmaster.plugins.base import BasePlugin
from dotmaster.renderer import render_to_file


class DockerPlugin(BasePlugin):
    name = "docker"
    description = "Generates Dockerfile and .dockerignore"
    triggers = ["docker:true"]

    def generate(self, config, output_dir: Path) -> list[Path]:
        ctx = {
            "project_name": config.project.name,
            "languages": config.stack.languages,
            "framework": config.stack.framework,
            "package_manager": config.stack.package_manager,
            "multistage": config.infrastructure.docker_multistage,
            "has_python": "python" in config.stack.languages,
            "has_node": any(
                l in config.stack.languages
                for l in ("javascript", "typescript")
            ),
            "has_go": "go" in config.stack.languages,
        }
        dockerfile = render_to_file(
            "dockerfile.j2", ctx, output_dir / "Dockerfile"
        )
        dockerignore = render_to_file(
            "dockerignore.j2", ctx, output_dir / ".dockerignore"
        )
        return [dockerfile, dockerignore]
