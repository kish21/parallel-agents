"""`cleanup` must not report success it did not achieve, and ids must never be reused.

Observed on a real project: a dev server started inside a worktree held a file open, so
`git worktree remove` failed. Cleanup downgraded that to a warning, printed "Successfully
cleaned up", released the ports and deleted the state record — after which nothing named
the leftover directory, `doctor` reported a clean environment, and the next `spawn` drew
the same recycled id, resolved to the same path and failed. Recovery needed a manual
delete, because no command could see the problem any more.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper.state import StateManager

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import run_cli  # noqa: E402


class TestCleanupHonesty(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "tester@test.com"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.root, check=True, capture_output=True)
        run_cli(["init"], cwd=self.root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def _spawn(self, lane="platform"):
        res = run_cli(["spawn", "--lane", lane, "--seat", "SR1", "--task", "work"], cwd=self.root)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        return res

    def test_failed_removal_reports_failure_and_keeps_state(self):
        """Removal is made to fail by replacing the worktree with a plain directory,
        which `git worktree remove` refuses because it is not a registered working tree."""
        self._spawn()
        state = StateManager(self.root)
        agent = state.get_agent("agent-001")
        worktree = Path(agent.worktree_path)

        import shutil
        shutil.rmtree(worktree)
        worktree.mkdir(parents=True)
        (worktree / "leftover.txt").write_text("work\n", encoding="utf-8")

        res = run_cli(["cleanup", "agent-001", "--force"], cwd=self.root)
        output = res.stdout + res.stderr

        self.assertNotEqual(res.returncode, 0, output)
        self.assertNotIn("Successfully cleaned up", output)
        self.assertIsNotNone(StateManager(self.root).get_agent("agent-001"),
                             "state record must survive so doctor can still see the problem")
        self.assertTrue(StateManager(self.root).get_allocated_ports(),
                        "ports must not be returned to the pool while the worktree remains")

    def test_a_problem_cleanup_could_not_fix_stays_visible_to_doctor(self):
        self._spawn()
        agent = StateManager(self.root).get_agent("agent-001")
        worktree = Path(agent.worktree_path)
        import shutil
        shutil.rmtree(worktree)
        worktree.mkdir(parents=True)

        run_cli(["cleanup", "agent-001", "--force"], cwd=self.root)
        res = run_cli(["doctor"], cwd=self.root)

        self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("agent-001", res.stdout + res.stderr)

    def test_successful_cleanup_releases_everything(self):
        self._spawn()
        res = run_cli(["cleanup", "agent-001", "--force"], cwd=self.root)

        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("Successfully cleaned up", res.stdout)
        state = StateManager(self.root)
        self.assertIsNone(state.get_agent("agent-001"))
        self.assertEqual(state.get_allocated_ports(), {})
        self.assertFalse((self.root / ".lanekeeper" / "worktrees" / "agent-001").exists())

    def test_agent_ids_are_never_reused_after_cleanup(self):
        """A recycled id resolves to a path a previous agent may still occupy."""
        self._spawn()
        run_cli(["cleanup", "agent-001", "--force"], cwd=self.root)
        self._spawn()

        agents = StateManager(self.root).list_agents()
        self.assertEqual([a.id for a in agents], ["agent-002"])

    def test_spawn_refuses_a_path_that_is_already_occupied(self):
        occupied = self.root / ".lanekeeper" / "worktrees" / "agent-001"
        occupied.mkdir(parents=True)

        res = run_cli(["spawn", "--lane", "platform", "--seat", "SR1", "--task", "work"],
                      cwd=self.root)
        output = res.stdout + res.stderr

        self.assertNotEqual(res.returncode, 0, output)
        self.assertIn("already exists", output)
        self.assertEqual(StateManager(self.root).get_allocated_ports(), {},
                         "a refused spawn must not leak a port reservation")


if __name__ == "__main__":
    unittest.main()


class TestUnfinishedCleanupIsHeldNotReleased(unittest.TestCase):
    """An agent whose cleanup failed keeps its resources until a human intervenes.

    Releasing them would recreate the original leak from the other direction: the ledger
    would hand a port back while a process nobody recorded is still serving it.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "tester@test.com"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.root, check=True, capture_output=True)
        run_cli(["init"], cwd=self.root)
        run_cli(["spawn", "--lane", "platform", "--seat", "SR1", "--task", "work"], cwd=self.root)

        agent = StateManager(self.root).get_agent("agent-001")
        worktree = Path(agent.worktree_path)
        import shutil
        shutil.rmtree(worktree)
        worktree.mkdir(parents=True)
        run_cli(["cleanup", "agent-001", "--force"], cwd=self.root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_cleanup_failure_is_recorded_on_the_agent(self):
        agent = StateManager(self.root).get_agent("agent-001")
        self.assertTrue(agent.metadata.get("cleanup_failed"))

    def test_repair_does_not_release_the_retained_ports(self):
        before = StateManager(self.root).get_allocated_ports()
        run_cli(["repair"], cwd=self.root)

        self.assertEqual(StateManager(self.root).get_allocated_ports(), before)

    def test_doctor_reports_it_as_something_repair_cannot_fix(self):
        res = run_cli(["doctor"], cwd=self.root)
        output = res.stdout + res.stderr

        self.assertNotEqual(res.returncode, 0, output)
        self.assertIn("unfinished cleanup", output)
        self.assertIn("None can be fixed automatically", output)

    def test_cleanup_succeeds_once_the_obstruction_is_gone(self):
        agent = StateManager(self.root).get_agent("agent-001")
        import shutil
        shutil.rmtree(agent.worktree_path)

        res = run_cli(["cleanup", "agent-001", "--force"], cwd=self.root)

        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        state = StateManager(self.root)
        self.assertIsNone(state.get_agent("agent-001"))
        self.assertEqual(state.get_allocated_ports(), {})

    def test_cleanup_removes_a_directory_git_has_already_disowned(self):
        """`git worktree prune` drops the record as soon as the path is unreachable, so a
        retried cleanup meets a plain directory that `git worktree remove` refuses. It
        must still be removable, or the failure is permanent."""
        run_cli(["repair"], cwd=self.root)  # prunes the registration
        agent = StateManager(self.root).get_agent("agent-001")
        self.assertTrue(Path(agent.worktree_path).exists())

        res = run_cli(["cleanup", "agent-001", "--force"], cwd=self.root)

        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse(Path(agent.worktree_path).exists())
        self.assertIsNone(StateManager(self.root).get_agent("agent-001"))
        self.assertEqual(StateManager(self.root).get_allocated_ports(), {})
