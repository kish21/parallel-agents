"""What a fresh worktree is missing: the dependencies.

A git worktree is a checkout of tracked files, and `node_modules` is not tracked. So
the window `lanekeeper open` puts on screen has a project in it that cannot run its
tests, cannot start its dev server, and shows an editor full of unresolved imports —
and until this module existed nothing said so. "Lanekeeper has prepared the desk" was
a claim, and the desk was missing the one thing needed to do any work at it.

This module *says* what to run; it never runs it. Silently spending several minutes and
several hundred megabytes per spawn, unasked, is the same category of mistake as
auto-starting five dev servers — the reason `commands:` was made opt-in. And it guesses
nothing: the lockfile is the reliable signal for which package manager a project uses,
and a project with no lockfile is told that the install is its own call. A repository
with no manifest at all gets no line, because inventing a dependency step is noise.
Issue #73.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

#: Lockfile → the install command that honours it, in the order they are looked for.
#: A lockfile is a stronger claim than a manifest: it names the tool *and* the versions.
LOCKFILES: Tuple[Tuple[str, str], ...] = (
    ("pnpm-lock.yaml", "pnpm install --frozen-lockfile"),
    ("yarn.lock", "yarn install --immutable"),
    ("package-lock.json", "npm ci"),
    ("uv.lock", "uv sync"),
    ("poetry.lock", "poetry install"),
    ("Pipfile.lock", "pipenv sync"),
    ("Gemfile.lock", "bundle install"),
    ("composer.lock", "composer install"),
)

#: Manifests that mean "this project has dependencies" without saying how to get them.
MANIFESTS: Tuple[str, ...] = (
    "package.json", "pyproject.toml", "requirements.txt", "Pipfile", "Gemfile",
    "composer.json",
)


@dataclass(frozen=True)
class DependencyStep:
    """What to run once per worktree before any work, or that it is the person's call."""

    #: The file that identified the project.
    evidence: str
    #: The command, or None when the manifest is recognised but no lockfile says how.
    command: Optional[str]

    def line(self) -> str:
        if self.command:
            return self.command
        return (f"this project has a {self.evidence} but no lockfile, so which install "
                f"command to run is your call")


def detect(root: Path) -> Optional[DependencyStep]:
    """The dependency step for the project at `root`, or None when it has none.

    Read from the main checkout rather than the worktree: they hold the same tracked
    files, and the main checkout exists before the worktree does, so the answer is the
    same and available earlier.
    """
    for lockfile, command in LOCKFILES:
        if (root / lockfile).is_file():
            return DependencyStep(evidence=lockfile, command=command)
    for manifest in MANIFESTS:
        if (root / manifest).is_file():
            return DependencyStep(evidence=manifest, command=None)
    return None
