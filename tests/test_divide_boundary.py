"""What a ticket says about the files it touches — and what it does not say.

The regression these guard is the one the ticket-template document parked for #38: a
boundary read out of the whole issue body is not a boundary. A stack trace pasted into
an Evidence field would otherwise become the set of files an agent is allowed to edit.
"""

import sys
import unittest
from pathlib import Path

from lanekeeper.config import DivideConfig
from lanekeeper.divide import boundary
from lanekeeper.divide.models import PathSource

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _divide_fixtures import ticket  # noqa: E402


class BoundaryTestCase(unittest.TestCase):
    def setUp(self):
        self.settings = DivideConfig()

    def read(self, issue):
        return boundary.read(issue, self.settings)

    def test_reads_the_paths_the_form_asked_for(self):
        result = self.read(ticket(7, "Add coupons",
                                  ["backend/app/domains/checkout/**",
                                   "frontend/src/components/checkout/Cart.tsx"]))
        self.assertEqual(result.paths,
                         ("backend/app/domains/checkout/**",
                          "frontend/src/components/checkout/Cart.tsx"))
        self.assertEqual(result.source, PathSource.TICKET)
        self.assertTrue(result.has_boundary)

    def test_a_path_elsewhere_in_the_body_is_not_a_boundary(self):
        """The parked defect: an Evidence field full of stack trace is not a claim."""
        issue = ticket(8, "Crash on checkout", paths=(),
                       body_extra="Traceback: backend/app/main.py line 42\n"
                                  "  File 'frontend/src/App.tsx'")
        result = self.read(issue)
        self.assertEqual(result.paths, ())
        self.assertFalse(result.has_boundary)

    def test_an_empty_field_reads_as_no_boundary(self):
        self.assertEqual(self.read(ticket(9, "Something", paths=())).paths, ())

    def test_a_body_with_no_form_at_all_reads_as_no_boundary(self):
        from lanekeeper.trackers.base import TrackedIssue
        issue = TrackedIssue(ref="10", title="Hand written",
                             body="## Why\n\nWe should change backend/app/main.py.\n")
        self.assertEqual(self.read(issue).paths, ())

    def test_the_section_ends_at_the_next_field(self):
        from lanekeeper.trackers.base import TrackedIssue
        body = ("### Allowed File Paths\n\nbackend/app/domains/cart/**\n\n"
                "### Anything else\n\nfrontend/src/whatever.tsx\n")
        self.assertEqual(self.read(TrackedIssue(ref="11", title="t", body=body)).paths,
                         ("backend/app/domains/cart/**",))

    def test_decoration_and_separators_are_normalised(self):
        from lanekeeper.trackers.base import TrackedIssue
        body = ("### Allowed File Paths\n\n"
                "- `backend\\app\\domains\\cart\\service.py`\n"
                "* ./frontend/src/cart/\n"
                "  /docs/cart.md,\n"
                "```\n"
                "tests/test_cart.py\n"
                "```\n")
        result = self.read(TrackedIssue(ref="12", title="t", body=body))
        self.assertEqual(result.paths, (
            "backend/app/domains/cart/service.py",
            "frontend/src/cart/**",
            "docs/cart.md",
            "tests/test_cart.py",
        ))

    def test_prose_in_the_box_is_not_taken_for_a_path(self):
        from lanekeeper.trackers.base import TrackedIssue
        body = ("### Allowed File Paths\n\n"
                "I am not sure which files this touches\n"
                "backend/app/domains/cart/**\n")
        self.assertEqual(self.read(TrackedIssue(ref="13", title="t", body=body)).paths,
                         ("backend/app/domains/cart/**",))

    def test_githubs_empty_marker_is_not_a_path(self):
        from lanekeeper.trackers.base import TrackedIssue
        body = "### Allowed File Paths\n\n_No response_\n"
        self.assertEqual(self.read(TrackedIssue(ref="14", title="t", body=body)).paths, ())

    def test_the_declared_feature_name_is_carried_through(self):
        result = self.read(ticket(15, "Coupons", ["backend/x.py"], lane="checkout"))
        self.assertEqual(result.declared_lane, "checkout")

    def test_a_blank_feature_name_is_ordinary_input(self):
        """The form tells the filer to leave it blank when unsure. Not a defect."""
        result = self.read(ticket(16, "Coupons", ["backend/x.py"]))
        self.assertEqual(result.declared_lane, "")
        self.assertTrue(result.has_boundary)

    def test_the_heading_is_configuration_not_a_constant(self):
        from lanekeeper.trackers.base import TrackedIssue
        settings = DivideConfig(path_headings=["files touched"])
        body = "### Files touched\n\nbackend/app/domains/cart/**\n"
        result = boundary.read(TrackedIssue(ref="17", title="t", body=body), settings)
        self.assertEqual(result.paths, ("backend/app/domains/cart/**",))

    def test_duplicate_lines_are_listed_once(self):
        result = self.read(ticket(18, "t", ["backend/a.py", "backend/a.py"]))
        self.assertEqual(result.paths, ("backend/a.py",))


if __name__ == "__main__":
    unittest.main()


class TestProductPlaybookTickets(unittest.TestCase):
    """The companion tool's own ticket shape, as found on the first real project."""

    BODY = (
        "# [FEAT-01]: Issue CRUD (M1)\n\n### 🎯 Feature Overview & User Goal\nProvide a fast UI.\n\n"
        "---\n\n### 📁 Target Modules & Exact File Names\n"
        "- [x] **Domain / Contracts:** `src/domain/contracts.ts` *(IssueContract, validateIssue)*\n"
        "- [ ] **Services / Logic:** `src/services/issueService.ts` *(CRUD & validation)*\n"
        "- [ ] **UI Components:** \n"
        "  - `src/components/features/IssueCard.tsx` *(Interactive card)*\n"
        "  - `src/components/features/NewIssueModal.tsx`\n"
        "- [x] **Automated Tests:** `tests/unit/promptSynthesis.test.ts` & `tests/unit/contracts.test.ts`\n\n"
        "---\n\n### 🛠️ Step-by-Step Implementation Tasks\n- [ ] 1. Implement `IssueService` in `src/services/issueService.ts`.\n"
    )

    def test_the_heading_with_an_emoji_and_backticked_paths_is_read(self):
        from lanekeeper.config import DivideConfig
        b = boundary.read(_issue(1, "t", self.BODY), DivideConfig())
        self.assertEqual(b.paths, (
            "src/domain/contracts.ts",
            "src/services/issueService.ts",
            "src/components/features/IssueCard.tsx",
            "src/components/features/NewIssueModal.tsx",
            "tests/unit/promptSynthesis.test.ts",
            "tests/unit/contracts.test.ts",
        ))
        self.assertEqual(b.ignored_lines, ("- [ ] **UI Components:**",))

    def test_paths_in_the_tasks_section_are_not_a_boundary(self):
        from lanekeeper.config import DivideConfig
        b = boundary.read(_issue(1, "t", self.BODY), DivideConfig())
        self.assertNotIn("IssueService", " ".join(b.paths))


def _issue(ref, title, body):
    from lanekeeper.trackers.base import TrackedIssue
    return TrackedIssue(ref=str(ref), title=title, body=body)


class TestHtmlCommentsInTheForm(unittest.TestCase):
    """The guidance a form carries in HTML comments is not something the filer wrote (#75).

    product-playbook's issue template puts its instructions in `<!-- … -->` blocks under
    each heading, and GitHub keeps them in the body while rendering nothing. A parser
    that reads lines under a heading reads the guidance as the answer: a blank Lane
    field came back as the whole comment, and a backticked example path inside the
    Target Files guidance became a boundary the merge gate would then enforce.
    """

    FORM = (
        "### Lane\n\n"
        "<!-- Leave blank if unsure. Example: `checkout` -->\n\n"
        "### 📁 Target Modules & Exact File Names\n\n"
        "<!-- Name a file, never `src/services/`. Example: `src/services/quoteEngine.ts` -->\n"
        "- [x] **Service:** `src/checkout/service.ts`\n"
    )

    def read(self, body, ref=75):
        return boundary.read(_issue(ref, "t", body), DivideConfig())

    def test_a_guidance_comment_under_a_blank_lane_is_not_a_lane_name(self):
        self.assertEqual(self.read(self.FORM).declared_lane, "")

    def test_a_lane_written_beside_the_guidance_is_still_read(self):
        body = self.FORM.replace("`checkout` -->\n", "`checkout` -->\ncheckout\n")
        self.assertEqual(self.read(body).declared_lane, "checkout")

    def test_example_paths_inside_a_comment_are_not_a_boundary(self):
        b = self.read(self.FORM)
        self.assertEqual(b.paths, ("src/checkout/service.ts",))
        # Not a boundary, and not a dropped line either: the filer never wrote it, so
        # there is nothing to show them.
        self.assertEqual(b.ignored_lines, ())
        self.assertNotIn("quoteEngine", " ".join(b.ignored_lines))

    def test_a_comment_spanning_several_lines_is_stripped_whole(self):
        body = (
            "### Allowed File Paths\n\n"
            "<!--\n"
            "  List every file this ticket touches, one per line.\n"
            "  Example: `src/services/quoteEngine.ts`\n"
            "  A directory such as src/legacy/ is too broad.\n"
            "-->\n"
            "src/checkout/service.ts\n"
            "src/checkout/service.test.ts\n"
        )
        b = self.read(body)
        self.assertEqual(b.paths, ("src/checkout/service.ts", "src/checkout/service.test.ts"))
        self.assertEqual(b.ignored_lines, ())

    def test_several_comments_on_one_line_leave_the_path_between_them(self):
        body = ("### Allowed File Paths\n\n"
                "<!-- a --> src/checkout/service.ts <!-- `src/b.ts` -->\n")
        b = self.read(body)
        self.assertEqual(b.paths, ("src/checkout/service.ts",))
        self.assertEqual(b.ignored_lines, ())

    def test_a_comment_that_opens_under_one_heading_and_closes_under_the_next(self):
        """GitHub hides everything between the markers, headings included."""
        body = (
            "### Lane\n\n"
            "<!-- the template used to have a field here\n"
            "### Allowed File Paths\n"
            "`src/old/example.ts`\n"
            "-->\n"
            "### Allowed File Paths\n\n"
            "src/checkout/service.ts\n"
        )
        b = self.read(body)
        self.assertEqual(b.declared_lane, "")
        self.assertEqual(b.paths, ("src/checkout/service.ts",))

    def test_an_unterminated_comment_hides_the_rest_of_the_body(self):
        """A `<!--` nobody closed swallows everything after it, which is how GitHub
        renders it — the filer saw no field there, so nothing there was stated."""
        body = ("### Allowed File Paths\n\n"
                "src/checkout/service.ts\n"
                "<!-- oops\n"
                "src/services/quoteEngine.ts\n")
        b = self.read(body)
        self.assertEqual(b.paths, ("src/checkout/service.ts",))
        self.assertEqual(b.ignored_lines, ())
