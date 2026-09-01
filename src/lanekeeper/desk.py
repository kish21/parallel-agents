"""Opening an agent's worktree in an editor: the desk.

An agent's worktree is a directory. Until somebody opens it in the tool the agent
actually runs in, nothing has happened that a person can see. This module does the
opening. It knows nothing about the editor beyond the command that starts it — `code`
by default, configurable — and it hands over the worktree path and returns. It never
waits: an editor window outlives the command that opened it.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

from .config import EditorConfig


class EditorNotFoundError(RuntimeError):
    """Raised when the configured editor command is not on PATH."""


def editor_command(editor: EditorConfig, worktree: Path) -> List[str]:
    """The argv that opens `worktree`, with the command resolved through PATH.

    Resolved rather than passed bare so that `code` finds `code.cmd` on Windows, and so
    that a missing editor is reported by name instead of as a failed process.
    """
    resolved = shutil.which(editor.command)
    if resolved is None:
        raise EditorNotFoundError(
            f"The editor command '{editor.command}' is not on PATH. Set 'editor.command' "
            f"in the configuration to the command that opens your editor, or open "
            f"{worktree} yourself.")
    return [resolved, *editor.args, str(worktree)]


def open_worktree(editor: EditorConfig, worktree: Path) -> List[str]:
    """Opens the worktree in the editor and returns the command that was run."""
    argv = editor_command(editor, worktree)
    kwargs = dict(cwd=str(worktree), stdin=subprocess.DEVNULL,
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(argv, **kwargs)
    return argv
