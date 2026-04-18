"""
tests/test_merger.py
Unit tests for the syntax-aware file merger.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import tomlkit
import yaml

from dotmaster.merger import merge_content, merge_json, merge_toml, merge_yaml, merge_text


class TestJSONMerger:
    def test_merge_json_basic(self):
        old = '{"env": {"browser": true}}'
        new = '{"env": {"es2021": true}, "rules": {"semi": "error"}}'
        merged = merge_json(old, new)
        data = json.loads(merged)
        
        # Original values should persist
        assert data["env"]["browser"] is True
        # New values should be added
        assert data["env"]["es2021"] is True
        assert data["rules"]["semi"] == "error"

    def test_merge_json_invalid_old(self):
        old = '{invalid_json...'
        new = '{"valid": true}'
        merged = merge_json(old, new)
        assert json.loads(merged) == {"valid": True}


class TestYAMLMerger:
    def test_merge_yaml_basic(self):
        old = "services:\n  web:\n    image: node\n"
        new = "services:\n  db:\n    image: postgres\n"
        merged = merge_yaml(old, new)
        data = yaml.safe_load(merged)
        
        assert data["services"]["web"]["image"] == "node"
        assert data["services"]["db"]["image"] == "postgres"


class TestTOMLMerger:
    def test_merge_toml_basic(self):
        old = "[tool.pytest]\nminversion = '6.0'\n"
        new = "[tool.ruff]\nline-length = 88\n"
        merged = merge_toml(old, new)
        
        assert "[tool.pytest]" in merged
        assert "[tool.ruff]" in merged
        assert "minversion" in merged
        assert "line-length = 88" in merged

    def test_merge_toml_nested(self):
        old = "[project.scripts]\nstart = 'node index.js'\n"
        new = "[project.scripts]\nbuild = 'tsc'\n"
        merged = merge_toml(old, new)
        data = tomlkit.parse(merged)
        
        assert data["project"]["scripts"]["start"] == "node index.js"
        assert data["project"]["scripts"]["build"] == "tsc"


class TestTextMerger:
    def test_merge_text_appends_smartly(self):
        old = "node_modules/\n.env\n"
        new = ".pytest_cache/\n"
        merged = merge_text(old, new)
        
        assert "node_modules/" in merged
        assert "-- managed by dotmaster --" in merged
        assert ".pytest_cache/" in merged

    def test_merge_text_idempotent(self):
        old = "node_modules/\n\n# -- managed by dotmaster --\n.pytest_cache/\n"
        new = ".pytest_cache/\n"
        # It shouldn't append it again if it's identical to new content
        # Note: merge_text uses `new_content.strip() in existing_content`
        merged = merge_text(old, new)
        assert merged.count(".pytest_cache") == 1


class TestMergeContentDispatch:
    def test_merge_content_creates_if_not_exists(self, tmp_path):
        f = tmp_path / "new.json"
        res = merge_content(f, '{"hello": "world"}')
        assert '{"hello": "world"}' in res

    def test_merge_content_dispatches_rc_files_as_json(self, tmp_path):
        f = tmp_path / ".eslintrc"
        f.write_text('{"env": {"browser": true}}')
        res = merge_content(f, '{"parser": "typescript"}')
        data = json.loads(res)
        assert data["env"]["browser"] is True
        assert data["parser"] == "typescript"
