"""Library preset profile — reusable package / SDK defaults."""

LIBRARY_PROFILE: dict = {
    "stack": {
        "languages": ["javascript", "typescript"],
        "framework": "none",
        "package_manager": "npm",
    },
    "quality": {
        "linter": "eslint",
        "formatter": "prettier",
        "testing": "jest",
    },
    "infrastructure": {
        "docker": False,
        "docker_multistage": False,
        "ci": "github_actions",
        "env_file": False,
        "editorconfig": True,
    },
}
