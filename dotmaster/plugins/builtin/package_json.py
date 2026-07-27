"""
dotmaster/plugins/builtin/package_json.py
Ensures package.json has the lint/format/test scripts the generated CI calls.

Without this, generated CI workflows invoke `npm run lint` / `format:check`
against a package.json that has no such scripts, and the very first push fails
with "Missing script". This plugin only ever adds scripts — it never touches
dependencies or other fields, and never creates package.json from scratch
(that's the package manager's job, not dotmaster's).
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, MergeStrategy, Plugin


class PackageJsonPlugin(Plugin):
    name = "package_json"
    description = "Adds lint/format/test scripts to an existing package.json"
    provides = ("scripts.javascript",)
    outputs = ("package.json",)
    triggers = ("node project with lint, format, or test tooling",)

    def matches(self, config) -> bool:
        return config.has_node and (
            config.quality.linter in ("eslint", "biome")
            or config.quality.formatter in ("prettier", "biome")
            or config.quality.testing in ("jest", "vitest")
        )

    def plan(self, config, ctx: Context) -> list[FileAction]:
        existing = ctx.read("package.json")
        if existing is None:
            # Not our job to scaffold package.json; the package manager does
            # that (npm init, pnpm init, ...).
            return []

        scripts: dict[str, str] = {}
        if config.quality.linter == "eslint":
            scripts["lint"] = "eslint ."
        elif config.quality.linter == "biome":
            scripts["lint"] = "biome lint ."
        if config.quality.formatter == "prettier":
            scripts["format"] = "prettier --write ."
            scripts["format:check"] = "prettier --check ."
        elif config.quality.formatter == "biome":
            scripts["format"] = "biome format --write ."
            scripts["format:check"] = "biome format ."
        if config.quality.testing in ("jest", "vitest"):
            scripts["test"] = config.quality.testing

        if not scripts:
            return []

        return [
            self.json_file(
                "package.json",
                {"scripts": scripts},
                strategy=MergeStrategy.MERGE,
                description="adds npm scripts your CI workflow calls (existing scripts win)",
            )
        ]
