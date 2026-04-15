"""Monorepo preset profile — multi-package workspace defaults."""

MONOREPO_PROFILE: dict = {
    "stack": {
        "languages": ["javascript", "typescript"],
        "framework": "none",
        "package_manager": "pnpm",
    },
    "quality": {
        "linter": "eslint",
        "formatter": "prettier",
        "testing": "jest",
    },
    "infrastructure": {
        "docker": True,
        "docker_multistage": False,
        "ci": "github_actions",
        "env_file": True,
        "editorconfig": True,
    },
}
