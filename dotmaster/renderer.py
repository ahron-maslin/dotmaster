"""
dotmaster/renderer.py
Jinja2 template rendering engine.

Templates live in dotmaster/templates/ and receive the full config dict plus
any extra context kwargs passed by individual plugins.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

# Templates directory co-located with the package
TEMPLATES_DIR = Path(__file__).parent / "templates"


def _make_env() -> Environment:
    """Create a preconfigured Jinja2 Environment."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )


def render(template_name: str, context: dict[str, Any]) -> str:
    """Render *template_name* with *context* and return the result string."""
    env = _make_env()
    template = env.get_template(template_name)
    return template.render(**context)


def render_to_file(
    template_name: str,
    context: dict[str, Any],
    output_path: Path,
    *,
    overwrite: bool = False,
    merge: bool = True,
) -> Path:
    """
    Render *template_name* and write the output to *output_path*.

    Parameters
    ----------
    template_name : str
        Filename relative to the ``templates/`` directory.
    context : dict
        Template variables.
    output_path : Path
        Destination file path.
    overwrite : bool
        If True, always overwrite the existing file completely. Note that `merge` is ignored if `overwrite` is True.
    merge : bool
        If True and *output_path* already exists, smartly merge the new content into the existing file.

    Returns
    -------
    Path
        The (possibly unchanged) output path.
    """
    from dotmaster.merger import merge_content

    if output_path.exists() and not overwrite and not merge:
        return output_path
        
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = render(template_name, context)

    if output_path.exists() and merge and not overwrite:
        content = merge_content(output_path, content)

    output_path.write_text(content, encoding="utf-8")
    return output_path
