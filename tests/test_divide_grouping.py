"""Grouping, and the promise that no ticket goes missing.

Two properties matter more than any single case and are asserted on every proposal
here: **every ticket is accounted for exactly once**, and **no ticket without a stated
boundary ever becomes something an agent is handed**. Both are the kind of thing that
holds in the case you wrote and quietly fails in the one you did not, so they are
checked as set identities rather than case by case.
"""

import sys
import unittest
from pathlib import Path

from lanekeeper.config import DivideConfig, DivideThresholds
from lanekeeper.divide import codebase, grouping
from lanekeeper.divide.models import PathSource, Placement
from lanekeeper.divide import boundary as boundary_reader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _divide_fixtures import feature_backlog, feature_files, ticket  # noqa: E402


class GroupingTestCase(unittest.TestCase):
    def setUp(self):
        self.settings = DivideConfig()

    def divide(self, issues, files=None, settings=None):
        settings = settings or self.settings
        boundaries = boundary_reader.read_all(issues, settings)
        slices, note = codebase.slices(Path("."), settings, files=files or [])
        proposal = grouping.proposal(boundaries, slices, settings, code_note=note)
        self.assert_every_ticket_accounted_for(issues, proposal)
        return proposal

    def assert_every_ticket_accounted_for(self, issues, proposal):
        """The promise: exactly one of grouped, needs-paths, or nothing-to-say."""
        placed = list(proposal.placed_refs)
        needs = [b.ref for b in proposal.needs_paths]
        unplaced = [b.ref for b in proposal.unplaced]
        everywhere = placed + needs + unplaced
        self.assertEqual(sorted(everywhere), sorted(str(i.ref) for i in issues))
        self.assertEqual(len(everywhere), len(set(everywhere)),
                         "a ticket appears in more than one place")

    # -- grouping ---------------------------------------------------------------

    def test_tickets_naming_the_same_feature_group(self):
        proposal = self.divide(feature_backlog(), feature_files())
        catalog = next(l for l in proposal.lanes if l.name == "catalog")
        self.assertEqual(sorted(catalog.tickets), ["1", "2"])
        self.assertIs(catalog.placement, Placement.GROUPED)

    def test_the_proposal_is_feature_slices_not_layers(self):
        proposal = self.divide(feature_backlog(), feature_files())
        names = {lane.name for lane in proposal.lanes}
        self.assertIn("catalog", names)
        self.assertIn("checkout", names)
        for layer in ("backend", "frontend", "api", "components", "data", "platform"):
            self.assertNotIn(layer, names)

    def test_a_lone_ticket_is_a_complete_entry_of_its_own(self):
        proposal = self.divide(feature_backlog(), feature_files())
        payments = next(l for l in proposal.lanes if l.name == "payments")
        self.assertEqual(payments.tickets, ("4",))
        self.assertIs(payments.placement, Placement.SINGLE_TICKET)
        self.assertEqual(payments.paths,
                         ("backend/app/domains/payments/stripe_provider.py",))

    def test_a_backlog_that_does_not_group_becomes_a_pick_list(self):
        """Never a stop. Each one is handed out on its own, with its own boundary."""
        issues = [
            ticket(1, "Rotate the log files", ["ops/logrotate.py"]),
            ticket(2, "Fix the invoice total", ["billing/invoice.py"]),
            ticket(3, "Speed up the importer", ["importer/run.py"]),
        ]
        proposal = self.divide(issues)
        self.assertEqual(len(proposal.lanes), 3)
        self.assertTrue(all(l.placement is Placement.SINGLE_TICKET
                            for l in proposal.lanes))
        self.assertEqual(proposal.needs_paths, ())
        self.assertEqual(proposal.unplaced, ())

    def test_the_grouping_threshold_is_configuration(self):
        settings = DivideConfig(thresholds=DivideThresholds(min_group_tickets=3))
        proposal = self.divide(feature_backlog(), feature_files(), settings)
        self.assertTrue(all(l.placement is Placement.SINGLE_TICKET
                            for l in proposal.lanes))

    def test_the_filers_own_feature_name_groups_on_its_own(self):
        issues = [
            ticket(1, "Rotate logs", ["ops/logrotate.py"], lane="housekeeping"),
            ticket(2, "Prune old exports", ["exports/prune.py"], lane="housekeeping"),
        ]
        proposal = self.divide(issues)
        self.assertEqual([l.name for l in proposal.lanes], ["housekeeping"])
        self.assertEqual(sorted(proposal.lanes[0].tickets), ["1", "2"])

    def test_a_ticket_lands_in_the_most_specific_group_it_matches(self):
        issues = [
            ticket(1, "a", ["shop/catalog/pricing/rules.py", "web/catalog/Price.tsx"]),
            ticket(2, "b", ["shop/catalog/pricing/tax.py"]),
            ticket(3, "c", ["shop/catalog/listing.py"]),
        ]
        proposal = self.divide(issues)
        pricing = next(l for l in proposal.lanes if l.name == "pricing")
        self.assertEqual(sorted(pricing.tickets), ["1", "2"])

    def test_the_same_backlog_divides_the_same_way_every_time(self):
        issues = feature_backlog()
        first = self.divide(issues, feature_files())
        second = self.divide(list(reversed(issues)), feature_files())
        self.assertEqual([(l.name, sorted(l.tickets)) for l in first.lanes],
                         [(l.name, sorted(l.tickets)) for l in second.lanes])

    def test_two_entries_never_share_a_name(self):
        issues = [
            ticket(1, "one", ["a/cart/x.py"]),
            ticket(2, "two", ["b/cart/y.py"]),
        ]
        # Both name `cart`, and with the default threshold they group; forcing them
        # apart must still leave two distinguishable entries.
        settings = DivideConfig(thresholds=DivideThresholds(min_group_tickets=5))
        proposal = self.divide(issues, settings=settings)
        names = [lane.name for lane in proposal.lanes]
        self.assertEqual(len(names), len(set(names)))

    # -- tickets with nothing to enforce ----------------------------------------

    def test_a_ticket_with_no_paths_is_never_given_out(self):
        issues = feature_backlog() + [ticket(9, "Improve checkout speed", paths=())]
        proposal = self.divide(issues, feature_files())
        self.assertNotIn("9", proposal.placed_refs)
        self.assertIn("9", [b.ref for b in proposal.needs_paths])

    def test_a_suggestion_is_marked_as_a_suggestion(self):
        issues = feature_backlog() + [ticket(9, "Improve checkout speed", paths=())]
        proposal = self.divide(issues, feature_files())
        suggested = next(b for b in proposal.needs_paths if b.ref == "9")
        self.assertIs(suggested.source, PathSource.PROPOSED)
        self.assertTrue(suggested.paths)

    def test_nothing_is_invented_when_there_is_nothing_to_go_on(self):
        proposal = self.divide([ticket(9, "Make it faster", paths=())])
        self.assertEqual(proposal.lanes, ())
        self.assertEqual(proposal.needs_paths, ())
        self.assertEqual([b.ref for b in proposal.unplaced], ["9"])

    # -- the fallback -----------------------------------------------------------

    def test_a_backlog_with_no_paths_falls_back_to_the_code(self):
        issues = [ticket(1, "Fix the catalog", paths=(), lane="catalog"),
                  ticket(2, "Something else", paths=())]
        proposal = self.divide(issues, feature_files())
        self.assertTrue(proposal.lanes)
        self.assertTrue(all(l.source is PathSource.CODE for l in proposal.lanes))
        self.assertIn("catalog", [l.name for l in proposal.lanes])
        # The lanes come from the code, so no ticket is inside one of them.
        self.assertEqual(proposal.placed_refs, ())
        self.assertIn("1", [b.ref for b in proposal.needs_paths])


if __name__ == "__main__":
    unittest.main()
