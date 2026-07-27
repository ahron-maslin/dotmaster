"""
tests/test_artifact_validity.py
Parses every file dotmaster generates, across a matrix of representative
stacks.

This is the regression test that should have existed from day one: the
original v0.2 template bugs (broken YAML indentation in CI workflows, invalid
JSON in .eslintrc) shipped because the test suite asserted substrings like
`"postgres" in content` rather than actually parsing the output. A substring
check passes on garbage; a parser does not.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import tomlkit
import yaml

from dotmaster.config import DotmasterConfig
from dotmaster.core.apply import apply_plan
from dotmaster.core.engine import build_plan
from dotmaster.plugins import registry

STACKS: dict[str, dict] = {
    "node-next-multistage-full": {
        "stack": {
            "languages": ["javascript", "typescript"],
            "framework": "nextjs",
            "package_manager": "pnpm",
        },
        "quality": {"linter": "eslint", "formatter": "prettier", "testing": "jest"},
        "infrastructure": {
            "docker": True,
            "docker_multistage": True,
            "ci": "github_actions",
            "env_file": True,
            "pre_commit": True,
        },
        "database": {
            "enabled": True,
            "engines": ["postgresql"],
            "orm": "prisma",
            "migrations": "prisma",
        },
    },
    "node-express-gitlab": {
        "stack": {"languages": ["typescript"], "framework": "express", "package_manager": "npm"},
        "quality": {"linter": "eslint", "formatter": "prettier", "testing": "vitest"},
        "infrastructure": {
            "docker": True,
            "docker_multistage": False,
            "ci": "gitlab_ci",
            "env_file": True,
        },
        "database": {"enabled": True, "engines": ["mysql"], "orm": "typeorm", "migrations": "none"},
    },
    "node-yarn-single-stage": {
        "stack": {"languages": ["javascript"], "framework": "express", "package_manager": "yarn"},
        "quality": {"testing": "jest"},
        "infrastructure": {"docker": True, "docker_multistage": False},
        "database": {},
    },
    "python-fastapi-poetry-full": {
        "stack": {"languages": ["python"], "framework": "fastapi", "package_manager": "poetry"},
        "quality": {"linter": "ruff", "formatter": "black", "testing": "pytest"},
        "infrastructure": {
            "docker": True,
            "docker_multistage": True,
            "ci": "github_actions",
            "env_file": True,
            "pre_commit": True,
        },
        "database": {
            "enabled": True,
            "engines": ["postgresql", "redis"],
            "orm": "sqlalchemy",
            "migrations": "alembic",
        },
    },
    "python-uv-gitlab": {
        "stack": {"languages": ["python"], "framework": "fastapi", "package_manager": "uv"},
        "quality": {"linter": "ruff", "formatter": "ruff", "testing": "pytest"},
        "infrastructure": {"docker": True, "docker_multistage": True, "ci": "gitlab_ci"},
        "database": {},
    },
    "python-pip-no-lockfile": {
        "stack": {"languages": ["python"], "framework": "flask", "package_manager": "pip"},
        "quality": {"linter": "ruff"},
        "infrastructure": {"docker": True, "docker_multistage": False},
        "database": {},
    },
    "python-minimal": {
        "stack": {"languages": ["python"], "framework": "none", "package_manager": "pip"},
        "quality": {},
        "infrastructure": {},
        "database": {},
    },
    "go-gin-github": {
        "stack": {"languages": ["go"], "framework": "gin", "package_manager": "go_mod"},
        "quality": {"linter": "golangci-lint", "formatter": "gofmt", "testing": "go_test"},
        "infrastructure": {"docker": True, "docker_multistage": True, "ci": "github_actions"},
        "database": {},
    },
    "mixed-python-typescript-mongo": {
        "stack": {
            "languages": ["python", "typescript"],
            "framework": "fastapi",
            "package_manager": "uv",
        },
        "quality": {"linter": "ruff", "formatter": "prettier", "testing": "pytest"},
        "infrastructure": {
            "docker": True,
            "docker_multistage": True,
            "ci": "gitlab_ci",
            "env_file": True,
        },
        "database": {
            "enabled": True,
            "engines": ["mongodb"],
            "orm": "mongoose",
            "migrations": "none",
        },
    },
}


def _parse(path: Path) -> None:
    """Parse *path* with the parser its extension/name implies, or raise."""
    name, suffix = path.name, path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix in (".yml", ".yaml"):
        yaml.safe_load(text)
    elif suffix == ".json" or name in (".eslintrc.json", ".prettierrc", ".eslintrc"):
        json.loads(text)
    elif suffix == ".toml":
        tomlkit.parse(text)
    elif suffix == ".mjs":
        _check_balanced_js(text, path)
    # Dockerfile, .env.example, .editorconfig, .gitignore, Mako templates:
    # no machine-checkable grammar beyond "we can decode it", already
    # guaranteed by read_text above.


def _check_balanced_js(text: str, path: Path) -> None:
    """A cheap syntax smoke test for generated JS: balanced brackets."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    closers = set(pairs.values())
    stack: list[str] = []
    in_string: str | None = None
    for ch in text:
        if in_string:
            if ch == in_string:
                in_string = None
            continue
        if ch in ("'", '"', "`"):
            in_string = ch
        elif ch in pairs:
            stack.append(pairs[ch])
        elif ch in closers:
            assert stack and stack.pop() == ch, f"unbalanced brackets in {path}"
    assert not stack, f"unclosed brackets in {path}: {stack}"


@pytest.mark.parametrize("stack_name", sorted(STACKS))
def test_generated_files_all_parse(stack_name):
    overrides = STACKS[stack_name]
    config = DotmasterConfig.model_validate({"project": {"name": "demo app"}, **overrides})
    root = Path(tempfile.mkdtemp())
    active = registry.active(config)
    plan = build_plan(config, root, active)
    assert not plan.errors, f"{stack_name}: plugin errors: {plan.errors}"

    result = apply_plan(plan, root, backup=False)
    written = list(result.created) + list(result.updated)
    assert written, f"{stack_name}: no files were written"

    failures: list[str] = []
    for rel in written:
        try:
            _parse(root / str(rel))
        except Exception as exc:
            failures.append(f"{rel}: {type(exc).__name__}: {exc}")
    assert not failures, f"{stack_name}:\n  " + "\n  ".join(failures)


def test_every_plugin_is_exercised_by_the_matrix():
    """Guard against a new plugin quietly having zero coverage in this file."""
    exercised: set[str] = set()
    for overrides in STACKS.values():
        config = DotmasterConfig.model_validate({"project": {"name": "x"}, **overrides})
        exercised |= {p.name for p in registry.active(config)}
    all_names = set(registry.names())
    uncovered = all_names - exercised
    assert not uncovered, f"plugins with no artifact-validity coverage: {uncovered}"
