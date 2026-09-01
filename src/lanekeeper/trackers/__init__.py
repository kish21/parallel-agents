"""Tracker providers, selected by configuration.

`get_tracker` is the only supported way to obtain one. It fails closed on an
unrecognised name rather than falling back to a default, because silently reading a
different tracker than the one configured would make every later step wrong in a way
nobody would notice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import AvailabilityReport, IssueTracker, TrackedIssue, TrackerError
from .github_issues import GitHubIssuesTracker
from .null_tracker import NullTracker

__all__ = [
    "AvailabilityReport",
    "GitHubIssuesTracker",
    "IssueTracker",
    "NullTracker",
    "TrackedIssue",
    "TrackerError",
    "UnknownTrackerError",
    "get_tracker",
    "known_trackers",
]


class UnknownTrackerError(ValueError):
    """Raised when the configured tracker name matches no implementation."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(
            f"Unknown tracker '{name}'. Available: {', '.join(known_trackers())}."
        )


def known_trackers() -> list:
    return [GitHubIssuesTracker.name, NullTracker.name]


def get_tracker(settings, root: Path, runner: Optional[object] = None) -> IssueTracker:
    """Builds the tracker named by `settings.tracker` (the `intake` config section)."""
    name = (settings.tracker or "").strip().lower()
    if name == GitHubIssuesTracker.name:
        return GitHubIssuesTracker(settings.github, root, runner=runner)  # type: ignore[arg-type]
    if name == NullTracker.name:
        return NullTracker()
    raise UnknownTrackerError(settings.tracker)
