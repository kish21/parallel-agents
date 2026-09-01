"""Do any two entries touch the same files?

The one thing here a person cannot check by eye, so it is the one thing that must be
exactly right. Both halves are tested: the answer proved by files that exist, and the
answer about files that do not exist yet — because two entries claiming the same
directory collide the moment somebody writes the first file in it, and finding that out
then rather than now is the failure the check exists to prevent.
"""

import unittest

from lanekeeper.config import DivideConfig, DivideThresholds
from lanekeeper.divide import collision
from lanekeeper.divide.models import PathSource, Placement, ProposedLane


def lane(name, *paths):
    return ProposedLane(name=name, paths=tuple(paths), tickets=(),
                        source=PathSource.TICKET, placement=Placement.GROUPED)


class CollisionTestCase(unittest.TestCase):
    def setUp(self):
        self.settings = DivideConfig()

    def test_two_entries_over_one_real_file_collide_with_that_file_as_evidence(self):
        files = ["backend/app/main.py", "backend/app/cart.py"]
        found = collision.report([lane("a", "backend/**"), lane("b", "backend/app/main.py")],
                                 files, self.settings)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].kind, "files")
        self.assertIn("backend/app/main.py", found[0].example_files)

    def test_disjoint_entries_do_not_collide(self):
        files = ["backend/a.py", "frontend/b.tsx"]
        found = collision.report([lane("a", "backend/**"), lane("b", "frontend/**")],
                                 files, self.settings)
        self.assertEqual(found, [])

    def test_an_overlap_over_files_that_do_not_exist_yet_is_still_reported(self):
        found = collision.report(
            [lane("a", "backend/app/domains/cart/**"),
             lane("b", "backend/app/domains/cart/**")],
            files=["README.md"], settings=self.settings)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].kind, "patterns-only")
        self.assertEqual(found[0].example_files, ())

    def test_proved_collisions_are_reported_before_theoretical_ones(self):
        files = ["backend/app/main.py"]
        lanes = [lane("theory", "future/**"), lane("t2", "future/**"),
                 lane("real", "backend/**"), lane("r2", "backend/app/main.py")]
        found = collision.report(lanes, files, self.settings)
        self.assertEqual(found[0].kind, "files")

    def test_the_report_is_capped(self):
        settings = DivideConfig(thresholds=DivideThresholds(overlap_report_limit=2))
        lanes = [lane(f"l{i}", "shared/**") for i in range(6)]
        self.assertEqual(len(collision.report(lanes, ["shared/x.py"], settings)), 2)

    def test_files_nobody_claims_are_named(self):
        files = ["backend/a.py", "docs/readme.md"]
        loose = collision.unclaimed([lane("a", "backend/**")], files, limit=5)
        self.assertEqual(loose, ("docs/readme.md",))

    # -- the pattern intersection itself ----------------------------------------

    def test_patterns_intersect(self):
        yes = [
            ("backend/**", "backend/app/main.py"),
            ("backend/app/**", "**/main.py"),
            ("frontend/src/*.ts", "frontend/src/index.ts"),
            ("a/**/c.py", "a/b/c.py"),
            ("**", "anything/at/all.py"),
            ("a/*/c.py", "a/b/c.py"),
        ]
        for left, right in yes:
            self.assertTrue(collision.patterns_intersect(left, right), f"{left} vs {right}")
            self.assertTrue(collision.patterns_intersect(right, left), f"{right} vs {left}")

    def test_patterns_that_cannot_share_a_path(self):
        no = [
            ("backend/**", "frontend/**"),
            ("a/b/c.py", "a/b/d.py"),
            ("frontend/src/*.ts", "frontend/src/nested/index.ts"),
            ("a/b/**", "a/c/**"),
        ]
        for left, right in no:
            self.assertFalse(collision.patterns_intersect(left, right), f"{left} vs {right}")
            self.assertFalse(collision.patterns_intersect(right, left), f"{right} vs {left}")

    def test_an_answered_overlap_does_not_hide_an_unanswered_one(self):
        """A zone or a carve-out answers the pair it covers, and only that pair.

        Blanking every structural finding because a zone exists somewhere would let one
        answered overlap conceal all the ones nobody has looked at.
        """
        lanes = [lane("a", "shared/spine.py"), lane("b", "shared/**"),
                 lane("c", "future/**"), lane("d", "future/**")]
        zones = ("shared/spine.py",)
        found = collision.report(lanes, files=[], settings=self.settings,
                                 shared_paths=zones)
        pairs = {(o.left, o.right) for o in found}
        self.assertNotIn(("a", "b"), pairs)
        self.assertIn(("c", "d"), pairs)

    def test_a_carve_out_answers_only_what_it_carves_out(self):
        lanes = [lane("wide", "backend/**"), lane("narrow", "backend/catalog/**")]
        carved = [ProposedLane(name="wide", paths=("backend/**",),
                               deny=("backend/catalog/**",)), lanes[1]]
        self.assertTrue(collision.report(lanes, [], self.settings))
        self.assertFalse(collision.report(carved, [], self.settings))

    def test_a_real_collision_is_never_suppressed_by_a_carve_out_elsewhere(self):
        """Only the weaker structural finding may be answered this way."""
        lanes = [ProposedLane(name="a", paths=("backend/**",),
                              deny=("backend/elsewhere/**",)),
                 lane("b", "backend/app/main.py")]
        found = collision.report(lanes, ["backend/app/main.py"], self.settings)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].kind, "files")

    def test_it_reports_the_overlap_and_judges_nothing_about_it(self):
        """#39 keeps the hard question. This one only ever answers yes or no."""
        found = collision.report([lane("a", "shared/spine.py"), lane("b", "shared/**")],
                                 ["shared/spine.py"], self.settings)
        self.assertEqual(len(found), 1)
        self.assertEqual(set(vars(found[0])) & {"verdict", "recommendation", "advice"},
                         set())


if __name__ == "__main__":
    unittest.main()
