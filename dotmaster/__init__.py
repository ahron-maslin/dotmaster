"""
dotmaster — Interactive dotfile generator and manager.

Run `dotmaster init` to set up your project's dotfiles via a guided Q&A.
"""

try:
    from dotmaster._version import __version__
except ImportError:
    # _version.py is generated at build time by hatch-vcs; it may be
    # missing in a source checkout that hasn't been built/installed yet.
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
