"""
tests/test_engine.py
Unit tests for dotmaster.core.engine — turning plugins + config into a Plan.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from dotmaster.config import DotmasterConfig
from dotmaster.core.engine import build_plan, safe_target
from dotmaster.core.plan import ChangeKind, FileAction, MergeStrategy
from dotmaster.plugins.api import Plugin


class _StaticPlugin(Plugin):
    def __init__(self, name, actions):
        self.name = name
        self.description = "test"
        self._actions = actions

    def matches(self, config):
        return True

    def plan(self, config, ctx):
        return self._actions


def _cfg() -> DotmasterConfig:
    return DotmasterConfig.model_validate({"project": {"name": "x"}})


class TestBuildPlan:
    def test_new_file_is_a_create(self, tmp_path):
        action = FileAction(
            path=PurePosixPath("a.txt"),
            content="hi\n",
            plugin="p",
            strategy=MergeStrategy.OVERWRITE,
        )
        plan = build_plan(_cfg(), tmp_path, [_StaticPlugin("p", [action])])
        assert plan.changes[0].kind == ChangeKind.CREATE

    def test_existing_untouched_file_is_regenerated(self, tmp_path):
        (tmp_path / "a.txt").write_text("old\n")
        action = FileAction(
            path=PurePosixPath("a.txt"),
            content="new\n",
            plugin="p",
            strategy=MergeStrategy.OVERWRITE,
        )
        plan = build_plan(_cfg(), tmp_path, [_StaticPlugin("p", [action])])
        # Not owned by the state ledger and not force -> conflict, not silent overwrite.
        assert plan.changes[0].kind == ChangeKind.CONFLICT

    def test_owned_file_regenerates_without_conflict(self, tmp_path):
        from dotmaster.core.apply import apply_plan

        action = FileAction(
            path=PurePosixPath("a.txt"),
            content="v1\n",
            plugin="p",
            strategy=MergeStrategy.OVERWRITE,
        )
        plan1 = build_plan(_cfg(), tmp_path, [_StaticPlugin("p", [action])])
        apply_plan(plan1, tmp_path)

        action2 = FileAction(
            path=PurePosixPath("a.txt"),
            content="v2\n",
            plugin="p",
            strategy=MergeStrategy.OVERWRITE,
        )
        plan2 = build_plan(_cfg(), tmp_path, [_StaticPlugin("p", [action2])])
        assert plan2.changes[0].kind == ChangeKind.UPDATE

    def test_two_plugins_same_path_is_a_conflict(self, tmp_path):
        a1 = FileAction(path=PurePosixPath("shared.txt"), content="a\n", plugin="p1")
        a2 = FileAction(path=PurePosixPath("shared.txt"), content="b\n", plugin="p2")
        plan = build_plan(_cfg(), tmp_path, [_StaticPlugin("p1", [a1]), _StaticPlugin("p2", [a2])])
        assert len(plan.conflicts) == 1
        assert plan.conflicts[0].subject == "shared.txt"

    def test_capability_conflict_detected(self, tmp_path):
        class P1(_StaticPlugin):
            provides = ("lint.python",)

        class P2(_StaticPlugin):
            provides = ("lint.python",)

        plan = build_plan(_cfg(), tmp_path, [P1("p1", []), P2("p2", [])])
        assert any(c.subject == "lint.python" for c in plan.conflicts)

    def test_plugin_exception_is_isolated(self, tmp_path):
        class Bad(_StaticPlugin):
            def plan(self, config, ctx):
                raise RuntimeError("boom")

        good_action = FileAction(path=PurePosixPath("ok.txt"), content="fine\n", plugin="good")
        plan = build_plan(_cfg(), tmp_path, [Bad("bad", []), _StaticPlugin("good", [good_action])])
        assert "bad" in plan.errors
        assert any(c.path == PurePosixPath("ok.txt") for c in plan.changes)

    def test_create_only_skips_existing_file(self, tmp_path):
        (tmp_path / "once.txt").write_text("existing\n")
        action = FileAction(
            path=PurePosixPath("once.txt"),
            content="new\n",
            plugin="p",
            strategy=MergeStrategy.CREATE_ONLY,
        )
        plan = build_plan(_cfg(), tmp_path, [_StaticPlugin("p", [action])])
        assert plan.changes[0].kind == ChangeKind.SKIP

    def test_directory_at_target_path_is_a_conflict(self, tmp_path):
        (tmp_path / "a_dir").mkdir()
        action = FileAction(path=PurePosixPath("a_dir"), content="x\n", plugin="p")
        plan = build_plan(_cfg(), tmp_path, [_StaticPlugin("p", [action])])
        assert plan.changes[0].kind == ChangeKind.CONFLICT


class TestSafeTarget:
    def test_normal_path_resolves_inside_root(self, tmp_path):
        assert safe_target(tmp_path, "Dockerfile") is not None

    def test_parent_traversal_is_refused(self, tmp_path):
        assert safe_target(tmp_path, "../secret.txt") is None

    def test_nested_traversal_is_refused(self, tmp_path):
        assert safe_target(tmp_path, "a/b/../../../secret.txt") is None
