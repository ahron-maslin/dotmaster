"""
dotmaster/plugins/builtin/prettier.py
Generates .prettierrc and .prettierignore.
"""

from __future__ import annotations

from dotmaster.plugins.api import Context, FileAction, Plugin


class PrettierPlugin(Plugin):
    name = "prettier"
    description = "Generates .prettierrc and .prettierignore"
    provides = ("format.javascript",)
    outputs = (".prettierrc", ".prettierignore")
    triggers = ("formatter is prettier",)

    def matches(self, config) -> bool:
        return config.quality.formatter == "prettier"

    def plan(self, config, ctx: Context) -> list[FileAction]:
        # No top-level "parser" key: Prettier already selects the right
        # parser from the file extension, and forcing "typescript" here used
        # to break formatting for every non-TS file Prettier touched.
        data = {
            "semi": True,
            "singleQuote": False,
            "tabWidth": 2,
            "useTabs": False,
            "trailingComma": "all",
            "printWidth": 100,
            "bracketSpacing": True,
            "arrowParens": "always",
            "endOfLine": "lf",
        }
        return [
            self.json_file(".prettierrc", data),
            self.block_file(
                ".prettierignore",
                "node_modules/\ndist/\nbuild/\nout/\n.next/\ncoverage/\n"
                "*.min.js\n*.min.css\npackage-lock.json\nyarn.lock\npnpm-lock.yaml\n",
            ),
        ]
