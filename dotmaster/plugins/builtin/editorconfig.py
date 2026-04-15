"""
dotmaster/plugins/builtin/editorconfig.py
Generates .editorconfig for consistent editor behaviour across IDEs.
"""
from __future__ import annotations

from pathlib import Path

from dotmaster.plugins.base import BasePlugin
from dotmaster.renderer import render_to_file


class EditorConfigPlugin(BasePlugin):
    name = "editorconfig"
    description = "Generates .editorconfig"
    triggers = ["editorconfig:true"]

    def generate(self, config, output_dir: Path) -> list[Path]:
        ctx = {
            "languages": config.stack.languages,
            "framework": config.stack.framework,
        }
        out = render_to_file(
            "editorconfig.j2", ctx, output_dir / ".editorconfig"
        )
        return [out]
