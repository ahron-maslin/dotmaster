"""
dotmaster/plugins/builtin/__init__.py
Exports the list of all built-in plugin classes.
"""
from __future__ import annotations

from dotmaster.plugins.builtin.docker import DockerPlugin
from dotmaster.plugins.builtin.dotenv import DotenvPlugin
from dotmaster.plugins.builtin.editorconfig import EditorConfigPlugin
from dotmaster.plugins.builtin.eslint import ESLintPlugin
from dotmaster.plugins.builtin.gitignore import GitignorePlugin
from dotmaster.plugins.builtin.github_actions import GitHubActionsPlugin
from dotmaster.plugins.builtin.gitlab_ci import GitLabCIPlugin
from dotmaster.plugins.builtin.prettier import PrettierPlugin
from dotmaster.plugins.builtin.pyproject import PyprojectPlugin
from dotmaster.plugins.builtin.ruff import RuffPlugin
from dotmaster.plugins.builtin.database import DatabasePlugin
from dotmaster.plugins.builtin.alembic import AlembicPlugin
from dotmaster.plugins.builtin.prisma import PrismaPlugin

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
]

__all__ = ["BUILTIN_PLUGINS"]
