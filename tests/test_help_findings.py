"""#64: `lanekeeper --help` did not tell a new user what to run first.

Twenty-two commands in registration order, `init` fifth and `spawn` ninth, and a
mistyped subcommand answered with all twenty-two rather than the obvious one.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402


class TestTheFrontDoor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_help_names_spawn_ticket_as_the_usual_start_and_links_the_guide(self):
        res = run_cli(["--help"], cwd=self.tmp)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("Most people need one command", res.stdout)
        self.assertIn("lanekeeper spawn --ticket", res.stdout)
        self.assertIn("lanekeeper install-gate", res.stdout)
        self.assertIn("docs/getting-started.md", res.stdout)
        self.assertLess(res.stdout.index("spawn --ticket"), res.stdout.index("Without a tracker"))

    def test_help_says_what_init_is_for_and_what_it_costs(self):
        res = run_cli(["--help"], cwd=self.tmp)
        self.assertIn("Without a tracker:     init", res.stdout)
        self.assertIn("technology layers", res.stdout)

    def test_the_usage_line_does_not_dump_every_command(self):
        res = run_cli(["--help"], cwd=self.tmp)
        first = res.stdout.splitlines()[0]
        self.assertIn("<command>", first)
        self.assertNotIn("{start,board", first)

    def test_a_mistyped_command_suggests_the_nearest_real_one(self):
        res = run_cli(["spwan"], cwd=self.tmp)
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("'spwan' is not a lanekeeper command", res.stderr)
        self.assertIn("most similar command is 'spawn'", res.stderr)
        self.assertNotIn("choose from", res.stderr)

    def test_nothing_close_keeps_the_full_list(self):
        res = run_cli(["zzzzzz"], cwd=self.tmp)
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("choose from", res.stderr)

    def test_no_command_at_all_prints_the_help(self):
        res = run_cli([], cwd=self.tmp)
        self.assertEqual(res.returncode, 1)
        self.assertIn("Most people need one command", res.stdout)


if __name__ == "__main__":
    unittest.main()
