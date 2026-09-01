"""Coverage has three outcomes, and the third one is the point.

"I cannot tell" must never be dressed up as "looks complete". Every later step is
derived from this answer, so a confident-looking verdict on a question that was never
asked would be wrong precisely where it matters most.
"""

import sys
import unittest
from pathlib import Path

from lanekeeper.config import IntakeThresholds
from lanekeeper.intake.coverage import judge
from lanekeeper.intake.models import CoverageVerdict, Feature, ProductSpec, SpecSource

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _intake_fakes import issue  # noqa: E402


def spec(*names, source=SpecSource.PRODUCT_MD, path="PRODUCT.md"):
    return ProductSpec(source=source, path=path,
                       features=tuple(Feature(name=n) for n in names))


class TestCoverage(unittest.TestCase):
    def setUp(self):
        self.thresholds = IntakeThresholds()

    def test_every_feature_matched_is_covered(self):
        report = judge(
            spec("Checkout", "Search"),
            [issue(1, "Checkout fails on an expired coupon"), issue(2, "Search facets")],
            self.thresholds,
        )
        self.assertIs(report.verdict, CoverageVerdict.COVERED)
        self.assertEqual(report.uncovered, ())
        self.assertEqual(report.matches[0].issue_refs, ("1",))

    def test_a_feature_with_no_ticket_is_named(self):
        report = judge(spec("Checkout", "Billing"),
                       [issue(1, "Checkout fails on an expired coupon")],
                       self.thresholds)
        self.assertIs(report.verdict, CoverageVerdict.GAPS)
        self.assertEqual([f.name for f in report.uncovered], ["Billing"])

    def test_nothing_to_compare_against_is_never_a_verdict(self):
        report = judge(ProductSpec(source=SpecSource.NONE),
                       [issue(1, "Anything"), issue(2, "Anything else")],
                       self.thresholds)
        self.assertIs(report.verdict, CoverageVerdict.CANNOT_JUDGE)
        # Nothing is invented: no features, no matches, no gaps.
        self.assertEqual(report.matches, ())
        self.assertEqual(report.uncovered, ())

    def test_an_empty_feature_list_cannot_be_judged_either(self):
        report = judge(spec(), [issue(1, "Anything")], self.thresholds)
        self.assertIs(report.verdict, CoverageVerdict.CANNOT_JUDGE)

    def test_labels_and_body_count_as_evidence_not_just_the_title(self):
        report = judge(
            spec("Voiceover"),
            [issue(1, "Retry the synth call", body="backend/app/stages/voiceover/run.py")],
            self.thresholds,
        )
        self.assertIs(report.verdict, CoverageVerdict.COVERED)

    def test_the_match_threshold_is_configuration(self):
        # A two-word feature against a ticket carrying one of the two words.
        tickets = [issue(1, "Cost tracking for the assembly stage")]
        loose = judge(spec("Video cost"), tickets, IntakeThresholds(feature_match_score=0.5))
        strict = judge(spec("Video cost"), tickets, IntakeThresholds(feature_match_score=0.99))
        self.assertIs(loose.verdict, CoverageVerdict.COVERED)
        self.assertIs(strict.verdict, CoverageVerdict.GAPS)


if __name__ == "__main__":
    unittest.main()
