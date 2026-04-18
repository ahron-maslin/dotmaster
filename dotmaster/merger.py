"""
dotmaster/merger.py
Smart merging logic for JSON, YAML, TOML, and plaintext files.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
import tomlkit

logger = logging.getLogger("dotmaster.merger")


def merge_json(existing_content: str, new_content: str) -> str:
    """Recursively merge two JSON objects."""
    try:
        existing = json.loads(existing_content)
        new = json.loads(new_content)
    except json.JSONDecodeError as exc:
        logger.warning(f"Failed to parse JSON for merging: {exc}. Overwriting.")
        return new_content

    if not isinstance(existing, dict) or not isinstance(new, dict):
        return new_content

    merged = _deep_merge(existing, new)
    return json.dumps(merged, indent=2) + "\n"


def merge_yaml(existing_content: str, new_content: str) -> str:
    """Recursively merge two YAML documents."""
    try:
        existing = yaml.safe_load(existing_content) or {}
        new = yaml.safe_load(new_content) or {}
    except yaml.YAMLError as exc:
        logger.warning(f"Failed to parse YAML for merging: {exc}. Overwriting.")
        return new_content

    if not isinstance(existing, dict) or not isinstance(new, dict):
        return new_content

    merged = _deep_merge(existing, new)
    return yaml.dump(merged, default_flow_style=False, sort_keys=False)


def _merge_toml_table(existing_table: Any, new_table: Any) -> None:
    for key, value in new_table.items():
        if key not in existing_table:
            existing_table[key] = value
        elif isinstance(value, dict) and isinstance(existing_table.get(key), dict):
            _merge_toml_table(existing_table[key], value)
        else:
            existing_table[key] = value

def merge_toml(existing_content: str, new_content: str) -> str:
    """Smart merge TOML documents preserving comments and style via tomlkit."""
    try:
        existing = tomlkit.parse(existing_content)
        new = tomlkit.parse(new_content)
    except Exception as exc:
        logger.warning(f"Failed to parse TOML for merging: {exc}. Overwriting.")
        return new_content

    _merge_toml_table(existing, new)

    return tomlkit.dumps(existing)


def merge_text(existing_content: str, new_content: str) -> str:
    """Append managed text to an existing file if not already present."""
    managed_header = "\n# -- managed by dotmaster --\n"
    if new_content.strip() in existing_content:
        return existing_content
        
    return existing_content.rstrip() + managed_header + new_content


def _deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge `update` into `base`."""
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        elif isinstance(value, list) and isinstance(base.get(key), list):
            # Merge lists uniquely
            merged_list = list(base[key])
            for item in value:
                if item not in merged_list:
                    merged_list.append(item)
            base[key] = merged_list
        else:
            base[key] = value
    return base


def merge_content(file_path: Path, new_content: str) -> str:
    """
    Load existing content from *file_path* and merge *new_content* into it
    based on the file extension.
    """
    if not file_path.exists():
        return new_content

    existing_content = file_path.read_text(encoding="utf-8")
    ext = file_path.suffix.lower()

    if ext == ".json" or file_path.name.endswith("rc"):  # e.g. .eslintrc
        # heuristics for json without extension
        if new_content.strip().startswith("{"):
            return merge_json(existing_content, new_content)

    if ext in (".yml", ".yaml"):
        return merge_yaml(existing_content, new_content)

    if ext == ".toml":
        return merge_toml(existing_content, new_content)

    return merge_text(existing_content, new_content)
