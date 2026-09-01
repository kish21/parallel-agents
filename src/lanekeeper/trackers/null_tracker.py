"""The tracker for a project that has not connected one.

This exists so that "no tracker is configured" is a first-class, honest answer rather
than an empty list that reads identically to "you have written nothing down".
"""

from __future__ import annotations

from typing import List

from .base import AvailabilityReport, IssueTracker, TrackedIssue


class NullTracker(IssueTracker):
    name = "none"

    def is_available(self) -> AvailabilityReport:
        return AvailabilityReport(
            available=False,
            reason=(
                "This project is not connected to a place where its work is written "
                "down, so there is nothing for me to read."
            ),
        )

    def list_issues(self) -> List[TrackedIssue]:
        return []
