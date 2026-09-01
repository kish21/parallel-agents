"""The draft, and what confirming it does.

The rule these guard: **confirming re-checks what the user wrote, not what lanekeeper
proposed.** Checking the proposal and then writing the edit would make the check
decoration, and the two things it must catch — an entry with no files, and two entries
over the same files — are exactly the ones an edit introduces.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from lanekeeper.config import DivideConfig
from lanekeeper.divide import draft
from lanekeeper.divide.models import (
    DivisionProposal,
    PathSource,
    Placement,
    ProposedLane,
    TicketBoundary,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))


def lane(name, *paths, tickets=()):
    return ProposedLane(name=name, paths=tuple(paths), tickets=tuple(tickets),
                        source=PathSource.TICKET, placement=Placement.GROUPED,
                        why="because")


class DraftTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.settings = DivideConfig()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def proposal(self, **kwargs):
        base = dict(lanes=(lane("catalog", "backend/catalog/**", tickets=("1", "2")),),
                    ticket_count=2)
        base.update(kwargs)
        return DivisionProposal(**base)

    # -- writing ----------------------------------------------------------------

    def save(self, proposal=None, **kwargs):
        return draft.save(proposal or self.proposal(), self.root, self.settings,
                          **kwargs)

    def test_the_draft_is_valid_yaml_in_the_documented_schema(self):
        path, _ = self.save()
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertIn("catalog", data["lanes"])
        self.assertEqual(data["lanes"]["catalog"]["allow"], ["backend/catalog/**"])

    def test_the_draft_is_not_the_real_file(self):
        self.save()
        self.assertFalse((self.root / self.settings.lane_file).exists())

    def test_a_ticket_with_no_files_is_present_but_switched_off(self):
        proposal = self.proposal(needs_paths=(
            TicketBoundary(ref="9", title="Speed up checkout",
                           paths=("backend/checkout/**",), source=PathSource.PROPOSED),))
        path, _ = self.save(proposal)
        text = path.read_text(encoding="utf-8")
        self.assertIn("Speed up checkout", text)
        data = yaml.safe_load(text)
        # Present as text for the user to switch on; absent from the actual entries,
        # because nobody has confirmed those paths.
        self.assertNotIn("work-9", data["lanes"])

    def test_paths_with_awkward_characters_survive_the_round_trip(self):
        proposal = self.proposal(lanes=(lane("odd", "src/**/*.py", "a: b/#c.md"),))
        path, _ = self.save(proposal)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(data["lanes"]["odd"]["allow"], ["src/**/*.py", "a: b/#c.md"])

    # -- reading it back --------------------------------------------------------

    def test_confirming_before_proposing_says_what_to_run(self):
        lanes, _, problem = draft.load(self.root, self.settings)
        self.assertEqual(lanes, [])
        self.assertEqual(problem.kind, "unreadable")
        self.assertIn("lanekeeper divide", problem.detail)

    def test_an_unreadable_draft_is_reported_not_raised(self):
        path = draft.draft_path(self.root, self.settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("lanes: [this: is: not: right\n", encoding="utf-8")
        _, _, problem = draft.load(self.root, self.settings)
        self.assertEqual(problem.kind, "unreadable")

    def test_an_edited_draft_is_read_as_the_user_wrote_it(self):
        self.save()
        path = draft.draft_path(self.root, self.settings)
        path.write_text(
            "version: 1\nlanes:\n  renamed:\n    tickets: ['1']\n"
            "    allow:\n      - backend/renamed/**\n", encoding="utf-8")
        lanes, _, problem = draft.load(self.root, self.settings)
        self.assertIsNone(problem)
        self.assertEqual([l.name for l in lanes], ["renamed"])
        self.assertEqual(lanes[0].paths, ("backend/renamed/**",))

    # -- validating what the user wrote -----------------------------------------

    def test_an_entry_with_no_files_is_refused_by_name(self):
        report = draft.validate([lane("empty")], ["backend/a.py"], self.settings)
        self.assertFalse(report.ok)
        self.assertEqual(report.problems[0].kind, "no-paths")
        self.assertIn("empty", report.problems[0].detail)

    def test_two_entries_over_the_same_files_are_refused(self):
        report = draft.validate([lane("a", "backend/**"), lane("b", "backend/a.py")],
                                ["backend/a.py"], self.settings)
        self.assertFalse(report.ok)
        self.assertTrue(report.overlaps)

    def test_the_same_ticket_in_two_entries_is_refused(self):
        report = draft.validate(
            [lane("a", "x/**", tickets=("7",)), lane("b", "y/**", tickets=("7",))],
            ["x/a.py", "y/b.py"], self.settings)
        self.assertFalse(report.ok)
        self.assertEqual(report.problems[0].kind, "duplicate-ticket")

    def test_a_blank_line_in_the_list_is_not_a_path(self):
        """It loads as `None`, and `str(None)` is the very plausible path `"None"`.

        Which would satisfy the check that an entry has a boundary while giving it one
        that matches nothing at all.
        """
        path = draft.draft_path(self.root, self.settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("version: 1\nlanes:\n  half:\n    allow:\n      -\n",
                        encoding="utf-8")
        lanes, _, problem = draft.load(self.root, self.settings)
        self.assertIsNone(problem)
        self.assertEqual(lanes[0].paths, ())
        report = draft.validate(lanes, ["backend/a.py"], self.settings)
        self.assertFalse(report.ok)
        self.assertEqual(report.problems[0].kind, "no-paths")

    def test_the_switched_off_block_is_valid_yaml_once_switched_on(self):
        """The file tells the user to delete the `# `. What is left has to load.

        Two ways it did not: a blank list item, which loads as an entry with a path of
        `None`; and an unquoted title, which a colon or a `#` in it makes unparseable.
        """
        proposal = self.proposal(unplaced=(
            TicketBoundary(ref="9", title="Fix this: it is # broken"),))
        path, _ = self.save(proposal)
        text = path.read_text(encoding="utf-8")

        block = []
        for line in text.splitlines():
            if line.startswith("#   work-9:"):
                block.append(line[2:])
            elif block and line.startswith("#     "):
                block.append(line[2:])
            elif block:
                break
        self.assertTrue(block, text)
        self.assertNotIn("    - ", "\n".join(block))

        entry = yaml.safe_load("lanes:\n" + "\n".join(block))
        self.assertEqual(entry["lanes"]["work-9"]["description"],
                         "Fix this: it is # broken")
        self.assertFalse(entry["lanes"]["work-9"].get("allow"))

    def test_an_empty_draft_is_refused(self):
        report = draft.validate([], [], self.settings)
        self.assertFalse(report.ok)
        self.assertEqual(report.problems[0].kind, "no-lanes")

    # -- writing the real file ---------------------------------------------------

    def test_the_confirmed_file_loads_back_in_the_documented_schema(self):
        document = {"version": 1, "lanes": {"catalog": {
            "description": "d", "owner": "senior", "tickets": ["1"],
            "allow": ["backend/catalog/**"]}}}
        path, written = draft.write_lane_file(document, self.root, self.settings)
        self.assertTrue(written)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["lanes"]["catalog"]["allow"], ["backend/catalog/**"])
        self.assertEqual(data["lanes"]["catalog"]["owner"], "senior")
        # `tickets` is not part of the documented lane-file schema and must not appear.
        self.assertNotIn("tickets", data["lanes"]["catalog"])

    def test_a_single_ticket_entry_is_a_complete_confirmed_entry(self):
        document = {"version": 1, "lanes": {"logs": {
            "tickets": ["4"], "allow": ["ops/logrotate.py"]}}}
        path, _ = draft.write_lane_file(document, self.root, self.settings)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(data["lanes"]["logs"]["allow"], ["ops/logrotate.py"])

    def test_everything_the_user_wrote_survives_confirming(self):
        """`deny`, `shared` and `unowned` are the documented ways to answer an overlap.

        Re-rendering the file from the entries step 2 understood would drop the fix and
        report the same collision again on the next run.
        """
        document = {
            "version": 1,
            "unowned": "new-modules",
            "defaults": {"harness": "claude-code"},
            "lanes": {"catalog": {"owner": "senior", "harness": "aider",
                                  "allow": ["backend/catalog/**"],
                                  "deny": ["backend/catalog/legacy/**"],
                                  "tickets": ["1"]}},
            "shared": {"spine": {"steward": "catalog", "mode": "escalate",
                                 "paths": ["backend/main.py"]}},
        }
        path, _ = draft.write_lane_file(document, self.root, self.settings)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(data["unowned"], "new-modules")
        self.assertEqual(data["shared"]["spine"]["paths"], ["backend/main.py"])
        self.assertEqual(data["lanes"]["catalog"]["deny"],
                         ["backend/catalog/legacy/**"])
        self.assertEqual(data["lanes"]["catalog"]["harness"], "aider")
        self.assertNotIn("tickets", data["lanes"]["catalog"])

    def test_an_existing_file_is_not_replaced_without_being_asked(self):
        (self.root / self.settings.lane_file).write_text(
            "version: 1\n# written by hand\n", encoding="utf-8")
        path, written = draft.write_lane_file({"lanes": {}}, self.root, self.settings)
        self.assertFalse(written)
        self.assertIn("written by hand", path.read_text(encoding="utf-8"))
        _, forced = draft.write_lane_file({"lanes": {}}, self.root, self.settings,
                                          overwrite=True)
        self.assertTrue(forced)

    def test_a_draft_the_user_has_edited_is_never_overwritten(self):
        self.save()
        path = draft.draft_path(self.root, self.settings)
        path.write_text("version: 1\nlanes:\n  mine:\n    allow: [a/**]\n",
                        encoding="utf-8")
        _, written = self.save()
        self.assertFalse(written)
        self.assertIn("mine", path.read_text(encoding="utf-8"))
        _, rewritten = self.save(overwrite=True)
        self.assertTrue(rewritten)
        self.assertNotIn("mine", path.read_text(encoding="utf-8"))

    def test_a_carve_out_answers_a_reported_overlap(self):
        """`deny` beats `allow` within an entry, so the fix must clear the finding."""
        lanes = [lane("wide", "backend/**"), lane("narrow", "backend/catalog/x.py")]
        files = ["backend/catalog/x.py", "backend/other.py"]
        self.assertFalse(draft.validate(lanes, files, self.settings).ok)
        fixed = [ProposedLane(name="wide", paths=("backend/**",),
                              deny=("backend/catalog/**",)), lanes[1]]
        self.assertTrue(draft.validate(fixed, files, self.settings).ok)

    def test_a_shared_zone_is_not_a_collision(self):
        """A file in a zone belongs to the zone, however specifically it is claimed."""
        lanes = [lane("a", "backend/**"), lane("b", "backend/main.py")]
        files = ["backend/main.py"]
        document = {"shared": {"spine": {"paths": ["backend/main.py"]}}}
        self.assertFalse(draft.validate(lanes, files, self.settings).ok)
        self.assertTrue(draft.validate(lanes, files, self.settings,
                                       document=document).ok)


if __name__ == "__main__":
    unittest.main()
