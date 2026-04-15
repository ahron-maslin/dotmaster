"""
dotmaster/plugins/builtin/eslint.py
Generates ESLint configuration via template.

We use template-based generation (not `eslint --init` delegation) for
predictability and to avoid interactive prompts breaking the wizard flow.
"""
from __future__ import annotations

from pathlib import Path

from dotmaster.plugins.base import BasePlugin
from dotmaster.renderer import render_to_file


class ESLintPlugin(BasePlugin):
    name = "eslint"
    description = "Generates .eslintrc.json and .eslintignore"
    triggers = ["linter:eslint"]

    def generate(self, config, output_dir: Path) -> list[Path]:
        ctx = {
            "framework": config.stack.framework,
            "has_typescript": "typescript" in config.stack.languages,
            "has_react": config.stack.framework in ("react", "nextjs"),
            "testing": config.quality.testing,
            "package_manager": config.stack.package_manager,
        }
        eslintrc = render_to_file(
            "eslintrc.j2", ctx, output_dir / ".eslintrc.json"
        )
        eslintignore = render_to_file(
            "eslintignore.j2", ctx, output_dir / ".eslintignore"
        )
        return [eslintrc, eslintignore]
