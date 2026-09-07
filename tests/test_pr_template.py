"""The shipped pull-request template is the last place the layer model survived (#74).

`test_issue_template.py` guards the ticket form: a lane is a feature slice, not a
technology layer, so `Lane` is free text and never a dropdown. The PR template escaped
that pass. It kept a checkbox row of `interface · service · data · platform` and a row
of seat names, which contradicts the rule twice over — the four boxes are layers, and
the gate does not read a checkbox at all. It reads exactly one `lane: <name>` label
(`check.py`), and `policy` is the reserved name for a change to the policy itself.

Since product-playbook 1.7.0 stopped writing a PR template where lanekeeper is present,
this file is the only PR template a lane-mode project gets, so what it teaches is what
the project learns. The strings below are named literally, as in the ticket test: a
restored checkbox must fail on the exact text, not on some cleverer rule a future edit
happens to satisfy.
"""

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: The copy that ships to users. This repository's own `.github/` copy is a different
#: file with a different audience (contributors to lanekeeper, not agents in lanes) and
#: is left to its own devices here; the issue is about the shipped one.
TEMPLATE = REPO / "templates" / "pull_request_template.md"

#: The four layer boxes, exactly as they were written. Any one of them coming back is
#: the regression.
LAYER_CHECKBOXES = ("[ ] interface", "[ ] service", "[ ] data", "[ ] platform")

#: The seat row. Seats are numbers, not something a reviewer needs to tick.
SEAT_CHECKBOXES = ("[ ] SR1", "[ ] SR2", "[ ] JR1", "[ ] JR2")


def text():
    return TEMPLATE.read_text(encoding="utf-8")


class TemplateExists(unittest.TestCase):

    def test_shipped_template_is_present(self):
        self.assertTrue(TEMPLATE.is_file(), f"{TEMPLATE} is missing")


class LaneIsAFeatureNotALayer(unittest.TestCase):
    """The #23 rule, applied to the one template that still broke it."""

    def test_no_layer_checkbox_row(self):
        body = text()
        for box in LAYER_CHECKBOXES:
            with self.subTest(box):
                self.assertNotIn(box, body,
                                 f"the PR template offers '{box}' as a lane")

    def test_lane_comes_from_the_label_the_gate_reads(self):
        """The workflow reads a `lane: <name>` label and nothing else, so the template
        has to point at that label rather than invent a second place to say it."""
        self.assertIn("lane:", text(),
                      "the PR template does not mention the 'lane:' label the gate reads")

    def test_policy_is_named_as_the_reserved_lane(self):
        """A change to the policy files is denied to every ordinary lane; a template
        that does not say so leaves the author guessing why the gate refused them."""
        self.assertIn("policy", text().lower(),
                      "the PR template does not name the reserved 'policy' lane")


class NoSeatRow(unittest.TestCase):
    """Seats are numbers on capability cards. `declare` prints the seat if anyone
    wants it; a reviewer ticking one by hand is the honour system the command
    replaced."""

    def test_no_seat_checkbox_row(self):
        body = text()
        for box in SEAT_CHECKBOXES:
            with self.subTest(box):
                self.assertNotIn(box, body, f"the PR template asks the author to tick '{box}'")


class TheGateIsNamed(unittest.TestCase):
    """The declaration block must ask for the output of the thing that actually
    checks the boundary, so the pasted text and the CI result describe one run."""

    def test_mentions_lanekeeper_check(self):
        self.assertIn("lanekeeper check", text(),
                      "the PR template never mentions 'lanekeeper check'")

    def test_still_mentions_declare(self):
        """`lanekeeper declare <agent>` exists and generates this section from recorded
        state. Dropping the mention would orphan the command."""
        self.assertIn("lanekeeper declare", text(),
                      "the PR template no longer mentions 'lanekeeper declare'")


class ClosesTheIssue(unittest.TestCase):

    def test_has_closes_line(self):
        self.assertIn("Closes #", text(), "the PR template has no 'Closes #' line")


if __name__ == "__main__":
    unittest.main()
