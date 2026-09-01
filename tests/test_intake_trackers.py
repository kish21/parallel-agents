"""The tracker provider interface, and GitHub Issues as one implementation of it."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper.config import GitHubTrackerConfig, IntakeConfig
from lanekeeper.trackers import (
    GitHubIssuesTracker,
    NullTracker,
    UnknownTrackerError,
    get_tracker,
)
from lanekeeper.trackers.base import TrackerError, TrackerNotConnectedError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _intake_fakes import RecordingRunner  # noqa: E402

SAMPLE = json.dumps([
    {
        "number": 12,
        "title": "Checkout fails on an expired coupon",
        "body": "backend/app/api/checkout.py",
        "labels": [{"name": "bug"}, {"name": "checkout"}],
        "state": "OPEN",
        "url": "https://example.test/12",
    }
])


class TestTrackerFactory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_factory_selects_by_configuration(self):
        self.assertIsInstance(get_tracker(IntakeConfig(tracker="github"), self.root),
                              GitHubIssuesTracker)
        self.assertIsInstance(get_tracker(IntakeConfig(tracker="none"), self.root),
                              NullTracker)

    def test_unknown_tracker_fails_closed(self):
        with self.assertRaises(UnknownTrackerError) as ctx:
            get_tracker(IntakeConfig(tracker="jira"), self.root)
        self.assertIn("jira", str(ctx.exception))
        self.assertIn("github", str(ctx.exception))

    def test_null_tracker_says_why_rather_than_looking_empty(self):
        tracker = NullTracker()
        report = tracker.is_available()
        self.assertFalse(report.available)
        self.assertIn("written down", report.reason)
        self.assertEqual(tracker.list_issues(), [])


class TestGitHubIssuesTracker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _tracker(self, runner, **overrides):
        settings = GitHubTrackerConfig(**overrides)
        return GitHubIssuesTracker(settings, self.root, runner=runner)

    def test_builds_the_configured_command(self):
        runner = RecordingRunner({"issue": (0, SAMPLE, "")})
        self._tracker(runner, state="all", limit=7).list_issues()
        argv = runner.calls[0]
        self.assertEqual(argv[:3], ["gh", "issue", "list"])
        self.assertIn("--state", argv)
        self.assertEqual(argv[argv.index("--state") + 1], "all")
        self.assertEqual(argv[argv.index("--limit") + 1], "7")
        # A blank repository means "the one this directory belongs to".
        self.assertNotIn("--repo", argv)

    def test_configured_repository_and_executable_are_used(self):
        runner = RecordingRunner({"issue": (0, SAMPLE, "")})
        self._tracker(runner, repo="kish21/parallel-agents", command="gh-wrapper").list_issues()
        argv = runner.calls[0]
        self.assertEqual(argv[0], "gh-wrapper")
        self.assertEqual(argv[argv.index("--repo") + 1], "kish21/parallel-agents")

    def test_parses_issues_into_the_contract(self):
        runner = RecordingRunner({"issue": (0, SAMPLE, "")})
        issues = self._tracker(runner).list_issues()
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue.ref, "12")
        self.assertEqual(issue.labels, ("bug", "checkout"))
        self.assertEqual(issue.state, "open")

    def test_missing_executable_is_an_availability_answer_not_a_crash(self):
        runner = RecordingRunner({"auth": (0, FileNotFoundError("gh"), "")})
        report = self._tracker(runner).is_available()
        self.assertFalse(report.available)
        self.assertIn("not installed", report.reason)

    def test_not_signed_in_is_reported_in_plain_words(self):
        runner = RecordingRunner({"auth": (1, "", "not logged in")})
        report = self._tracker(runner).is_available()
        self.assertFalse(report.available)
        self.assertIn("gh auth login", report.reason)

    def test_signed_in_is_available(self):
        runner = RecordingRunner({"auth": (0, "", "")})
        self.assertTrue(self._tracker(runner).is_available().available)

    def test_a_failed_read_raises_rather_than_reporting_no_work(self):
        runner = RecordingRunner({"issue": (1, "", "HTTP 503: service unavailable")})
        with self.assertRaises(TrackerError) as ctx:
            self._tracker(runner).list_issues()
        self.assertIn("503", str(ctx.exception))
        self.assertNotIsInstance(ctx.exception, TrackerNotConnectedError)

    def test_a_project_with_no_remote_is_not_connected_rather_than_broken(self):
        # A repository that has never been pushed is the ordinary first day of a
        # project. Reporting it as a failure sends the user to fix their setup when
        # what they actually need is to write the work down.
        for stderr in ("no git remotes found",
                       "none of the git remotes configured for this repository "
                       "point to a known GitHub host",
                       "could not resolve to a Repository with the name 'x/y'"):
            with self.subTest(stderr=stderr):
                runner = RecordingRunner({"issue": (1, "", stderr)})
                with self.assertRaises(TrackerNotConnectedError) as ctx:
                    self._tracker(runner).list_issues()
                self.assertIn("not connected to GitHub", str(ctx.exception))

    def test_unreadable_output_raises(self):
        runner = RecordingRunner({"issue": (0, "not json", "")})
        with self.assertRaises(TrackerError):
            self._tracker(runner).list_issues()


if __name__ == "__main__":
    unittest.main()
