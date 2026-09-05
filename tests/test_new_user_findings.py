"""What a first run of the deep-test protocol found, away from the gate itself.

None of these is a hole in the boundary check. All three are ways the tool told a
first-time user something false or unhelpful at the moment they were paying most
attention: a traceback instead of an answer, advice that would undo their setup, and
a count that disagreed with the list beneath it.
"""

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper.config import Config, LaneConfig, save_config

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402


class AgentRepoTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for cmd in (["git", "init", "-q", "-b", "main", "."],
                    ["git", "config", "user.email", "t@t.c"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.root, check=True)
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("x", encoding="utf-8")
        (self.root / "other").mkdir()
        (self.root / "other" / "thing.py").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.root, check=True)
        cfg = Config.default("p")
        cfg.capability_gates = {}
        cfg.lanes = {"mine": LaneConfig("mine", allow=["src/**"])}
        save_config(cfg, self.root)
        res = run_cli(["spawn", "--lane", "mine", "--task", "work"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.worktree = self.root / ".lanekeeper" / "worktrees" / "agent-001"


class TestCleanupNeverCrashesWithoutAnAnswer(AgentRepoTestCase):
    """`cleanup` asked a question of a pipe and died on the answer it never got."""

    def dirty_the_worktree(self):
        (self.worktree / "src" / "new.py").write_text("unsaved work", encoding="utf-8")

    def test_no_terminal_aborts_and_names_the_flag(self):
        self.dirty_the_worktree()
        res = run_cli(["cleanup", "agent-001"], cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertNotIn("Traceback", res.stderr)
        self.assertNotIn("EOFError", res.stderr)
        self.assertIn("--force", res.stderr)
        self.assertTrue(self.worktree.exists(), "the work must survive an unanswered question")

    def test_force_still_removes_it(self):
        self.dirty_the_worktree()
        res = run_cli(["cleanup", "agent-001", "--force"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertFalse(self.worktree.exists())

    def test_a_worktree_holding_only_lanekeepers_own_files_is_not_dirty(self):
        """`.lane` and `.env` are lanekeeper's, not the agent's: cleanup must not ask."""
        res = run_cli(["cleanup", "agent-001"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertNotIn("uncommitted changes", res.stdout)
        self.assertFalse(self.worktree.exists())


class TestTheAdviceDoesNotUndoTheSetup(AgentRepoTestCase):
    """Both messages sent a ticket-derived policy through `init --force`, which
    replaces its lanes with technology layers — the opposite of what it wants."""

    def test_validate_does_not_recommend_init_force(self):
        (self.worktree / "other" / "thing.py").write_text("edited", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.worktree, check=True)
        subprocess.run(["git", "commit", "-qm", "stray"], cwd=self.worktree, check=True)
        res = run_cli(["validate", "agent-001"], cwd=self.root)
        self.assertNotEqual(res.returncode, 0, output_of(res))
        out = res.stdout + res.stderr
        self.assertIn("other/thing.py", out)
        self.assertNotIn("init --force", out)
        self.assertIn("lanes", out)

    def test_missing_seat_cards_say_how_without_rewriting_the_lanes(self):
        cfg = Config.default("p")
        cfg.lanes = {"mine": LaneConfig("mine", allow=["src/**"])}
        save_config(cfg, self.root)  # keeps the default capability gates
        shutil.rmtree(self.root / ".lanekeeper" / "capabilities", ignore_errors=True)
        res = run_cli(["spawn", "--lane", "mine", "--task", "t"], cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("capability_gates", res.stderr)
        self.assertIn("git checkout", res.stderr)
        self.assertIn("technology layers", res.stderr,
                      "if it names init --force at all, it must say what that costs")


class TestTheDiffCountMatchesTheList(AgentRepoTestCase):
    def test_bookkeeping_files_are_neither_listed_nor_counted(self):
        (self.worktree / "src" / "new.py").write_text("y", encoding="utf-8")
        res = run_cli(["diff", "agent-001"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        listed = [line for line in res.stdout.splitlines()
                  if "[LANE OK]" in line or "[OUT-OF-LANE]" in line]
        total = [line for line in res.stdout.splitlines() if "Total Modified Files:" in line]
        self.assertEqual(len(total), 1, res.stdout)
        self.assertEqual(int(total[0].split(":")[1].strip()), len(listed), res.stdout)
        self.assertNotIn(".lane", res.stdout)


if __name__ == "__main__":
    unittest.main()
