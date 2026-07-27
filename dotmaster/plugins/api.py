"""
dotmaster/plugins/api.py
The public, versioned contract for dotmaster plugins.

This is the only module third-party plugins should import.  Everything else in
``dotmaster.*`` is internal and may change between releases.

Writing a plugin
----------------

.. code-block:: python

    from dotmaster.plugins.api import Plugin, Context, FileAction

    class TerraformPlugin(Plugin):
        name = "terraform"
        description = "Generates a Terraform skeleton"
        provides = ("iac.terraform",)
        outputs = ("main.tf",)

        def matches(self, config) -> bool:
            return config.plugins.settings.get("terraform", {}).get("enabled", False)

        def plan(self, config, ctx) -> list[FileAction]:
            return [self.file("main.tf", ctx.render("terraform_main.j2", config=config))]

Register it from your package's ``pyproject.toml``::

    [project.entry-points."dotmaster.plugins"]
    terraform = "my_package:TerraformPlugin"

Contract rules
--------------

1. ``plan()`` must be **pure**: it may read files and render templates, but it
   must never write.  The engine decides what actually lands on disk.
2. Declare every path you produce in ``outputs`` so conflicts with other
   plugins are caught before anything is written.
3. Declare capabilities in ``provides`` (e.g. ``"lint.python"``) so two plugins
   cannot silently fight over the same job.
4. Network access and subprocesses go through ``ctx`` so the user's
   ``--offline`` choice is honoured.
"""

from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from dotmaster.core.merge import default_strategy, wrap_managed_block
from dotmaster.core.plan import FileAction, MergeStrategy

if TYPE_CHECKING:
    from dotmaster.config import DotmasterConfig

#: Bumped only when the plugin contract changes incompatibly.  A plugin
#: declaring a higher ``requires_api`` than this is refused at load time.
API_VERSION = 1

__all__ = [
    "API_VERSION",
    "Context",
    "FileAction",
    "MergeStrategy",
    "Plugin",
]


@dataclass(frozen=True)
class Context:
    """
    The services a plugin is allowed to use.

    Passing capabilities through an explicit context (rather than letting
    plugins import whatever they like) is what makes ``--offline`` meaningful
    and gives us a place to enforce per-plugin permissions later.
    """

    root: Path
    config: DotmasterConfig
    offline: bool = True
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("dotmaster.plugin"))

    # -- templates -------------------------------------------------------

    def render(self, template_name: str, **variables: Any) -> str:
        from dotmaster.renderer import render

        return render(template_name, variables)

    # -- filesystem (read-only) -----------------------------------------

    def read(self, relative: str | PurePosixPath) -> str | None:
        """Read an existing project file, or None if it is absent/unreadable."""
        target = self.root / Path(str(relative))
        try:
            return target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def exists(self, relative: str | PurePosixPath) -> bool:
        return (self.root / Path(str(relative))).exists()

    # -- escape hatches --------------------------------------------------

    def fetch(self, url: str, *, timeout: float = 5.0, max_bytes: int = 262_144) -> str | None:
        """
        Fetch a URL, honouring the user's offline preference.

        Returns None when offline, on any error, or if the response is not
        plain text or exceeds *max_bytes*.  Callers must always have a local
        fallback — dotmaster never requires the network to function.
        """
        if self.offline:
            self.log.debug("Offline: skipping request to %s", url)
            return None
        import urllib.request

        from dotmaster import __version__

        if not url.startswith("https://"):
            self.log.warning("Refusing non-HTTPS request to %s", url)
            return None
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": f"dotmaster/{__version__}"}
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get_content_type()
                if not content_type.startswith("text/"):
                    self.log.warning("Unexpected content type %s from %s", content_type, url)
                    return None
                payload = response.read(max_bytes + 1)
        except Exception as exc:
            self.log.debug("Request to %s failed: %s", url, exc)
            return None
        if len(payload) > max_bytes:
            self.log.warning("Response from %s exceeded %d bytes; ignoring.", url, max_bytes)
            return None
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def run(
        self, cmd: Sequence[str], *, capture: bool = True, check: bool = False
    ) -> subprocess.CompletedProcess | None:
        """Run a command in the project root, or None if it is not installed."""
        from dotmaster.runner import command_exists

        if not cmd or not command_exists(cmd[0]):
            return None
        try:
            return subprocess.run(
                list(cmd),
                cwd=str(self.root),
                capture_output=capture,
                text=True,
                check=check,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            self.log.debug("Command %s failed: %s", cmd, exc)
            return None

    def settings(self, plugin_name: str) -> dict[str, Any]:
        return dict(self.config.plugins.settings.get(plugin_name, {}))


class Plugin(ABC):
    """Base class for every dotmaster plugin."""

    #: Unique id, used in CLI commands.  Namespace third-party plugins
    #: (``"acme.terraform"``) to avoid collisions.
    name: str = ""

    #: One-liner shown in ``dotmaster list``.
    description: str = ""

    #: The plugin's own version, reported by ``dotmaster doctor``.
    version: str = "1.0.0"

    #: The plugin API this plugin was written against.
    requires_api: int = API_VERSION

    #: Capability tags (e.g. ``"lint.python"``).  Two active plugins providing
    #: the same capability is reported as a conflict.
    provides: tuple[str, ...] = ()

    #: Paths this plugin can produce.  Shown in ``dotmaster list``.
    outputs: tuple[str, ...] = ()

    #: Human-readable activation summary for ``dotmaster list``.
    triggers: tuple[str, ...] = ()

    # -- activation ------------------------------------------------------

    @abstractmethod
    def matches(self, config: DotmasterConfig) -> bool:
        """Return True when this plugin applies to *config*."""

    # -- planning --------------------------------------------------------

    @abstractmethod
    def plan(self, config: DotmasterConfig, ctx: Context) -> list[FileAction]:
        """Return the files this plugin wants to exist.  Must not write."""

    def post_apply(self, config: DotmasterConfig, ctx: Context) -> None:  # noqa: B027
        """Optional hook run after every file has been written successfully."""

    # -- helpers for subclasses -----------------------------------------

    def file(
        self,
        path: str | PurePosixPath,
        content: str,
        *,
        strategy: MergeStrategy | None = None,
        executable: bool = False,
        description: str = "",
    ) -> FileAction:
        """Build a :class:`FileAction` owned by this plugin."""
        target = PurePosixPath(str(path))
        return FileAction(
            path=target,
            content=content if content.endswith("\n") else content + "\n",
            plugin=self.name,
            strategy=strategy or default_strategy(target),
            executable=executable,
            description=description,
        )

    def json_file(
        self,
        path: str | PurePosixPath,
        data: Any,
        *,
        strategy: MergeStrategy | None = None,
        description: str = "",
    ) -> FileAction:
        """
        Emit JSON from a Python structure.

        Always prefer this to a JSON-shaped Jinja template: it makes
        syntactically invalid output impossible, and the result merges cleanly
        with whatever the user has added.
        """
        import json

        return self.file(
            path,
            json.dumps(data, indent=2, ensure_ascii=False),
            strategy=strategy,
            description=description,
        )

    def block_file(
        self,
        path: str | PurePosixPath,
        content: str,
        *,
        description: str = "",
    ) -> FileAction:
        """Emit content wrapped in dotmaster markers, preserving user additions."""
        from dotmaster.core.merge import comment_prefix

        target = PurePosixPath(str(path))
        return self.file(
            target,
            wrap_managed_block(content, prefix=comment_prefix(target)),
            strategy=MergeStrategy.MANAGED_BLOCK,
            description=description,
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.name!r} v{self.version}>"
