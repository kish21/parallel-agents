"""The issue-tracker provider interface.

Everything downstream of step 1 — modules, lanes, seats, worktrees — is derived from
the issues, so where the issues come from has to be a choice rather than an assumption.
GitHub Issues is one implementation of this interface, not a fact baked into the logic
that reads it: business code asks the configuration for a tracker and is handed one.

A tracker answers two questions and nothing else: can I read this project's work, and
what does it say. It never judges the work; that is `lanekeeper.intake`'s job.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple


class TrackerError(RuntimeError):
    """Raised when a tracker that reported itself available then failed to read."""


class TrackerNotConnectedError(TrackerError):
    """The project is not connected to this tracker at all.

    Different from a failure, and the difference matters: there is no list of work
    because the project has never had one, which is the ordinary starting point for a
    brand-new project, not a fault to report. A person here needs to be pointed at the
    tool that writes work down, not told that something went wrong.
    """


@dataclass(frozen=True)
class TrackedIssue:
    """One piece of written-down work, in the only shape lanekeeper needs.

    `ref` is the tracker's own identifier — an issue number on GitHub — and is treated
    as opaque text everywhere else, so a tracker that numbers things differently does
    not need a change anywhere but in its own implementation.
    """

    ref: str
    title: str
    body: str = ""
    labels: Tuple[str, ...] = ()
    state: str = "open"
    url: str = ""


@dataclass(frozen=True)
class AvailabilityReport:
    """Whether the tracker can be read, and if not, why — in words a user can act on.

    An unreadable tracker is not an error and not an empty backlog. Both of those
    conclusions would be false, and the second is the dangerous one: it would send a
    user to write work down that they have already written down.
    """

    available: bool
    reason: str = ""


class IssueTracker(ABC):
    """Reads the project's written-down work from wherever it is kept."""

    #: Configuration value that selects this implementation.
    name: str = "unknown"

    @abstractmethod
    def is_available(self) -> AvailabilityReport:
        """Whether this tracker can be read right now, with a plain-language reason."""

    @abstractmethod
    def list_issues(self) -> List[TrackedIssue]:
        """Every open piece of work the tracker knows about.

        Raises `TrackerError` if reading fails after `is_available` said it would work.
        """
