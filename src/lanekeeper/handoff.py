"""Handing off to product-playbook when the work is not written down.

Lanekeeper divides work; it does not invent it. When `start` finds nothing to divide,
the honest next step is product-playbook's `/vision`, `/scope` and `/plan`, which are
Claude Code skills. Until now `start` printed their names and stopped, and the user
left one tool to go and run another.

This module runs them. It starts Claude Code interactively in the project, with the
first skill as the opening prompt, hands the terminal over, and returns when the user
exits. `start` then runs its pre-flight again against whatever now exists. Nothing is
automated past that: the skills are conversations, and a conversation held in the
background is one nobody had.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional, Sequence

Launcher = Callable[[Sequence[str], Path], int]


class HandoffError(RuntimeError):
    """Claude Code could not be started. Reported; `start` stops as it did before."""


def _interactive_launcher(argv: Sequence[str], cwd: Path) -> int:
    """Runs the command on the user's own terminal and waits for it to finish."""
    return subprocess.call(list(argv), cwd=str(cwd))


def can_hand_off(settings, interactive: Optional[bool] = None) -> bool:
    """Whether `start` should open Claude Code rather than only print the steps.

    Off when the configuration says so, and off when there is no terminal to hand over:
    a CI job or a piped command has nobody at the keyboard to hold the conversation.
    """
    if not settings.auto:
        return False
    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
    return bool(interactive)


def command_for(settings) -> List[str]:
    resolved = shutil.which(settings.command)
    if resolved is None:
        raise HandoffError(
            f"product-playbook runs inside Claude Code, and the '{settings.command}' "
            f"command is not on PATH. Install Claude Code, or run the steps yourself: "
            f"{'  then  '.join(settings.steps)}.")
    first = settings.steps[0] if settings.steps else "/vision"
    return [resolved, first]


def run_playbook(settings, root: Path, launcher: Optional[Launcher] = None) -> int:
    """Opens Claude Code on the first playbook step and waits. Returns its exit code."""
    argv = command_for(settings)
    launch = launcher or _interactive_launcher
    try:
        return launch(argv, Path(root))
    except OSError as exc:
        raise HandoffError(f"Could not start '{argv[0]}': {exc}") from exc


def describe(settings) -> str:
    steps = settings.steps or ["/vision", "/scope", "/plan"]
    rest = ", then ".join(steps[1:]) if len(steps) > 1 else ""
    lines = [
        f"🧭 Opening Claude Code here with {steps[0]}, so product-playbook can work out",
        "   what you are building and write the tickets down.",
    ]
    if rest:
        lines.append(f"   When {steps[0]} finishes, run {rest} in the same session.")
    lines.append("   Exit Claude Code when the tickets exist and I will carry on.")
    return "\n".join(lines)
