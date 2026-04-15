"""Backend API preset profile — Python service defaults."""

BACKEND_API_PROFILE: dict = {
    "stack": {
        "languages": ["python"],
        "framework": "fastapi",
        "package_manager": "poetry",
    },
    "quality": {
        "linter": "ruff",
        "formatter": "black",
        "testing": "pytest",
    },
    "infrastructure": {
        "docker": True,
        "docker_multistage": True,
        "ci": "github_actions",
        "env_file": True,
        "editorconfig": True,
    },
}
