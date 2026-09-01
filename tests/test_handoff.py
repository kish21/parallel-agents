"""`start` hands off to product-playbook instead of telling the user to.

Claude Code is a fake launcher that records what it was asked to open. What is tested
is the decision around it: when `start` opens it, when it only prints, and that it
looks at the tickets again afterwards.
"""

import argparse
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper import cli, handoff
from lanekeeper.config import PlaybookConfig

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _intake_fakes import FakeTracker, issue  # noqa: E402


@contextlib.contextmanager
def in_dir(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class TestTheDecision(unittest.TestCase):
    def test_off_in_configuration_means_off(self):
        self.assertFalse(handoff.can_hand_off(PlaybookConfig(auto=False), interactive=True))

    def test_no_terminal_means_off(self):
        self.assertFalse(handoff.can_hand_off(PlaybookConfig(), interactive=False))
        self.assertTrue(handoff.can_hand_off(PlaybookConfig(), interactive=True))

    def test_a_missing_claude_is_named_with_the_steps(self):
        with self.assertRaises(handoff.HandoffError) as ctx:
            handoff.command_for(PlaybookConfig(command="no-such-claude-xyz"))
        self.assertIn("no-such-claude-xyz", str(ctx.exception))
        self.assertIn("/vision", str(ctx.exception))

    def test_the_first_step_is_the_opening_prompt(self):
        argv = handoff.command_for(PlaybookConfig(command=sys.executable, steps=["/vision", "/scope"]))
        self.assertEqual(argv[-1], "/vision")

    def test_run_playbook_uses_the_launcher(self):
        seen = {}

        def launcher(argv, cwd):
            seen["argv"], seen["cwd"] = list(argv), cwd
            return 0

        code = handoff.run_playbook(PlaybookConfig(command=sys.executable), Path("."), launcher)
        self.assertEqual(code, 0)
        self.assertEqual(seen["argv"][-1], "/vision")

    def test_describe_names_the_remaining_steps(self):
        text = handoff.describe(PlaybookConfig())
        self.assertIn("/vision", text)
        self.assertIn("/scope", text)
        self.assertIn("/plan", text)


class TestStartHandsOff(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.launches = []
        self.original_run = handoff.run_playbook
        self.original_tracker = cli.get_tracker

    def tearDown(self):
        handoff.run_playbook = self.original_run
        cli.get_tracker = self.original_tracker

    def _start(self, tracker, extra=None, launch_code=0):
        def fake_run(settings, root, launcher=None):
            self.launches.append((settings.command, root))
            return launch_code
        handoff.run_playbook = fake_run
        cli.get_tracker = lambda settings, root, runner=None: tracker
        args = argparse.Namespace(take_as_is=False, fresh=True, redraft=False,
                                  no_handoff=False, handoff=False)
        for k, v in (extra or {}).items():
            setattr(args, k, v)
        out = io.StringIO()
        with in_dir(self.root), contextlib.redirect_stdout(out):
            code = cli.cmd_start(args)
        return code, out.getvalue()

    def test_nothing_written_down_opens_claude_and_looks_again(self):
        tracker = FakeTracker(issues=[])
        code, out = self._start(tracker, extra={"handoff": True})
        self.assertEqual(len(self.launches), 1)
        self.assertEqual(self.launches[0][0], "claude")
        self.assertEqual(tracker.list_calls, 2, "the tickets are read again after the hand-off")
        self.assertIn("Back from Claude Code", out)
        self.assertNotEqual(code, 0, "still nothing written down, so start still stops")

    def test_without_a_terminal_it_only_prints_the_steps(self):
        tracker = FakeTracker(issues=[])
        code, out = self._start(tracker)
        self.assertEqual(self.launches, [])
        self.assertEqual(tracker.list_calls, 1)
        self.assertIn("/vision", out)
        self.assertEqual(code, 1)

    def test_no_handoff_flag_wins_over_a_terminal(self):
        tracker = FakeTracker(issues=[])
        code, out = self._start(tracker, extra={"handoff": True, "no_handoff": True})
        self.assertEqual(self.launches, [])
        self.assertEqual(code, 1)

    def test_a_backlog_that_exists_is_never_handed_off(self):
        tracker = FakeTracker(issues=[issue(1, "Add cart"), issue(2, "Add search")])
        self._start(tracker, extra={"handoff": True, "take_as_is": True})
        self.assertEqual(self.launches, [])

    def test_a_failed_claude_session_stops_without_a_second_read(self):
        tracker = FakeTracker(issues=[])
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, _ = self._start(tracker, extra={"handoff": True}, launch_code=3)
        self.assertEqual(code, 1)
        self.assertEqual(tracker.list_calls, 1)
        self.assertIn("exited with 3", err.getvalue())


if __name__ == "__main__":
    unittest.main()
