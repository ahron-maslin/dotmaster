"""
tests/test_renderer.py
Unit tests for the (I/O-free, sandboxed) Jinja2 renderer.
"""

from __future__ import annotations

import pytest

from dotmaster.renderer import TemplateError, render


class TestRender:
    def test_render_gitignore_python(self):
        content = render(
            "gitignore.j2", {"languages": ["python"], "framework": "none", "package_manager": "pip"}
        )
        assert ".DS_Store" in content
        assert "__pycache__" in content

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
        content = render("editorconfig.j2", {"languages": ["python"], "framework": "fastapi"})
        assert "root = true" in content
        assert "indent_size = 4" in content

    def test_render_env_example(self):
        content = render(
            "env_example.j2",
            {
                "project_name": "my-api",
                "slug": "my-api",
                "framework": "fastapi",
                "has_python": True,
                "has_node": False,
                "db_engines": ["postgresql", "redis"],
            },
        )
        assert "APP_NAME" in content
        assert "DATABASE_URL" in content

    def test_render_ruff_toml(self):
        content = render("ruff_toml.j2", {"slug": "my_lib", "use_as_formatter": True})
        assert "target-version" in content
        assert "[format]" in content

    def test_unknown_template_raises_template_error(self):
        with pytest.raises(TemplateError):
            render("does_not_exist.j2", {})

    def test_missing_variable_raises(self):
        from jinja2 import UndefinedError

        # StrictUndefined: a template referencing an undefined variable must
        # fail loudly rather than silently render an empty string.
        with pytest.raises(UndefinedError):
            render("editorconfig.j2", {})

    def test_kwargs_form(self):
        content = render("editorconfig.j2", languages=["go"], framework="none")
        assert "indent_style = tab" in content
