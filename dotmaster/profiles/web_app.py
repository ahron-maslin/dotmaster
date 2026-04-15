"""Web App preset profile — full-stack application defaults."""

WEB_APP_PROFILE: dict = {
    "stack": {
        "languages": ["javascript", "typescript"],
        "framework": "nextjs",
        "package_manager": "npm",
    },
    "quality": {
        "linter": "eslint",
        "formatter": "prettier",
        "testing": "jest",
    },
    "infrastructure": {
        "docker": True,
        "docker_multistage": True,
        "ci": "github_actions",
        "env_file": True,
        "editorconfig": True,
    },
}
