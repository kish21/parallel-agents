"""Regressions for the ways step 1 could report something untrue.

Every case here was found by reviewing the first cut of this feature. They are grouped
by the lie each one told, because that is what makes them worth keeping: a step whose
whole purpose is an honest verdict is worth exactly as much as its worst wrong answer.
"""

import sys
import tempfile
import time
import unittest
from pathlib import Path

import yaml

from lanekeeper import paths
from lanekeeper.config import (
    Config,
    IntakeConfig,
    IntakeThresholds,
    InvalidIntakeSettingError,
    load_config,
)
from lanekeeper.intake import record
from lanekeeper.intake.gate import run_intake
from lanekeeper.intake.models import CoverageVerdict, FlagKind, Verdict
from lanekeeper.intake.presenter import render
from lanekeeper.intake.quality import inspect
from lanekeeper.intake.spec import resolve_spec

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _intake_fakes import FakeTracker, issue  # noqa: E402


class TestStaleAnswersAreNotResumed(unittest.TestCase):
    """"Nothing has changed since" has to be true of everything the answer used."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "PRODUCT.md").write_text("## Scope\n- Checkout\n- Search\n",
                                              encoding="utf-8")
        self.settings = IntakeConfig(tracker="fake")
        self.issues = [
            issue(1, "Checkout coupon fix", body="backend/api/checkout.py"),
            issue(2, "Search facets", body="frontend/src/search/Facets.tsx"),
            issue(3, "Checkout address form", body="frontend/src/checkout/Address.tsx"),
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def test_emptying_the_ticket_bodies_is_a_change(self):
        # The bodies are read by both the coverage match and the file-hint check, so a
        # backlog gutted of them is a different backlog.
        run_intake(self.root, self.settings, FakeTracker(self.issues))
        gutted = [issue(i.ref, i.title, body="", labels=i.labels) for i in self.issues]
        again = run_intake(self.root, self.settings, FakeTracker(gutted))
        self.assertFalse(again.resumed)

    def test_editing_a_threshold_is_a_change(self):
        run_intake(self.root, self.settings, FakeTracker(self.issues))
        stricter = IntakeConfig(tracker="fake",
                                thresholds=IntakeThresholds(feature_match_score=0.99))
        again = run_intake(self.root, stricter, FakeTracker(self.issues))
        self.assertFalse(again.resumed)


class TestAStopIsAlwaysExplained(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "PRODUCT.md").write_text("## Scope\n- Checkout\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_thin_backlog_says_that_is_why_it_stopped(self):
        # Coverage is COVERED and there are no flags, so without a stated reason the
        # output would report everything as fine and then exit non-zero.
        settings = IntakeConfig(tracker="fake",
                                thresholds=IntakeThresholds(thin_issue_count=10))
        result = run_intake(self.root, settings,
                            FakeTracker([issue(1, "Checkout", body="api/checkout.py")]))
        self.assertIs(result.verdict, Verdict.NEEDS_TIDYING)
        self.assertTrue(result.stop_reasons)
        text = render(result)
        self.assertIn("only 1 of them", text)
        self.assertIn("10", text)

    def test_too_many_unclear_tickets_says_how_many(self):
        settings = IntakeConfig(tracker="fake")
        vague = [issue(n, f"Checkout thing {n}", body="no paths here", labels=())
                 for n in range(1, 5)]
        result = run_intake(self.root, settings, FakeTracker(vague))
        self.assertIs(result.verdict, Verdict.NEEDS_TIDYING)
        self.assertIn("4 of the 4 are unclear to me", render(result))


class TestResumedWordingMatchesWhatWasFound(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_an_accepted_run_is_not_replayed_as_a_coverage_finding(self):
        # It passed because the user said so, not because anything was checked. Saying
        # "it still covers what this project set out to do" would be the dressed-up
        # verdict the whole step exists to refuse.
        settings = IntakeConfig(tracker="fake")
        issues = [issue(n, f"Thing {n}", body=f"src/thing{n}.py") for n in range(1, 5)]
        run_intake(self.root, settings, FakeTracker(issues), accept_as_is=True)
        resumed = run_intake(self.root, settings, FakeTracker(issues))
        self.assertTrue(resumed.resumed)
        text = render(resumed)
        self.assertIn("already told me it is the whole job", text)
        self.assertNotIn("still covers what this project", text)

    def test_the_count_is_not_doubled_up(self):
        settings = IntakeConfig(tracker="fake")
        issues = [issue(n, f"Thing {n}", body=f"src/thing{n}.py") for n in range(1, 5)]
        run_intake(self.root, settings, FakeTracker(issues), accept_as_is=True)
        text = render(run_intake(self.root, settings, FakeTracker(issues)))
        self.assertNotIn("of work of work", text)


class TestFileHints(unittest.TestCase):
    def test_a_link_is_not_a_statement_about_which_code_is_touched(self):
        flags = inspect([issue(1, "Slow", body="See https://example.test/a/b for detail")],
                        IntakeThresholds())
        self.assertIn(FlagKind.NO_FILE_HINT, {f.kind for f in flags})

    def test_prose_with_a_dot_is_not_a_file(self):
        flags = inspect([issue(1, "Upgrade", body="We should move to Node.js 22, e.g. soon")],
                        IntakeThresholds())
        self.assertIn(FlagKind.NO_FILE_HINT, {f.kind for f in flags})

    def test_a_real_filename_still_counts(self):
        flags = inspect([issue(1, "Fix", body="CheckoutPage.tsx renders twice")],
                        IntakeThresholds())
        self.assertNotIn(FlagKind.NO_FILE_HINT, {f.kind for f in flags})


class TestDuplicateReportingStaysReadable(unittest.TestCase):
    def test_a_large_similar_backlog_is_capped_and_quick(self):
        # 400 near-identical tickets is 79,800 pairs. Uncapped, that was minutes of
        # comparison and a report no one could read.
        issues = [issue(n, f"Fix the checkout coupon bug number {n}",
                        body="backend/api/checkout.py")
                  for n in range(400)]
        started = time.monotonic()
        flags = inspect(issues, IntakeThresholds(duplicate_report_limit=10))
        elapsed = time.monotonic() - started
        dupes = [f for f in flags if f.kind is FlagKind.POSSIBLE_DUPLICATE]
        self.assertLessEqual(len(dupes), 10)
        self.assertLess(elapsed, 20, "duplicate detection should not dominate the run")

    def test_the_limit_is_configuration(self):
        issues = [issue(n, f"Fix the checkout coupon bug {n}") for n in range(6)]
        flags = inspect(issues, IntakeThresholds(duplicate_report_limit=2))
        dupes = [f for f in flags if f.kind is FlagKind.POSSIBLE_DUPLICATE]
        self.assertEqual(len(dupes), 2)


class TestConfigurationErrorsAreExplained(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, intake_section):
        data = Config.default("x").to_dict()
        data["intake"] = intake_section
        home = paths.home(self.root)
        home.mkdir(parents=True, exist_ok=True)
        (home / paths.CONFIG_FILENAME).write_text(yaml.safe_dump(data), encoding="utf-8")

    def test_an_unusable_threshold_names_the_setting(self):
        self._write({"thresholds": {"tidy_flag_ratio": "half"}})
        with self.assertRaises(InvalidIntakeSettingError) as ctx:
            load_config(self.root)
        self.assertIn("intake.thresholds.tidy_flag_ratio", str(ctx.exception))
        self.assertIn("half", str(ctx.exception))

    def test_an_explicitly_empty_source_list_is_honoured(self):
        # "Compare against nothing" is a legitimate instruction, and silently restoring
        # the defaults would judge coverage against a document the user excluded.
        self._write({"spec_sources": []})
        loaded = load_config(self.root)
        self.assertEqual(loaded.intake.spec_sources, [])
        (self.root / "PRODUCT.md").write_text("## Scope\n- Checkout\n", encoding="utf-8")
        spec = resolve_spec(self.root, loaded.intake)
        self.assertFalse(spec.has_features)

    def test_a_blank_tracker_falls_back_to_the_default(self):
        self._write({"tracker": ""})
        self.assertEqual(load_config(self.root).intake.tracker, "github")


if __name__ == "__main__":
    unittest.main()
