"""
tests/test_merge.py
Unit tests for dotmaster.core.merge — the syntax-aware reconciliation layer.
"""

from __future__ import annotations

import json

import pytest
import tomlkit
import yaml

from dotmaster.core.merge import (
    MergeError,
    detect_format,
    merge,
    merge_json,
    merge_line_union,
    merge_managed_block,
    merge_toml,
    merge_yaml,
    wrap_managed_block,
)
from dotmaster.core.plan import MergeStrategy


class TestDetectFormat:
    def test_json_by_suffix(self):
        assert detect_format("foo.json") == "json"

    def test_json_by_known_filename(self):
        assert detect_format(".eslintrc") == "json"
        assert detect_format(".prettierrc") == "json"

    def test_yaml_by_suffix(self):
        assert detect_format("a.yml") == "yaml"
        assert detect_format("a.yaml") == "yaml"

    def test_toml_by_suffix(self):
        assert detect_format("pyproject.toml") == "toml"

    def test_plain_text_has_no_format(self):
        assert detect_format("Dockerfile") is None
        assert detect_format(".npmrc") is None  # NOT json — was a bug before


class TestJSONMerge:
    def test_user_values_win(self):
        existing = '{"env": {"browser": true}}'
        incoming = '{"env": {"browser": false, "es2021": true}}'
        merged = json.loads(merge_json(existing, incoming))
        assert merged["env"]["browser"] is True  # user's value preserved
        assert merged["env"]["es2021"] is True  # new key still added

    def test_invalid_existing_raises(self):
        with pytest.raises(MergeError):
            merge_json("{not json", '{"a": 1}')

    def test_lists_are_unioned(self):
        existing = '{"ignorePatterns": ["dist/"]}'
        incoming = '{"ignorePatterns": ["dist/", "build/"]}'
        merged = json.loads(merge_json(existing, incoming))
        assert merged["ignorePatterns"] == ["dist/", "build/"]


class TestYAMLMerge:
    def test_user_values_win(self):
        existing = "services:\n  web:\n    image: node:18\n"
        incoming = "services:\n  web:\n    image: node:20\n  db:\n    image: postgres\n"
        merged = yaml.safe_load(merge_yaml(existing, incoming))
        assert merged["services"]["web"]["image"] == "node:18"
        assert merged["services"]["db"]["image"] == "postgres"


class TestTOMLMerge:
    def test_new_table_added(self):
        merged = merge_toml(
            "[tool.pytest]\nminversion = '6.0'\n", "[tool.ruff]\nline-length = 88\n"
        )
        data = tomlkit.parse(merged)
        assert data["tool"]["pytest"]["minversion"] == "6.0"
        assert data["tool"]["ruff"]["line-length"] == 88

    def test_user_values_win(self):
        merged = merge_toml('[project]\nversion = "2.1.0"\n', '[project]\nversion = "0.1.0"\n')
        data = tomlkit.parse(merged)
        assert data["project"]["version"] == "2.1.0"

    def test_preserves_comments(self):
        merged = merge_toml("# important note\n[tool.x]\na = 1\n", "[tool.y]\nb = 2\n")
        assert "# important note" in merged


class TestManagedBlock:
    def test_first_write_wraps_content(self):
        block = wrap_managed_block("node_modules/\n.env\n", prefix="#")
        assert "dotmaster:start" in block
        assert "dotmaster:end" in block
        assert "node_modules/" in block

    def test_user_content_outside_block_is_preserved(self):
        existing = wrap_managed_block("node_modules/\n", prefix="#") + "\nmy-custom-thing/\n"
        merged = merge_managed_block(existing, "node_modules/\ndist/\n", prefix="#")
        assert "my-custom-thing/" in merged
        assert "dist/" in merged

    def test_regenerating_same_content_is_idempotent(self):
        existing = wrap_managed_block("a/\nb/\n", prefix="#")
        merged = merge_managed_block(existing, "a/\nb/\n", prefix="#")
        assert merged.count("dotmaster:start") == 1

    def test_no_markers_appends(self):
        merged = merge_managed_block("old content\n", "new/\n", prefix="#")
        assert "old content" in merged
        assert "new/" in merged


class TestLineUnion:
    def test_adds_missing_lines(self):
        merged = merge_line_union("a/\nb/\n", "b/\nc/\n")
        assert merged.count("b/") == 1
        assert "c/" in merged

    def test_noop_when_nothing_new(self):
        existing = "a/\nb/\n"
        assert merge_line_union(existing, "a/\n") == existing


class TestMergeDispatch:
    def test_overwrite_strategy_ignores_existing(self):
        assert merge("x.txt", "old", "new", MergeStrategy.OVERWRITE) == "new"

    def test_create_only_keeps_existing(self):
        assert merge("x.txt", "old", "new", MergeStrategy.CREATE_ONLY) == "old"

    def test_plain_text_merge_strategy_raises(self):
        with pytest.raises(MergeError):
            merge("Dockerfile", "FROM old\n", "FROM new\n", MergeStrategy.MERGE)

    def test_json_via_merge_strategy(self):
        result = merge(".prettierrc", '{"a": 1}', '{"b": 2}', MergeStrategy.MERGE)
        assert json.loads(result) == {"a": 1, "b": 2}
