"""`lanekeeper divide` end to end, against #38's definition of done.

The tracker is injected at the command's own seam (`cli.get_tracker`), so these run the
real command — configuration loading, both steps, the draft file, the exit code —
without a network, a GitHub account, or `gh` being installed. The repository is a real
one with real files in it, because the division reads what git says is there.
"""

import argparse
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from lanekeeper import cli, paths
from lanekeeper.config import Config, save_config

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _divide_fixtures import (  # noqa: E402
    feature_backlog,
    feature_files,
    layer_files,
    ticket,
)
from _intake_fakes import FakeTracker  # noqa: E402


@contextlib.contextmanager
def in_dir(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class DivideCommandTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init"], cwd=self.root, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@example.test"],
                       cwd=self.root, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"],
                       cwd=self.root, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # -- helpers ----------------------------------------------------------------

    def commit(self, files):
        for name in files:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "files"], cwd=self.root,
                       capture_output=True)

    def run_divide(self, issues, confirm=False, command="divide", fresh=True,
                   force=False, redraft=False):
        args = argparse.Namespace(take_as_is=True, fresh=fresh, confirm=confirm,
                                  force=force, redraft=redraft)
        original = cli.get_tracker
        cli.get_tracker = lambda settings, root, runner=None: FakeTracker(issues)
        buffer = io.StringIO()
        try:
            with in_dir(self.root), contextlib.redirect_stdout(buffer):
                run = cli.cmd_divide if command == "divide" else cli.cmd_start
                code = run(args)
        finally:
            cli.get_tracker = original
        return code, buffer.getvalue()

    def draft_text(self):
        return (self.root / paths.home_dirname() / "start" / "lanes.draft.yaml").read_text(
            encoding="utf-8")

    def write_draft(self, text):
        path = self.root / paths.home_dirname() / "start" / "lanes.draft.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    # -- the definition of done -------------------------------------------------

    def test_a_feature_organised_project_divides_into_features(self):
        self.commit(feature_files())
        code, out = self.run_divide(feature_backlog())
        self.assertEqual(code, 0, out)
        self.assertIn("catalog", out)
        self.assertIn("checkout", out)
        for layer in ("backend\n", "frontend\n"):
            self.assertNotIn(f"   {layer}", out)

    def test_a_layer_only_project_is_not_split_by_layer(self):
        """#23: the detection that proposed backend/frontend is not the default here."""
        self.commit(layer_files())
        issues = [ticket(1, "Tidy the formatter", ["frontend/src/utils/format.ts"])]
        code, out = self.run_divide(issues)
        self.assertEqual(code, 0, out)
        self.assertNotIn("   backend\n", out)
        self.assertNotIn("   frontend\n", out)

    def test_a_backlog_that_does_not_group_is_a_pick_list_not_a_stop(self):
        self.commit(["ops/logrotate.py", "billing/invoice.py", "importer/run.py"])
        issues = [
            ticket(1, "Rotate the log files", ["ops/logrotate.py"]),
            ticket(2, "Fix the invoice total", ["billing/invoice.py"]),
            ticket(3, "Speed up the importer", ["importer/run.py"]),
        ]
        code, out = self.run_divide(issues)
        self.assertEqual(code, 0, out)
        self.assertNotIn("🛑", out)
        for name in ("logrotate", "invoice", "importer"):
            self.assertIn(name, out)

    def test_the_proposal_is_written_to_a_draft_and_nothing_else(self):
        self.commit(feature_files())
        self.run_divide(feature_backlog())
        self.assertTrue(self.draft_text())
        self.assertFalse((self.root / "lanes.yaml").exists())

    def test_a_ticket_with_no_files_is_never_handed_over(self):
        self.commit(feature_files())
        issues = feature_backlog() + [ticket(9, "Improve checkout speed", paths=())]
        code, out = self.run_divide(issues)
        self.assertEqual(code, 0, out)
        self.assertIn("#9", out)
        data = yaml.safe_load(self.draft_text())
        listed = [ref for body in data["lanes"].values()
                  for ref in (body or {}).get("tickets", [])]
        self.assertNotIn("9", listed)

    def test_a_wider_boundary_is_offered_but_never_applied(self):
        """A boundary of exactly today's files leaves no room for tomorrow's.

        The wider area is offered as a comment so the user can accept it. Applying it
        would hand an agent more than any ticket asked for.
        """
        self.commit(feature_files())
        self.run_divide(feature_backlog())
        text = self.draft_text()
        self.assertIn("# - backend/app/domains/catalog/**", text)
        data = yaml.safe_load(text)
        self.assertNotIn("backend/app/domains/catalog/**",
                         data["lanes"]["catalog"]["allow"])

    def test_running_again_does_not_throw_away_the_users_edits(self):
        """`start` runs this step every time. The draft is the file the user answers
        in, so overwriting it would destroy the answer they came back to give."""
        self.commit(feature_files())
        self.run_divide(feature_backlog())
        self.write_draft("version: 1\nlanes:\n  mine:\n    allow:\n      - backend/**\n")
        code, out = self.run_divide(feature_backlog(), fresh=False)
        self.assertEqual(code, 0, out)
        self.assertIn("mine", self.draft_text())
        self.assertIn("left it exactly as it is", " ".join(out.split()))

    def test_asking_for_a_new_proposal_replaces_the_draft(self):
        """And it takes its own flag to do it.

        `--fresh` means "ignore what step 1 decided"; re-using it here would make a flag
        about a recorded judgement quietly delete an afternoon of editing.
        """
        self.commit(feature_files())
        self.run_divide(feature_backlog())
        self.write_draft("version: 1\nlanes:\n  mine:\n    allow:\n      - backend/**\n")
        self.run_divide(feature_backlog(), fresh=True)
        self.assertIn("mine", self.draft_text())
        self.run_divide(feature_backlog(), redraft=True)
        self.assertNotIn("mine", self.draft_text())

    def test_a_hand_written_lane_file_is_not_replaced_without_force(self):
        self.commit(feature_files())
        (self.root / "lanes.yaml").write_text("version: 1\n# written by hand\n",
                                              encoding="utf-8")
        self.run_divide(feature_backlog())
        code, out = self.run_divide(feature_backlog(), confirm=True)
        self.assertEqual(code, 1)
        self.assertIn("--force", out)
        self.assertIn("written by hand",
                      (self.root / "lanes.yaml").read_text(encoding="utf-8"))
        code, _ = self.run_divide(feature_backlog(), confirm=True, force=True)
        self.assertEqual(code, 0)
        self.assertNotIn("written by hand",
                         (self.root / "lanes.yaml").read_text(encoding="utf-8"))

    def test_a_carve_out_the_user_wrote_survives_and_answers_the_overlap(self):
        """The documented fix for a reported clash must not be dropped on the way in."""
        self.commit(feature_files())
        self.write_draft(
            "version: 1\n"
            "unowned: new-modules\n"
            "lanes:\n"
            "  wide:\n    allow:\n      - backend/**\n"
            "    deny:\n      - backend/app/domains/catalog/**\n"
            "  narrow:\n    allow:\n      - backend/app/domains/catalog/**\n")
        code, out = self.run_divide(feature_backlog(), confirm=True)
        self.assertEqual(code, 0, out)
        data = yaml.safe_load((self.root / "lanes.yaml").read_text(encoding="utf-8"))
        self.assertEqual(data["unowned"], "new-modules")
        self.assertEqual(data["lanes"]["wide"]["deny"],
                         ["backend/app/domains/catalog/**"])

    def test_a_line_that_was_not_read_as_a_file_is_reported(self):
        """A boundary quietly narrower than the one the filer wrote is still wrong."""
        self.commit(feature_files())
        from lanekeeper.trackers.base import TrackedIssue
        issue = TrackedIssue(
            ref="7", title="Tidy the catalog",
            body=("### Allowed File Paths\n\n"
                  "backend/app/domains/catalog/service.py\n"
                  "not sure about the front end yet\n"))
        code, out = self.run_divide([issue])
        self.assertEqual(code, 0, out)
        self.assertIn("not sure about the front end", " ".join(out.split()))

    def test_a_backlog_with_no_files_is_matched_to_the_project_not_duplicated(self):
        """A suggestion that copies an entry's own files is a clash by construction."""
        self.commit(feature_files())
        from _divide_fixtures import ticket as make
        issues = [make(1, "Fix the catalog page", paths=(), lane="catalog"),
                  make(2, "Fix the checkout", paths=(), lane="checkout")]
        code, out = self.run_divide(issues)
        self.assertEqual(code, 0, out)
        self.assertIn("Looks like part of", " ".join(out.split()))
        text = self.draft_text()
        self.assertNotIn("work-1:", text.replace("# ", ""))

    def test_confirming_writes_the_file_the_user_edited(self):
        self.commit(feature_files())
        self.run_divide(feature_backlog())
        code, out = self.run_divide(feature_backlog(), confirm=True)
        self.assertEqual(code, 0, out)
        data = yaml.safe_load((self.root / "lanes.yaml").read_text(encoding="utf-8"))
        self.assertIn("catalog", data["lanes"])
        self.assertIn("backend/app/domains/catalog/service.py",
                      data["lanes"]["catalog"]["allow"])

    def test_confirming_an_entry_with_no_files_writes_nothing(self):
        self.commit(feature_files())
        self.write_draft("version: 1\nlanes:\n  empty:\n    allow: []\n")
        code, out = self.run_divide(feature_backlog(), confirm=True)
        self.assertEqual(code, 1)
        self.assertIn("empty", out)
        self.assertFalse((self.root / "lanes.yaml").exists())

    def test_a_collision_is_reported_before_anything_is_written(self):
        self.commit(feature_files())
        self.write_draft(
            "version: 1\nlanes:\n"
            "  one:\n    allow:\n      - backend/**\n"
            "  two:\n    allow:\n      - backend/app/domains/catalog/service.py\n")
        code, out = self.run_divide(feature_backlog(), confirm=True)
        self.assertEqual(code, 1)
        self.assertIn("one", out)
        self.assertIn("two", out)
        self.assertFalse((self.root / "lanes.yaml").exists())

    def test_confirming_before_proposing_says_what_to_run(self):
        self.commit(feature_files())
        code, out = self.run_divide(feature_backlog(), confirm=True)
        self.assertEqual(code, 1)
        self.assertIn("lanekeeper divide", out)

    def test_the_same_backlog_produces_the_same_draft_every_time(self):
        self.commit(feature_files())
        self.run_divide(feature_backlog())
        first = self.draft_text()
        self.run_divide(feature_backlog())
        self.assertEqual(first, self.draft_text())

    def test_start_runs_both_steps_and_says_what_is_not_built(self):
        self.commit(feature_files())
        code, out = self.run_divide(feature_backlog(), command="start")
        self.assertEqual(code, 0, out)
        self.assertIn("catalog", out)
        self.assertIn("not built yet", out)

    def test_the_division_does_not_read_the_tracker_twice(self):
        """Step 2 is handed step 1's tickets. Two reads of a live backlog can
        disagree, and half a command answering about a different list is worse than
        no answer."""
        self.commit(feature_files())
        tracker = FakeTracker(feature_backlog())
        args = argparse.Namespace(take_as_is=True, fresh=True, confirm=False)
        original = cli.get_tracker
        cli.get_tracker = lambda settings, root, runner=None: tracker
        try:
            with in_dir(self.root), contextlib.redirect_stdout(io.StringIO()):
                cli.cmd_divide(args)
        finally:
            cli.get_tracker = original
        self.assertEqual(tracker.list_calls, 1)

    def test_an_existing_project_configuration_is_not_touched(self):
        self.commit(feature_files())
        config = Config.default(project_name="existing")
        with in_dir(self.root):
            save_config(config, self.root)
        before = (self.root / paths.home_dirname() / "config.yaml").read_text(
            encoding="utf-8")
        self.run_divide(feature_backlog())
        after = (self.root / paths.home_dirname() / "config.yaml").read_text(
            encoding="utf-8")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
