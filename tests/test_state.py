"""
tests/test_state.py
Unit tests for dotmaster.core.state — the generated-file ledger.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from dotmaster.core.state import State, load_state, save_state


class TestState:
    def test_owns_matches_identical_content(self):
        state = State()
        state.record("a.txt", plugin="p", content="hello\n", strategy="overwrite")
        assert state.owns("a.txt", "hello\n")
        assert not state.owns("a.txt", "different\n")

    def test_record_preserves_timestamp_when_unchanged(self):
        state = State()
        state.record("a.txt", plugin="p", content="hello\n", strategy="overwrite")
        first_at = state.record_for("a.txt").at
        state.record("a.txt", plugin="p", content="hello\n", strategy="overwrite")
        assert state.record_for("a.txt").at == first_at

    def test_record_updates_timestamp_when_changed(self):
        state = State()
        with patch("dotmaster.core.state.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1, tzinfo=timezone.utc)
            state.record("a.txt", plugin="p", content="hello\n", strategy="overwrite")
            first_at = state.record_for("a.txt").at

            mock_dt.now.return_value = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
                hours=1
            )
            state.record("a.txt", plugin="p", content="changed\n", strategy="overwrite")
        assert state.record_for("a.txt").at != first_at

    def test_forget_removes_entry(self):
        state = State()
        state.record("a.txt", plugin="p", content="x", strategy="overwrite")
        state.forget("a.txt")
        assert not state.is_tracked("a.txt")

    def test_paths_for_plugin(self):
        state = State()
        state.record("a.txt", plugin="p1", content="x", strategy="overwrite")
        state.record("b.txt", plugin="p2", content="y", strategy="overwrite")
        assert [str(p) for p in state.paths_for_plugin("p1")] == ["a.txt"]


class TestStateIO:
    def test_save_and_load_round_trip(self, tmp_path):
        state = State()
        state.record("a.txt", plugin="p", content="hello\n", strategy="overwrite")
        save_state(state, tmp_path)
        loaded = load_state(tmp_path)
        assert loaded.owns("a.txt", "hello\n")

    def test_missing_state_file_is_empty_not_an_error(self, tmp_path):
        state = load_state(tmp_path)
        assert state.files == {}

    def test_corrupt_state_file_is_empty_not_an_error(self, tmp_path):
        state_dir = tmp_path / ".dotmaster"
        state_dir.mkdir()
        (state_dir / "state.json").write_text("{not valid json")
        state = load_state(tmp_path)
        assert state.files == {}

    def test_state_dir_gets_its_own_gitignore(self, tmp_path):
        save_state(State(), tmp_path)
        content = (tmp_path / ".dotmaster" / ".gitignore").read_text(encoding="utf-8")
        assert content.strip() == "# Created by dotmaster — internal state, do not commit.\n*"
