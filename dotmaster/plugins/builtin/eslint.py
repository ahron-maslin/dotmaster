"""
dotmaster/plugins/builtin/eslint.py
Generates ESLint configuration.

Emits flat config (``eslint.config.mjs``), the format ESLint 9 defaults to.
``.eslintrc.json`` and ``.eslintignore`` are legacy — ESLint 9 dropped
``.eslintignore`` entirely — so legacy output is opt-in via
``plugins.settings.eslint.legacy: true``.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, MergeStrategy, Plugin


class ESLintPlugin(Plugin):
    name = "eslint"
    description = "Generates ESLint flat config (eslint.config.mjs)"
    provides = ("lint.javascript",)
    outputs = ("eslint.config.mjs", ".eslintrc.json", ".eslintignore")
    triggers = ("linter is eslint",)

    def matches(self, config) -> bool:
        return config.quality.linter == "eslint"

    def plan(self, config, ctx: Context) -> list[FileAction]:
        if ctx.settings(self.name).get("legacy"):
            return self._legacy(config, ctx)
        content = ctx.render(
            "eslint_flat_config.j2",
            has_typescript=config.has_typescript,
            has_react=config.has_react,
            testing=config.quality.testing,
            uses_prettier=config.quality.formatter == "prettier",
        )
        return [
            self.file(
                "eslint.config.mjs",
                content,
                strategy=MergeStrategy.OVERWRITE,
                description="flat config for ESLint 9+",
            )
        ]

    # -- legacy (.eslintrc.json) ----------------------------------------

    def _legacy(self, config, ctx: Context) -> list[FileAction]:
        """
        Build the legacy config as a Python dict.

        Hand-assembling JSON in a template is how this file used to end up
        with missing and trailing commas; serialising a dict makes invalid
        output impossible.
        """
        plugins: list[str] = []
        extends: list[str] = ["eslint:recommended"]
        rules: dict[str, object] = {
            "no-console": "warn",
            "no-unused-vars": "warn",
            "prefer-const": "error",
            "eqeqeq": ["error", "always"],
        }
        settings: dict[str, object] = {}

        if config.has_typescript:
            plugins.append("@typescript-eslint")
            extends.append("plugin:@typescript-eslint/recommended")
            rules.update(
                {
                    "no-unused-vars": "off",
                    "@typescript-eslint/no-unused-vars": ["warn", {"argsIgnorePattern": "^_"}],
                    "@typescript-eslint/explicit-module-boundary-types": "off",
                    "@typescript-eslint/no-explicit-any": "warn",
                }
            )
        if config.has_react:
            plugins.extend(["react", "react-hooks"])
            extends.extend(["plugin:react/recommended", "plugin:react-hooks/recommended"])
            rules.update({"react/prop-types": "off", "react/react-in-jsx-scope": "off"})
            settings["react"] = {"version": "detect"}
        if config.quality.testing == "jest":
            plugins.append("jest")
            extends.append("plugin:jest/recommended")

        data: dict[str, object] = {
            "root": True,
            "env": {"browser": config.has_react, "node": True, "es2022": True},
            "parser": "@typescript-eslint/parser" if config.has_typescript else "espree",
            "parserOptions": {
                "ecmaVersion": "latest",
                "sourceType": "module",
                **({"ecmaFeatures": {"jsx": True}} if config.has_react else {}),
            },
            "plugins": plugins,
            "extends": extends,
            **({"settings": settings} if settings else {}),
            "rules": rules,
            "ignorePatterns": ["dist/", "build/", ".next/", "node_modules/", "coverage/"],
        }
        return [
            self.json_file(".eslintrc.json", data, description="legacy ESLint config"),
            self.block_file(
                ".eslintignore",
                "node_modules/\ndist/\nbuild/\nout/\n.next/\ncoverage/\n",
            ),
        ]
