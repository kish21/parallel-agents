"""Which tickets would make step 2 guess — reported, never edited."""

import sys
import unittest
from pathlib import Path

from lanekeeper.config import IntakeThresholds
from lanekeeper.intake.models import FlagKind
from lanekeeper.intake.quality import flagged_refs, inspect

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _intake_fakes import issue  # noqa: E402


def kinds(flags):
    return {f.kind for f in flags}


class TestQuality(unittest.TestCase):
    def setUp(self):
        self.thresholds = IntakeThresholds()

    def test_a_usable_backlog_produces_no_flags(self):
        flags = inspect(
            [
                issue(1, "Checkout coupon fix", body="backend/app/api/checkout.py"),
                issue(2, "Search facets", body="frontend/src/components/search/Facets.tsx"),
            ],
            self.thresholds,
        )
        self.assertEqual(flags, ())

    def test_a_ticket_that_says_nothing_about_what_it_touches(self):
        flags = inspect([issue(1, "Make it faster", body="It is slow.")], self.thresholds)
        self.assertIn(FlagKind.NO_FILE_HINT, kinds(flags))
        flag = next(f for f in flags if f.kind is FlagKind.NO_FILE_HINT)
        self.assertEqual(flag.issue_refs, ("1",))

    def test_unlabelled_tickets_are_flagged(self):
        flags = inspect([issue(1, "Checkout fix", labels=())], self.thresholds)
        self.assertIn(FlagKind.NO_LABELS, kinds(flags))

    def test_near_identical_titles_are_flagged_as_a_pair(self):
        flags = inspect(
            [issue(1, "Fix the checkout coupon bug"), issue(2, "Fix the checkout coupon bugs")],
            self.thresholds,
        )
        dupes = [f for f in flags if f.kind is FlagKind.POSSIBLE_DUPLICATE]
        self.assertEqual(len(dupes), 1)
        self.assertEqual(set(dupes[0].issue_refs), {"1", "2"})

    def test_distinct_titles_are_not_duplicates(self):
        flags = inspect([issue(1, "Checkout coupons"), issue(2, "Search facets")],
                        self.thresholds)
        self.assertNotIn(FlagKind.POSSIBLE_DUPLICATE, kinds(flags))

    def test_a_ticket_spanning_many_areas_is_flagged(self):
        body = ("backend/app/api.py frontend/src/App.tsx infra/main.tf "
                "docs/guide.md scripts/deploy.sh")
        flags = inspect([issue(1, "Ship everything", body=body)], self.thresholds)
        self.assertIn(FlagKind.BROAD_TICKET, kinds(flags))

    def test_the_breadth_threshold_is_configuration(self):
        body = "backend/app/api.py frontend/src/App.tsx"
        tickets = [issue(1, "Two areas", body=body)]
        self.assertNotIn(FlagKind.BROAD_TICKET,
                         kinds(inspect(tickets, IntakeThresholds(broad_ticket_areas=3))))
        self.assertIn(FlagKind.BROAD_TICKET,
                      kinds(inspect(tickets, IntakeThresholds(broad_ticket_areas=1))))

    def test_flagged_refs_counts_each_ticket_once(self):
        flags = inspect([issue(1, "Vague", body="no paths", labels=())], self.thresholds)
        self.assertEqual(flagged_refs(flags), {"1"})


if __name__ == "__main__":
    unittest.main()
