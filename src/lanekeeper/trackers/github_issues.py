"""GitHub Issues as one implementation of the tracker interface.

It shells out to the `gh` command line tool rather than talking to the API directly,
because `gh` already holds the user's authentication and already knows which repository
the current directory belongs to. Both of those are things lanekeeper should not
reimplement or store.

The command itself, the repository, the issue state and the page size all come from
configuration. The subprocess call is injected, so every test drives this class without
a network, an account, or `gh` being installed.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from .base import AvailabilityReport, IssueTracker, TrackedIssue, TrackerError

#: A command runner takes an argv list and returns (exit_code, stdout, stderr).
CommandRunner = Callable[[Sequence[str]], "CommandResult"]


class CommandResult:
    """The only part of a completed process this module cares about."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


#: The fields `gh` is asked for, in the order the parser expects to find them.
ISSUE_FIELDS = "number,title,body,labels,state,url"


def _subprocess_runner(root: Path) -> CommandRunner:
    """Runs the command in the repository, so `gh` can infer the repository itself."""

    def run(argv: Sequence[str]) -> CommandResult:
        res = subprocess.run(
            list(argv),
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return CommandResult(res.returncode, res.stdout or "", res.stderr or "")

    return run


class GitHubIssuesTracker(IssueTracker):
    name = "github"

    def __init__(self, settings, root: Path, runner: Optional[CommandRunner] = None):
        """`settings` is the `intake.github` section; `runner` is injected by tests."""
        self._settings = settings
        self._root = Path(root)
        self._run = runner or _subprocess_runner(self._root)

    # -- reading -----------------------------------------------------------------

    def is_available(self) -> AvailabilityReport:
        try:
            res = self._run([self._settings.command, "auth", "status"])
        except FileNotFoundError:
            return AvailabilityReport(
                available=False,
                reason=(
                    f"The GitHub command line tool ('{self._settings.command}') is not "
                    "installed, so I cannot read this project's issue list. Install it "
                    "from https://cli.github.com and sign in with 'gh auth login'."
                ),
            )
        except OSError as exc:
            return AvailabilityReport(
                available=False,
                reason=f"I could not run the GitHub command line tool: {exc}",
            )

        if res.returncode != 0:
            return AvailabilityReport(
                available=False,
                reason=(
                    "The GitHub command line tool is installed but not signed in, so I "
                    "cannot read this project's issue list. Run 'gh auth login' and try "
                    "again."
                ),
            )
        return AvailabilityReport(available=True)

    def list_issues(self) -> List[TrackedIssue]:
        argv = self._list_argv()
        try:
            res = self._run(argv)
        except OSError as exc:  # pragma: no cover - availability check runs first
            raise TrackerError(f"Could not run '{' '.join(argv)}': {exc}") from exc

        if res.returncode != 0:
            raise TrackerError(
                "Reading the issue list from GitHub failed: "
                + (res.stderr.strip() or f"'{' '.join(argv)}' exited {res.returncode}")
            )

        return _parse_issues(res.stdout)

    # -- internals ---------------------------------------------------------------

    def _list_argv(self) -> List[str]:
        s = self._settings
        argv = [
            s.command, "issue", "list",
            "--state", s.state,
            "--limit", str(s.limit),
            "--json", ISSUE_FIELDS,
        ]
        # A blank repository is not a missing value: it means "the one this directory
        # belongs to", which `gh` resolves from the git remote better than we could.
        if s.repo:
            argv += ["--repo", s.repo]
        return argv


def _parse_issues(raw: str) -> List[TrackedIssue]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise TrackerError(f"GitHub returned something I could not read: {exc}") from exc
    if not isinstance(data, list):
        raise TrackerError("GitHub returned something I could not read: expected a list.")

    issues: List[TrackedIssue] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        issues.append(
            TrackedIssue(
                ref=str(item.get("number", "")),
                title=str(item.get("title", "")),
                body=str(item.get("body") or ""),
                labels=tuple(_label_names(item.get("labels"))),
                state=str(item.get("state", "open")).lower(),
                url=str(item.get("url", "")),
            )
        )
    return issues


def _label_names(raw) -> List[str]:
    """`gh` returns labels as objects; older shapes return plain strings."""
    names: List[str] = []
    for label in raw or []:
        if isinstance(label, dict):
            name = label.get("name")
            if name:
                names.append(str(name))
        elif label:
            names.append(str(label))
    return names
