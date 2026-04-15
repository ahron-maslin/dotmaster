"""
dotmaster/runner.py
Shell command runner — safely delegates to official CLI tools when available.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def command_exists(name: str) -> bool:
    """Return True if *name* is an executable available on PATH."""
    return shutil.which(name) is not None


def run(
    cmd: list[str],
    cwd: Path | None = None,
    *,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """
    Run *cmd* as a subprocess.

    Parameters
    ----------
    cmd     : list[str] — command + arguments
    cwd     : working directory (defaults to current directory)
    capture : if True, stdout/stderr are captured rather than forwarded
    check   : if True, raise CalledProcessError on non-zero exit
    """
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=capture,
        text=True,
        check=check,
    )


def delegate(cmd: list[str], cwd: Path | None = None) -> bool:
    """
    Try to run an official tool command.

    Checks whether *cmd[0]* exists on PATH before executing.
    Returns True on success, False if the command is missing or exits non-zero.
    """
    if not command_exists(cmd[0]):
        return False
    try:
        run(cmd, cwd=cwd, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
