"""
dotmaster/plugins/builtin/gitignore.py
Generates .gitignore.

Offline by default.  gitignore.io produces excellent output, but fetching it
sends a fingerprint of the user's stack to a third party and lets that third
party decide the contents of the file that keeps secrets out of the repo. That
is opt-in (``options.offline: false``), never the default, and the bundled
template is always a complete fallback.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, Plugin

GITIGNORE_IO = "https://www.toptal.com/developers/gitignore/api/"

_LANG_TERMS: dict[str, str] = {
    "javascript": "node",
    "typescript": "node",
    "python": "python",
    "go": "go",
    "rust": "rust",
    "java": "java",
}

_FRAMEWORK_TERMS: dict[str, str] = {
    "react": "react",
    "nextjs": "nextjs",
    "vue": "vue",
    "angular": "angular",
    "django": "django",
    "flask": "flask",
}

_COMMON_TERMS = ["macos", "linux", "windows", "visualstudiocode", "jetbrains"]


class GitignorePlugin(Plugin):
    name = "gitignore"
    description = "Generates .gitignore"
    provides = ("vcs.ignore",)
    outputs = (".gitignore",)
    triggers = ("always",)

    def matches(self, config) -> bool:
        return True

    def plan(self, config, ctx: Context) -> list[FileAction]:
        content = None if ctx.offline else self._from_api(config, ctx)
        if content is None:
            content = ctx.render(
                "gitignore.j2",
                languages=config.stack.languages,
                framework=config.stack.framework,
                package_manager=config.stack.package_manager,
            )
        return [
            self.block_file(
                ".gitignore", content, description="ignore rules for the selected stack"
            )
        ]

    def _from_api(self, config, ctx: Context) -> str | None:
        terms: list[str] = []
        for lang in config.stack.languages:
            term = _LANG_TERMS.get(lang)
            if term and term not in terms:
                terms.append(term)
        framework_term = _FRAMEWORK_TERMS.get(config.stack.framework)
        if framework_term and framework_term not in terms:
            terms.append(framework_term)
        terms.extend(t for t in _COMMON_TERMS if t not in terms)

        body = ctx.fetch(GITIGNORE_IO + ",".join(terms))
        if body is None:
            return None
        # Sanity-check the payload before trusting it with a security-relevant
        # file: a truncated or hijacked response must not silently unignore
        # things like .env.
        if "#" not in body or len(body.splitlines()) < 10:
            ctx.log.warning("gitignore.io response looked wrong; using the bundled template.")
            return None
        extras = "\n".join(
            line for line in (".env", ".dotmaster/", ".dotmaster.log") if line not in body
        )
        return f"{body.rstrip()}\n\n# ── dotmaster ──\n{extras}\n" if extras else body
