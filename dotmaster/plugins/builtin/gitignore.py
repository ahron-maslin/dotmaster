"""
dotmaster/plugins/builtin/gitignore.py
Generates .gitignore via gitignore.io API (delegates) or a built-in template.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

from dotmaster.plugins.base import BasePlugin
from dotmaster.renderer import render_to_file

# Maps our language keys → gitignore.io API terms
_LANG_MAP: dict[str, str] = {
    "javascript": "node",
    "typescript": "node",
    "python": "python",
    "go": "go",
    "rust": "rust",
    "java": "java",
}

# Maps framework keys → gitignore.io API terms
_FW_MAP: dict[str, str] = {
    "react": "react",
    "nextjs": "nextjs",
    "vue": "vue",
    "angular": "angular",
    "django": "django",
    "flask": "flask",
}

# Always append these for a comprehensive ignore file
_COMMON_TERMS = ["macos", "linux", "windows", "visualstudiocode", "jetbrains"]


class GitignorePlugin(BasePlugin):
    name = "gitignore"
    description = "Generates .gitignore via gitignore.io or a built-in template"
    triggers = []  # always active — overriding should_run below

    def should_run(self, config) -> bool:
        return True  # gitignore is always needed

    def delegate(self, config, output_dir: Path) -> bool:
        """Fetch from gitignore.io API and write directly."""
        terms: list[str] = []
        for lang in config.stack.languages:
            term = _LANG_MAP.get(lang)
            if term and term not in terms:
                terms.append(term)
        fw_term = _FW_MAP.get(config.stack.framework)
        if fw_term:
            terms.append(fw_term)
        terms.extend(_COMMON_TERMS)

        url = (
            "https://www.toptal.com/developers/gitignore/api/"
            + ",".join(terms)
        )
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "dotmaster/0.1"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                content = resp.read().decode("utf-8")
            out = output_dir / ".gitignore"
            out.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False  # fall back to template

    def generate(self, config, output_dir: Path) -> list[Path]:
        ctx = {
            "languages": config.stack.languages,
            "framework": config.stack.framework,
            "package_manager": config.stack.package_manager,
        }
        out = render_to_file("gitignore.j2", ctx, output_dir / ".gitignore")
        return [out]
