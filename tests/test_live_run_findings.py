"""What the first end-to-end run against real GitHub CI turned up (2026-09-09).

Published 0.9.0 ran on `kish21/subscription-tracker`: a real project, real tickets,
a real pull request, a real Actions run. The gate's verdicts were right every time.
One thing was wrong, and only a live run could show it — our own tests asserted the
annotation's *prefix* and never the line GitHub would file it against.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lanekeeper import check
from lanekeeper.lanes import LaneValidationResult


def _report(*errors: str) -> "check.CheckReport":
    return check.CheckReport(
        lane="adhoc-02", base="origin/main", head="HEAD",
        result=LaneValidationResult(lane_name="adhoc-02", is_valid=False),
        errors=list(errors))


class TestTheAnnotationLandsOnALine(unittest.TestCase):
    """`::error file=…` with no `line=` is filed by GitHub at line 0.

    Observed on pull request #16 of subscription-tracker, in the check-run's own
    annotations: `src/app/layout.tsx:0 — outside lane 'adhoc-02'`. Line 0 is not a
    line, so the annotation does not anchor in the Files-changed tab — which is the
    one thing `annotations()`' docstring promises it does. The violation is about the
    whole file, so line 1 is the honest anchor: the top of the file it is about.
    """

    def test_every_annotation_names_a_line(self):
        lines = check.annotations(_report("src/app/layout.tsx: outside lane 'adhoc-02'."))
        self.assertEqual(len(lines), 1)
        self.assertIn("line=1", lines[0],
                      "GitHub files an annotation with no line= at line 0, where it "
                      "does not anchor to the file. Seen on subscription-tracker #16.")

    def test_the_line_comes_before_the_title_so_the_message_still_parses(self):
        lines = check.annotations(_report("src/a.py: outside lane 'adhoc-02'."))
        self.assertTrue(lines[0].startswith("::error file=src/a.py,line=1,"))
        self.assertIn("::outside lane 'adhoc-02'.", lines[0])

    def test_a_violation_that_names_no_file_is_still_left_alone(self):
        lines = check.annotations(_report(
            "Could not read the change, so nothing was checked: boom"))
        self.assertEqual(lines, [])


if __name__ == "__main__":
    unittest.main()
