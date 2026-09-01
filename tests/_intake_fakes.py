"""Test doubles for step 1.

Every intake test drives a tracker through the provider interface rather than through
GitHub, which is the point of the interface existing: the judgement is testable without
a network, an account, or `gh` being installed.
"""

from lanekeeper.trackers.base import AvailabilityReport, IssueTracker, TrackedIssue, TrackerError


class FakeTracker(IssueTracker):
    name = "fake"

    def __init__(self, issues=(), available=True, reason="", raise_on_list=False):
        self._issues = list(issues)
        self._available = available
        self._reason = reason
        self._raise = raise_on_list
        self.list_calls = 0

    def is_available(self):
        return AvailabilityReport(available=self._available, reason=self._reason)

    def list_issues(self):
        self.list_calls += 1
        if self._raise:
            raise TrackerError("Reading the issue list from GitHub failed: boom")
        return list(self._issues)


def issue(ref, title, body="backend/app/api/thing.py", labels=("feature",)):
    """A ticket that is usable by default, so a test only spells out what it breaks."""
    return TrackedIssue(ref=str(ref), title=title, body=body, labels=tuple(labels),
                        state="open", url=f"https://example.test/{ref}")


class RecordingRunner:
    """A stand-in for the subprocess call, capturing argv and replaying answers."""

    def __init__(self, results):
        # results maps the second argv word ("auth" / "issue") to (code, stdout, stderr)
        self._results = results
        self.calls = []

    def __call__(self, argv):
        from lanekeeper.trackers.github_issues import CommandResult

        self.calls.append(list(argv))
        key = argv[1] if len(argv) > 1 else ""
        code, out, err = self._results.get(key, (0, "", ""))
        if isinstance(out, Exception):
            raise out
        return CommandResult(code, out, err)
