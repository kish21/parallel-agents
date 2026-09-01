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
CAPABILITIES_DIRNAME = "capabilities"
START_DIRNAME = "start"
INTAKE_FILENAME = "intake.json"


class InvalidHomeError(ValueError):
    """Raised when LANEKEEPER_HOME is set to an unusable directory name."""


def _validated_override() -> Optional[str]:
    """Return the environment override, or None when it is unset or blank.

    A value that is absolute, or that climbs out of the repository, is
    rejected rather than silently accepted: every caller joins it onto a
    repository root and would otherwise write outside the repository.
    """
    raw = os.environ.get(ENV_HOME)
    if raw is None:
        return None

    value = raw.strip()
    if not value:
        return None

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


def home_dirname(root: Optional[Path] = None) -> str:
    """Return the name of lanekeeper's directory inside a repository.

    ``root`` is accepted so every function in this module takes the same
    argument, but the name does not depend on it: it is the environment
    override when set, and the default otherwise.
    """
    override = _validated_override()
    return override if override is not None else DEFAULT_HOME


def home(root: Optional[Path] = None) -> Path:
    """Path to lanekeeper's directory, relative to ``root`` when given."""
    base = Path(root) if root is not None else Path()
    return base / home_dirname(root)


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


def capabilities_dir(root: Optional[Path] = None) -> Path:
    """Directory holding per-seat capability cards."""
    return home(root) / CAPABILITIES_DIRNAME


def start_dir(root: Optional[Path] = None) -> Path:
    """Directory holding what each step of `lanekeeper start` has decided.

    Every step writes its result here before the next one runs, which is what makes
    `start` resumable rather than restartable.
    """
    return home(root) / START_DIRNAME


def intake_record_path(root: Optional[Path] = None) -> Path:
    """The recorded result of step 1: is the work written down, and does it cover
    the features."""
    return start_dir(root) / INTAKE_FILENAME


def divide_draft_path(root: Optional[Path] = None,
                      relative: str = "start/lanes.draft.yaml") -> Path:
    """The proposed division of the work, written for the user to edit.

    A draft rather than the real lane file: step 2 proposes and the user confirms, so
    what it writes must be somewhere that carries no authority. `relative` comes from
    the configuration rather than from here, because where a project keeps its draft is
    the project's business; the default is stated at the call site's dataclass.
    """
    return home(root) / Path(relative)


def _posix(*parts: str) -> str:
    """Join with forward slashes, for text shown to users or written to files."""
    return "/".join(parts)


def display_home(root: Optional[Path] = None) -> str:
    """Directory name as it should appear in messages, with a trailing slash."""
    return _posix(home_dirname(root), "")


def display_config_path(root: Optional[Path] = None) -> str:
    """Configuration file path as it should appear in messages."""
    return _posix(home_dirname(root), CONFIG_FILENAME)


def display_capabilities_dir(root: Optional[Path] = None) -> str:
    """Capabilities directory as it should appear in messages."""
    return _posix(home_dirname(root), CAPABILITIES_DIRNAME, "")


def default_worktree_dir(root: Optional[Path] = None) -> str:
    """Default value for the configurable ``worktree_dir`` setting.

    Returned with forward slashes so the generated configuration file reads
    the same on every platform.
    """
    return _posix(home_dirname(root), WORKTREES_DIRNAME)


def ignored_prefixes(root: Optional[Path] = None) -> Tuple[str, ...]:
    """Path prefixes that lane checks treat as bookkeeping rather than work.

    These are lanekeeper's directory and git's, both of which change as a side
    effect of running an agent and so must never count as an agent writing
    outside its lane.
    """
    return (_posix(home_dirname(root), ""), ".git/")


def gitignore_lines(root: Optional[Path] = None) -> Tuple[str, ...]:
    """The .gitignore entries `init` writes for lanekeeper's own directory.

    Everything in the directory is ignored except the configuration file,
    which is the lane policy every agent is validated against and so belongs
    in version control.
    """
    name = home_dirname(root)
    return (
        f"/{name}/*",
        f"!/{name}/{CONFIG_FILENAME}",
    )
