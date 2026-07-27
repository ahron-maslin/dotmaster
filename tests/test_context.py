"""
tests/test_context.py
Unit tests for dotmaster.plugins.api.Context — the sandboxed capability
surface plugins use instead of importing urllib/subprocess directly.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dotmaster.config import DotmasterConfig
from dotmaster.plugins.api import Context


def _cfg() -> DotmasterConfig:
    return DotmasterConfig.model_validate(
        {"project": {"name": "x"}, "plugins": {"settings": {"myplugin": {"a": 1}}}}
    )


class TestContextFilesystem:
    def test_read_existing_file(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello\n")
        ctx = Context(root=tmp_path, config=_cfg())
        assert ctx.read("a.txt") == "hello\n"

    def test_read_missing_file_returns_none(self, tmp_path):
        ctx = Context(root=tmp_path, config=_cfg())
        assert ctx.read("missing.txt") is None

    def test_exists(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        ctx = Context(root=tmp_path, config=_cfg())
        assert ctx.exists("a.txt")
        assert not ctx.exists("b.txt")

    def test_settings_scoped_per_plugin(self, tmp_path):
        ctx = Context(root=tmp_path, config=_cfg())
        assert ctx.settings("myplugin") == {"a": 1}
        assert ctx.settings("other") == {}


class TestContextFetch:
    def test_offline_returns_none_without_network_call(self, tmp_path):
        ctx = Context(root=tmp_path, config=_cfg(), offline=True)
        with patch("urllib.request.urlopen") as mock_open:
            result = ctx.fetch("https://example.com/x")
        mock_open.assert_not_called()
        assert result is None

    def test_refuses_non_https(self, tmp_path):
        ctx = Context(root=tmp_path, config=_cfg(), offline=False)
        assert ctx.fetch("http://example.com/x") is None

    def test_returns_text_response(self, tmp_path):
        ctx = Context(root=tmp_path, config=_cfg(), offline=False)
        response = MagicMock()
        response.headers.get_content_type.return_value = "text/plain"
        response.read.return_value = b"hello world"
        response.__enter__ = lambda self: response
        response.__exit__ = lambda *a: False
        with patch("urllib.request.urlopen", return_value=response):
            assert ctx.fetch("https://example.com/x") == "hello world"

    def test_rejects_non_text_content_type(self, tmp_path):
        ctx = Context(root=tmp_path, config=_cfg(), offline=False)
        response = MagicMock()
        response.headers.get_content_type.return_value = "application/octet-stream"
        response.read.return_value = b"binary"
        response.__enter__ = lambda self: response
        response.__exit__ = lambda *a: False
        with patch("urllib.request.urlopen", return_value=response):
            assert ctx.fetch("https://example.com/x") is None

    def test_rejects_oversized_response(self, tmp_path):
        ctx = Context(root=tmp_path, config=_cfg(), offline=False)
        response = MagicMock()
        response.headers.get_content_type.return_value = "text/plain"
        response.read.return_value = b"x" * 100
        response.__enter__ = lambda self: response
        response.__exit__ = lambda *a: False
        with patch("urllib.request.urlopen", return_value=response):
            assert ctx.fetch("https://example.com/x", max_bytes=10) is None

    def test_network_error_returns_none_not_raise(self, tmp_path):
        ctx = Context(root=tmp_path, config=_cfg(), offline=False)
        with patch("urllib.request.urlopen", side_effect=OSError("no route")):
            assert ctx.fetch("https://example.com/x") is None


class TestContextRun:
    def test_missing_command_returns_none(self, tmp_path):
        ctx = Context(root=tmp_path, config=_cfg())
        assert ctx.run(["definitely-not-a-real-command-xyz"]) is None

    def test_runs_a_real_command(self, tmp_path):
        ctx = Context(root=tmp_path, config=_cfg())
        result = ctx.run(["python3", "-c", "print('hi')"])
        assert result is not None
        assert result.stdout.strip() == "hi"

    def test_empty_command_returns_none(self, tmp_path):
        ctx = Context(root=tmp_path, config=_cfg())
        assert ctx.run([]) is None
