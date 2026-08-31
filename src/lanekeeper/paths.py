"""Filesystem layout for lanekeeper.

Single source of truth for where lanekeeper keeps its files inside a
repository. Every other module asks this one for a path rather than spelling
out a directory name, so the layout is defined in exactly one place.

The name of the top-level directory is read from the ``LANEKEEPER_HOME``
environment variable, falling back to ``.lanekeeper``. It is deliberately
resolved on each call rather than captured at import time, so a process that
sets the variable after importing lanekeeper still gets the directory it
asked for.

The directory name cannot itself live in the configuration file, because the
configuration file lives inside that directory. The environment is the only
place it can be set without hardcoding it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

#: Environment variable overriding the name of lanekeeper's directory.
ENV_HOME = "LANEKEEPER_HOME"

#: Directory name used when the environment does not override it.
DEFAULT_HOME = ".lanekeeper"

CONFIG_FILENAME = "config.yaml"
STATE_DIRNAME = "state"
LOGS_DIRNAME = "logs"
WORKTREES_DIRNAME = "worktrees"


class InvalidHomeError(ValueError):
    """Raised when LANEKEEPER_HOME is set to an unusable directory name."""


def home_dirname() -> str:
    """Return the name of lanekeeper's directory inside a repository.

    Reads ``LANEKEEPER_HOME`` and falls back to ``.lanekeeper``. The value is
    a directory name relative to the repository root: an absolute path or one
    that climbs out of the repository is rejected rather than silently
    accepted, because every caller joins it onto a root directory and would
    otherwise write outside the repository.
    """
    raw = os.environ.get(ENV_HOME)
    if raw is None:
        return DEFAULT_HOME

    value = raw.strip()
    if not value:
        return DEFAULT_HOME

    candidate = Path(value)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise InvalidHomeError(
            f"{ENV_HOME} must be a directory name relative to the repository "
            f"root, not an absolute path: {raw!r}"
        )
    if ".." in candidate.parts:
        raise InvalidHomeError(
            f"{ENV_HOME} must not climb above the repository root: {raw!r}"
        )
    return value


def home(root: Optional[Path] = None) -> Path:
    """Path to lanekeeper's directory, relative to ``root`` when given."""
    base = Path(root) if root is not None else Path()
    return base / home_dirname()


def config_path(root: Optional[Path] = None) -> Path:
    """Path to the configuration file."""
    return home(root) / CONFIG_FILENAME


def state_dir(root: Optional[Path] = None) -> Path:
    """Directory holding agent and port state."""
    return home(root) / STATE_DIRNAME


def logs_dir(root: Optional[Path] = None) -> Path:
    """Directory holding per-agent execution logs."""
    return home(root) / LOGS_DIRNAME


def worktrees_dir(root: Optional[Path] = None) -> Path:
    """Default directory holding per-agent worktrees."""
    return home(root) / WORKTREES_DIRNAME


def default_worktree_dir() -> str:
    """Default value for the configurable ``worktree_dir`` setting.

    Returned with forward slashes so the generated configuration file reads
    the same on every platform.
    """
    return f"{home_dirname()}/{WORKTREES_DIRNAME}"


def ignored_prefixes() -> Tuple[str, ...]:
    """Path prefixes that lane checks treat as lanekeeper's own bookkeeping.

    These are lanekeeper's directory and git's, both of which change as a
    side effect of running an agent and so must never count as the agent
    writing outside its lane.
    """
    return (f"{home_dirname()}/", ".git/")
