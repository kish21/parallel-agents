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
