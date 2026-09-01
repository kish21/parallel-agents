"""Nothing in step 1 may require the user to know what a lane is.

That is one of #37's four exit criteria, and a wording rule that lives only in a style
guide is not enforced. Every string this step prints comes from `intake.presenter`, so
the rule can be a failing test instead.
"""

import unittest

from lanekeeper.intake.models import (
    CoverageReport,
    CoverageVerdict,
    Feature,
    FlagKind,
    IntakeResult,
    QualityFlag,
    SpecSource,
    Verdict,
)
from lanekeeper.intake.presenter import BANNED_WORDS, render


def result(**overrides):
    base = dict(
        verdict=Verdict.READY,
        issue_count=12,
        coverage=CoverageReport(verdict=CoverageVerdict.COVERED,
                                source=SpecSource.PRODUCT_MD, source_path="PRODUCT.md"),
        tracker_name="github",
    )
    base.update(overrides)
    return IntakeResult(**base)


FLAGS = (QualityFlag(kind=FlagKind.NO_FILE_HINT, issue_refs=("4", "5"),
                     detail="These do not say which part of the project they change."),)

CASES = {
    "nothing written down": result(verdict=Verdict.NEEDS_PLAYBOOK, issue_count=0,
                                   coverage=CoverageReport(CoverageVerdict.CANNOT_JUDGE)),
    "covered": result(),
    "gaps": result(verdict=Verdict.NEEDS_PLAYBOOK,
                   coverage=CoverageReport(CoverageVerdict.GAPS, SpecSource.PRODUCT_MD,
                                           "PRODUCT.md",
                                           uncovered=(Feature(name="Billing"),))),
    "cannot judge": result(verdict=Verdict.NEEDS_TIDYING,
                           coverage=CoverageReport(CoverageVerdict.CANNOT_JUDGE),
                           label_counts=(("bug", 5),), flags=FLAGS),
    "unreadable tracker": result(verdict=Verdict.NEEDS_TIDYING, issue_count=0,
                                 coverage=CoverageReport(CoverageVerdict.CANNOT_JUDGE),
                                 tracker_available=False,
                                 tracker_note="Sign in with 'gh auth login'."),
    "resumed": result(resumed=True),
    "taken as is": result(accepted_as_is=True,
                          coverage=CoverageReport(CoverageVerdict.CANNOT_JUDGE)),
}


class TestPlainLanguage(unittest.TestCase):
    def test_no_case_uses_lanekeepers_own_vocabulary(self):
        for name, case in CASES.items():
            for template in (True, False):
                text = render(case, has_issue_template=template).lower()
                for word in BANNED_WORDS:
                    with self.subTest(case=name, word=word, template=template):
                        self.assertNotRegex(text, r"\b" + word + r"\b")

    def test_no_case_tells_the_user_to_reorganise_their_project(self):
        # Lanes are patterns and can carve a feature out of a messy tree without moving
        # a file, so demanding a tidy layout would lock out the projects that need this
        # most. Step 1 does not comment on the folder structure at all.
        forbidden = ("restructure", "reorganise", "reorganize", "move the file",
                     "rename the folder", "folder structure", "directory structure")
        for name, case in CASES.items():
            text = render(case).lower()
            for phrase in forbidden:
                with self.subTest(case=name, phrase=phrase):
                    self.assertNotIn(phrase, text)


class TestRequiredSentences(unittest.TestCase):
    def test_nothing_written_down_names_the_playbook_and_its_steps(self):
        text = render(CASES["nothing written down"])
        self.assertIn("product-playbook", text)
        for step in ("/vision", "/scope", "/plan"):
            self.assertIn(step, text)
        self.assertIn("changed nothing", text)

    def test_cannot_judge_says_so_plainly_with_the_count(self):
        text = render(CASES["cannot judge"])
        self.assertIn("I count 12 pieces of work", text)
        self.assertIn("cannot tell whether that is", text)
        self.assertNotIn("looks complete", text)

    def test_gaps_name_the_features_with_nothing_written_against_them(self):
        text = render(CASES["gaps"])
        self.assertIn("Billing", text)
        self.assertIn("nothing written", text)

    def test_flags_are_reported_as_untouched(self):
        text = render(CASES["cannot judge"])
        self.assertIn("#4", text)
        self.assertIn("not changed any of them", text)

    def test_the_template_hint_only_appears_when_there_is_a_template(self):
        self.assertNotIn("ticket template", render(CASES["cannot judge"]))
        self.assertIn("ticket template",
                      render(CASES["cannot judge"], has_issue_template=True))

    def test_an_unreadable_tracker_is_not_reported_as_an_empty_backlog(self):
        text = render(CASES["unreadable tracker"])
        self.assertIn("could not read", text)
        self.assertIn("gh auth login", text)
        self.assertNotIn("no written-down work", text)

    def test_a_resumed_run_says_it_is_carrying_on(self):
        self.assertIn("already done", render(CASES["resumed"]))


if __name__ == "__main__":
    unittest.main()
