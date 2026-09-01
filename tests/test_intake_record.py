"""The recorded result, and the fingerprint that decides whether it still applies."""

import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper import paths
from lanekeeper.config import IntakeConfig, IntakeThresholds
from lanekeeper.intake import record
from lanekeeper.intake.gate import run_intake
from lanekeeper.intake.models import (
    CoverageReport,
    CoverageVerdict,
    Feature,
    FlagKind,
    IntakeResult,
    ProductSpec,
    QualityFlag,
    SpecSource,
    Verdict,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _intake_fakes import FakeTracker, issue  # noqa: E402

SPEC = ProductSpec(source=SpecSource.PRODUCT_MD, path="PRODUCT.md",
                   features=(Feature(name="Checkout"),))


class TestFingerprint(unittest.TestCase):
    def test_stable_across_runs_and_ordering(self):
        a = [issue(1, "Checkout"), issue(2, "Search")]
        b = [issue(2, "Search"), issue(1, "Checkout")]
        self.assertEqual(record.fingerprint("fake", a, SPEC),
                         record.fingerprint("fake", b, SPEC))

    def test_changing_a_title_changes_it(self):
        before = record.fingerprint("fake", [issue(1, "Checkout")], SPEC)
        after = record.fingerprint("fake", [issue(1, "Checkout coupons")], SPEC)
        self.assertNotEqual(before, after)

    def test_changing_the_features_changes_it(self):
        other = ProductSpec(source=SpecSource.PRODUCT_MD, path="PRODUCT.md",
                            features=(Feature(name="Checkout"), Feature(name="Billing")))
        self.assertNotEqual(record.fingerprint("fake", [issue(1, "Checkout")], SPEC),
                            record.fingerprint("fake", [issue(1, "Checkout")], other))

    def test_the_tracker_is_part_of_it(self):
        self.assertNotEqual(record.fingerprint("fake", [issue(1, "X")], SPEC),
                            record.fingerprint("github", [issue(1, "X")], SPEC))


class TestRecordFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _result(self):
        return IntakeResult(
            verdict=Verdict.READY,
            issue_count=4,
            coverage=CoverageReport(verdict=CoverageVerdict.COVERED,
                                    source=SpecSource.PRODUCT_MD,
                                    source_path="PRODUCT.md",
                                    uncovered=(Feature(name="Billing"),)),
            flags=(QualityFlag(kind=FlagKind.NO_LABELS, issue_refs=("7",), detail="d"),),
            tracker_name="fake",
            label_counts=(("bug", 2),),
            fingerprint="abc",
            recorded_at="2026-09-01T00:00:00+00:00",
        )

    def test_round_trip(self):
        record.save(self._result(), self.root)
        loaded = record.load(self.root)
        self.assertEqual(loaded, self._result())

    def test_written_inside_lanekeepers_own_directory(self):
        written = record.save(self._result(), self.root)
        self.assertEqual(written, paths.intake_record_path(self.root))
        self.assertTrue(str(written).startswith(str(paths.home(self.root))))

    def test_missing_record_is_none(self):
        self.assertIsNone(record.load(self.root))

    def test_a_corrupt_record_is_discarded_rather_than_raised(self):
        path = paths.intake_record_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(record.load(self.root))

    def test_a_record_from_another_version_is_ignored(self):
        path = paths.intake_record_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"record_version": 999, "verdict": "ready"}', encoding="utf-8")
        self.assertIsNone(record.load(self.root))


class TestResume(unittest.TestCase):
    """Fix your work, run it again, and it continues rather than restarting."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "PRODUCT.md").write_text(
            "## Scope\n- Checkout\n- Search\n", encoding="utf-8")
        self.settings = IntakeConfig(tracker="fake")
        self.issues = [
            issue(1, "Checkout coupon fix", body="backend/api/checkout.py"),
            issue(2, "Search facets", body="frontend/src/search/Facets.tsx"),
            issue(3, "Checkout address form", body="frontend/src/checkout/Address.tsx"),
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_passing_run_is_recorded_and_the_next_run_resumes(self):
        tracker = FakeTracker(self.issues)
        first = run_intake(self.root, self.settings, tracker)
        self.assertIs(first.verdict, Verdict.READY)
        self.assertFalse(first.resumed)
        self.assertTrue(paths.intake_record_path(self.root).is_file())

        second = run_intake(self.root, self.settings, FakeTracker(self.issues))
        self.assertTrue(second.resumed)
        self.assertIs(second.verdict, Verdict.READY)

    def test_changed_work_is_judged_again(self):
        run_intake(self.root, self.settings, FakeTracker(self.issues))
        changed = self.issues + [issue(4, "Billing invoices", body="backend/api/billing.py")]
        again = run_intake(self.root, self.settings, FakeTracker(changed))
        self.assertFalse(again.resumed)
        self.assertEqual(again.issue_count, 4)

    def test_fresh_ignores_the_record(self):
        run_intake(self.root, self.settings, FakeTracker(self.issues))
        again = run_intake(self.root, self.settings, FakeTracker(self.issues),
                           use_record=False)
        self.assertFalse(again.resumed)

    def test_a_stopped_run_records_nothing(self):
        empty_root = Path(tempfile.mkdtemp())
        try:
            result = run_intake(empty_root, IntakeConfig(tracker="fake"), FakeTracker([]))
            self.assertIs(result.verdict, Verdict.NEEDS_PLAYBOOK)
            self.assertFalse(paths.home(empty_root).exists())
        finally:
            import shutil
            shutil.rmtree(empty_root, ignore_errors=True)

    def test_taking_it_as_is_passes_and_is_remembered(self):
        # No PRODUCT.md here, so coverage cannot be judged.
        root = Path(tempfile.mkdtemp())
        try:
            settings = IntakeConfig(tracker="fake")
            stopped = run_intake(root, settings, FakeTracker(self.issues))
            self.assertIs(stopped.verdict, Verdict.NEEDS_TIDYING)
            self.assertFalse(paths.intake_record_path(root).is_file())

            accepted = run_intake(root, settings, FakeTracker(self.issues),
                                  accept_as_is=True)
            self.assertIs(accepted.verdict, Verdict.READY)
            self.assertTrue(accepted.accepted_as_is)
            self.assertTrue(record.load(root).accepted_as_is)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_taking_it_as_is_never_overrides_a_coverage_gap(self):
        (self.root / "PRODUCT.md").write_text(
            "## Scope\n- Checkout\n- Billing\n", encoding="utf-8")
        result = run_intake(self.root, self.settings, FakeTracker(self.issues),
                            accept_as_is=True)
        self.assertIs(result.verdict, Verdict.NEEDS_PLAYBOOK)

    def test_an_unreadable_tracker_is_not_an_empty_backlog(self):
        tracker = FakeTracker([], available=False, reason="not signed in")
        result = run_intake(self.root, self.settings, tracker)
        self.assertIs(result.verdict, Verdict.NEEDS_TIDYING)
        self.assertFalse(result.tracker_available)
        self.assertEqual(result.tracker_note, "not signed in")

    def test_a_read_failure_does_not_report_an_empty_backlog(self):
        result = run_intake(self.root, self.settings,
                            FakeTracker(self.issues, raise_on_list=True))
        self.assertFalse(result.tracker_available)
        self.assertIs(result.verdict, Verdict.NEEDS_TIDYING)

    def test_a_thin_backlog_stops_and_asks(self):
        thin = IntakeConfig(tracker="fake", thresholds=IntakeThresholds(thin_issue_count=10))
        result = run_intake(self.root, thin, FakeTracker(self.issues))
        self.assertIs(result.verdict, Verdict.NEEDS_TIDYING)


if __name__ == "__main__":
    unittest.main()
