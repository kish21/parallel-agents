"""Step 2 says nothing a user has to learn a vocabulary to read.

Same guard as step 1's, over step 2's strings, and for the same reason: a wording rule
that lives in a style guide is not enforced, and one asserted over every rendered case
is. The second guard is the constraint that matters most on somebody else's repository —
nothing here may tell them to move a file or reorganise a folder, because a split made
of path patterns never needs them to.
"""

import re
import sys
import unittest
from pathlib import Path

from lanekeeper.divide.models import (
    DivisionProposal,
    DraftProblem,
    Overlap,
    PathSource,
    Placement,
    ProposedLane,
    TicketBoundary,
    ValidationReport,
)
from lanekeeper.divide.presenter import BANNED_WORDS, render, render_confirmation

sys.path.insert(0, str(Path(__file__).resolve().parent))

#: A file name is a name, not a word the reader has to understand - and the file
#: this step writes is `lanes.yaml`, whose name is fixed by the documented schema
#: in README, The lane file. So paths and file names come out before the vocabulary
#: rule is applied to what is left, which is the prose.
_FILENAMES = re.compile(r"\S*/\S*|\S+\.(?:ya?ml|json|md|py|tsx?)\b")


def prose(text: str) -> str:
    """The words of a message, with file names taken out."""
    return _FILENAMES.sub(" ", text).lower()


def flat(text: str) -> str:
    """One line, so an assertion about a sentence is not defeated by where it wrapped."""
    return " ".join(text.split())


#: Wording that would send somebody off to rearrange their project before they
#: can use this at all - which would lock out exactly the legacy repositories
#: that need it most.
RESTRUCTURE_HINTS = (
    "restructure", "reorganise", "reorganize", "rename your", "move the file",
    "move your", "rearrange", "should be laid out", "tidy up your",
)


def lane(name="catalog", paths=("backend/catalog/**",), tickets=("1", "2"),
         placement=Placement.GROUPED, source=PathSource.TICKET):
    return ProposedLane(name=name, paths=tuple(paths), tickets=tuple(tickets),
                        source=source, placement=placement,
                        why="Two pieces of work name the same part of the project.")


def every_case():
    """One of every whole-output shape step 2 can produce."""
    ticket = TicketBoundary(ref="9", title="Make it faster",
                            paths=("backend/x.py",), source=PathSource.PROPOSED)
    return {
        "grouped": render(DivisionProposal(lanes=(lane(),), ticket_count=2), "d.yaml"),
        "pick-list": render(DivisionProposal(
            lanes=(lane("logs", ("ops/log.py",), ("1",), Placement.SINGLE_TICKET),
                   lane("bills", ("billing/x.py",), ("2",), Placement.SINGLE_TICKET)),
            ticket_count=2), "d.yaml"),
        "needs-paths": render(DivisionProposal(
            lanes=(lane(),), needs_paths=(ticket,), ticket_count=3), "d.yaml"),
        "unplaced": render(DivisionProposal(
            lanes=(lane(),),
            unplaced=(TicketBoundary(ref="10", title="Something"),),
            ticket_count=3), "d.yaml"),
        "overlap": render(DivisionProposal(
            lanes=(lane(), lane("cart", ("backend/**",), ("3",))),
            overlaps=(Overlap(left="catalog", right="cart",
                              example_files=("backend/catalog/a.py",), kind="files"),),
            ticket_count=3), "d.yaml"),
        "patterns-only": render(DivisionProposal(
            lanes=(lane(),),
            overlaps=(Overlap(left="a", right="b", kind="patterns-only"),),
            ticket_count=2), "d.yaml"),
        "unclaimed": render(DivisionProposal(
            lanes=(lane(),), unclaimed_examples=("README.md",), ticket_count=2),
            "d.yaml"),
        "from-code": render(DivisionProposal(
            lanes=(lane(source=PathSource.CODE, tickets=()),), ticket_count=2),
            "d.yaml"),
        "nothing": render(DivisionProposal(ticket_count=4), "d.yaml"),
        "kept-draft": render(DivisionProposal(lanes=(lane(),), ticket_count=2),
                             "d.yaml", draft_written=False),
        "ignored-line": render(DivisionProposal(
            lanes=(lane(),),
            ignored_lines=(("1", ("not sure which files yet",)),),
            ticket_count=2), "d.yaml"),
        "confirmed": render_confirmation(
            ValidationReport(lanes=(lane(),)), written="lanes.yaml"),
        "refused-empty": render_confirmation(ValidationReport(
            lanes=(lane(),),
            problems=(DraftProblem(kind="no-paths", subject="a",
                                   detail="'a' does not say which files it covers."),))),
        "refused-overlap": render_confirmation(ValidationReport(
            lanes=(lane(),),
            overlaps=(Overlap(left="a", right="b",
                              example_files=("x.py",), kind="files"),))),
    }


class LanguageTestCase(unittest.TestCase):
    def test_no_case_needs_lanekeepers_own_vocabulary(self):
        for name, text in every_case().items():
            lowered = prose(text)
            for word in BANNED_WORDS:
                self.assertNotRegex(
                    lowered, rf"\b{re.escape(word)}\b",
                    f"the {name} case uses the word '{word}', which a first-time user "
                    "has had no reason to meet")

    def test_no_case_tells_the_user_to_rearrange_their_project(self):
        for name, text in every_case().items():
            lowered = prose(text)
            for hint in RESTRUCTURE_HINTS:
                self.assertNotIn(hint, lowered,
                                 f"the {name} case tells the user to {hint}")

    def test_a_kept_draft_names_the_flag_that_actually_replaces_it(self):
        text = flat(every_case()["kept-draft"])
        self.assertIn("left it exactly as it is", text)
        self.assertIn("--redraft", text)
        self.assertNotIn("--fresh", text)

    def test_a_reading_of_the_project_is_not_described_as_sharing_out_the_work(self):
        """No ticket is inside these groups, so nothing has been shared out yet."""
        text = flat(render(DivisionProposal(
            lanes=(lane(tickets=()),), ticket_count=18), "d.yaml"))
        self.assertIn("how this project looks to me", text)
        self.assertNotIn("one for each agent", text)

    def test_the_pick_list_asks_rather_than_stopping(self):
        text = every_case()["pick-list"]
        self.assertNotIn("🛑", text)
        self.assertIn("on its own", flat(text))
        self.assertIn("lanekeeper divide --confirm", text)

    def test_a_single_entry_carries_no_apology(self):
        text = flat(every_case()["pick-list"]).lower()
        for word in ("degraded", "unfortunately", "could not group", "failed",
                     "only managed"):
            self.assertNotIn(word, text)

    def test_every_proposal_says_it_changed_nothing(self):
        for name, text in every_case().items():
            if name.startswith("refused") or name == "confirmed":
                continue
            self.assertIn("changed nothing", flat(text),
                          f"the {name} case does not say so")

    def test_a_ticket_with_no_files_is_visibly_not_handed_over(self):
        text = every_case()["needs-paths"]
        self.assertIn("#9", text)
        self.assertIn("have not given them out", flat(text))

    def test_the_source_of_every_boundary_is_stated(self):
        self.assertIn("the files the tickets themselves name",
                      flat(every_case()["grouped"]))
        self.assertIn("the files that are already in this project",
                      flat(every_case()["from-code"]))

    def test_a_theoretical_overlap_is_not_reported_as_a_real_one(self):
        text = every_case()["patterns-only"]
        self.assertIn("do not share any file that exists today", flat(text))

    def test_a_refusal_says_nothing_was_written(self):
        for case in ("refused-empty", "refused-overlap"):
            self.assertIn("have not written anything", flat(every_case()[case]))


if __name__ == "__main__":
    unittest.main()
