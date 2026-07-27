"""
dotmaster/plugins/builtin/__init__.py
The list of plugins dotmaster ships with, always available regardless of
whether third-party plugin discovery is enabled.
"""

from __future__ import annotations

from dotmaster.plugins.builtin.alembic import AlembicPlugin
from dotmaster.plugins.builtin.database import DatabasePlugin
from dotmaster.plugins.builtin.docker import DockerPlugin
from dotmaster.plugins.builtin.dotenv import DotenvPlugin
from dotmaster.plugins.builtin.editorconfig import EditorConfigPlugin
from dotmaster.plugins.builtin.eslint import ESLintPlugin
from dotmaster.plugins.builtin.github_actions import GitHubActionsPlugin
from dotmaster.plugins.builtin.gitignore import GitignorePlugin
from dotmaster.plugins.builtin.gitlab_ci import GitLabCIPlugin
from dotmaster.plugins.builtin.package_json import PackageJsonPlugin
from dotmaster.plugins.builtin.precommit import PreCommitPlugin
from dotmaster.plugins.builtin.prettier import PrettierPlugin
from dotmaster.plugins.builtin.prisma import PrismaPlugin
from dotmaster.plugins.builtin.pyproject import PyprojectPlugin
from dotmaster.plugins.builtin.ruff import RuffPlugin

BUILTIN_PLUGINS = [
    GitignorePlugin,
    ESLintPlugin,
    PrettierPlugin,
    EditorConfigPlugin,
    DockerPlugin,
    GitHubActionsPlugin,
    GitLabCIPlugin,
    PyprojectPlugin,
    DotenvPlugin,
    RuffPlugin,
    DatabasePlugin,
    AlembicPlugin,
    PrismaPlugin,
    PackageJsonPlugin,
    PreCommitPlugin,
]

__all__ = ["BUILTIN_PLUGINS"]
