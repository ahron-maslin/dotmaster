"""
tests/test_renderer.py
Unit tests for the Jinja2 template renderer.
"""
from __future__ import annotations

import pytest

from dotmaster.renderer import render, render_to_file


class TestRender:
    def test_render_gitignore(self):
        content = render(
            "gitignore.j2",
            {"languages": ["python"], "framework": "none", "package_manager": "pip"},
        )
        assert ".DS_Store" in content
        assert "__pycache__" in content   # Python section rendered

    def test_render_gitignore_node(self):
        content = render(
            "gitignore.j2",
            {
                "languages": ["javascript", "typescript"],
                "framework": "nextjs",
                "package_manager": "npm",
            },
        )
        assert "node_modules" in content
        assert ".next/" in content

    def test_render_editorconfig_python(self):
        content = render(
            "editorconfig.j2",
            {"languages": ["python"], "framework": "fastapi"},
        )
        assert "root = true" in content
        assert "indent_size = 4" in content   # Python override

    def test_render_to_file_creates_file(self, tmp_path):
        out = render_to_file(
            "editorconfig.j2",
            {"languages": ["go"], "framework": "none"},
            tmp_path / ".editorconfig",
        )
        assert out.exists()
        assert "root = true" in out.read_text()

    def test_render_to_file_skips_existing_when_no_overwrite(self, tmp_path):
        path = tmp_path / ".editorconfig"
        path.write_text("original content")
        render_to_file(
            "editorconfig.j2",
            {"languages": ["python"], "framework": "none"},
            path,
            overwrite=False,
            merge=False,
        )
        assert path.read_text() == "original content"

    def test_render_env_example(self):
        content = render(
            "env_example.j2",
            {
                "project_name": "my-api",
                "framework": "fastapi",
                "has_python": True,
                "has_node": False,
                "db_engines": ["postgresql", "redis"],
            },
        )
        assert "APP_NAME" in content
        assert "DATABASE_URL" in content

    def test_render_ruff_toml(self):
        content = render(
            "ruff_toml.j2",
            {
                "project_name": "my-lib",
                "use_as_formatter": True,
                "testing": "pytest",
            },
        )
        assert "target-version" in content
        assert "[format]" in content
