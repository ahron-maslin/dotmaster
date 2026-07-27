"""
dotmaster/renderer.py
Template rendering.

Rendering returns a string and never touches the filesystem — writing is the
sole responsibility of :mod:`dotmaster.core.apply`.

The environment is *sandboxed*.  Built-in templates are trusted, but plugins
and (soon) user-supplied template packs are not, and an unsandboxed Jinja
environment is a remote-code-execution primitive.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import ChoiceLoader, FileSystemLoader, StrictUndefined, TemplateNotFound
from jinja2.sandbox import SandboxedEnvironment

TEMPLATES_DIR = Path(__file__).parent / "templates"

#: Extra template roots contributed by plugins, searched after the built-ins.
_extra_roots: list[Path] = []


def register_template_dir(path: Path) -> None:
    """Let a plugin ship its own templates."""
    resolved = Path(path).resolve()
    if resolved not in _extra_roots:
        _extra_roots.append(resolved)
        _build_env.cache_clear()


def _to_json(value: Any, indent: int = 2) -> str:
    """Render a Python structure as JSON — the safe way to emit JSON configs."""
    return json.dumps(value, indent=indent, ensure_ascii=False)


@lru_cache(maxsize=1)
def _build_env() -> SandboxedEnvironment:
    env = SandboxedEnvironment(
        loader=ChoiceLoader(
            [FileSystemLoader(str(TEMPLATES_DIR))]
            + [FileSystemLoader(str(p)) for p in _extra_roots]
        ),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
        autoescape=False,  # config files, never HTML
    )
    env.filters["to_json"] = _to_json
    return env


class TemplateError(Exception):
    """A template could not be found or rendered."""


def render(template_name: str, context: dict[str, Any] | None = None, **kwargs: Any) -> str:
    """Render *template_name* and return the result."""
    merged = {**(context or {}), **kwargs}
    try:
        template = _build_env().get_template(template_name)
    except TemplateNotFound as exc:
        raise TemplateError(f"template not found: {template_name}") from exc
    return template.render(**merged)


def available_templates() -> list[str]:
    return sorted(_build_env().list_templates())
