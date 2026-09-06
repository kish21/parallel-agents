"""Reading the worktree registry is a locked operation — the race CI caught.

`git worktree list --porcelain` walks `.git/worktrees/<id>/`, which is exactly what
another agent's cleanup deletes. `cmd_cleanup` took that reading *outside* the git lock
that guards the removal three lines below it, so on a ten-agent concurrent cleanup the
read landed mid-deletion and git exited 128:

    fatal: failed to read .git/worktrees/agent-007/commondir: No such file or directory

which reached the user as a traceback out of an ordinary `lanekeeper cleanup`.

The timing could not be reproduced on demand — eight suite runs and two targeted
git-level harnesses stayed clean on a fast machine — so these tests pin the property
that makes the crash impossible rather than the crash itself: every reader of
`.git/worktrees` runs under the same lock every writer of it takes. That is checkable
exactly, and it fails against the code CI caught.
"""

import argparse
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lanekeeper import paths
from lanekeeper.capabilities import default_cards, save_card
from lanekeeper.cli import cmd_cleanup, cmd_uninit
from lanekeeper.config import generate_default_config, save_config
from lanekeeper.doctor import Doctor
from lanekeeper.lock import StateLock
from lanekeeper.state import AgentState, StateManager
from lanekeeper.worktree import WorktreeManager


def _git_lock_depth(root: Path) -> int:
    """How deeply *this thread* holds the git lock. Zero means it does not."""
    lock = StateLock(paths.state_dir(root), lock_name=".git.lock")
    depth_map = getattr(StateLock._tls, "depth_map", {})
    return depth_map.get(str(lock.lock_file.resolve()), 0)


class RegistryReaderTestCase(unittest.TestCase):
    """A repository with one real agent worktree in it."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        for cmd in (["git", "init", "-q", "-b", "main", "."],
                    ["git", "config", "user.email", "t@t.c"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=str(self.root), check=True, capture_output=True)
        (self.root / "README.md").write_text("# r\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.root), check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=str(self.root), check=True)

        self.config = generate_default_config("Locked")
        save_config(self.config, self.root)
        for card in default_cards(sorted(self.config.lanes)):
            save_card(card, self.root)

        self.wt_mgr = WorktreeManager(self.root)
        self.state_mgr = StateManager(self.root)
        branch = self.wt_mgr.make_branch_name("agent-001", "a task")
        wt_path = self.wt_mgr.create_worktree(
            self.root / paths.worktrees_dir() / "agent-001", branch)
        self.state_mgr.save_agent(AgentState(
            id="agent-001", name="worker-1", seat="SR1",
            lane=sorted(self.config.lanes)[0], task="a task",
            branch=branch, worktree_path=str(wt_path), status="STOPPED"))

        self.depths = []
        original = WorktreeManager.list_worktrees

        def spy(inner_self):
            self.depths.append(_git_lock_depth(self.root))
            return original(inner_self)

        self.patcher = patch.object(WorktreeManager, "list_worktrees", spy)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def assertReadUnderTheLock(self):
        self.assertTrue(self.depths, "the registry was never read at all")
        self.assertTrue(
            all(d > 0 for d in self.depths),
            f"the worktree registry was read without the git lock (depths: {self.depths}); "
            f"a cleanup running elsewhere can delete .git/worktrees entries mid-read")


class TestCleanupReadsUnderTheLock(RegistryReaderTestCase):
    def test_it_holds_the_lock_while_listing(self):
        import os
        cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)
        cmd_cleanup(argparse.Namespace(agent="agent-001", force=True))
        self.assertReadUnderTheLock()


class TestDoctorReadsUnderTheLock(RegistryReaderTestCase):
    def test_it_holds_the_lock_while_listing(self):
        import os
        cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)
        Doctor().diagnose()
        self.assertReadUnderTheLock()


class TestUninitReadsUnderTheLock(RegistryReaderTestCase):
    def test_it_holds_the_lock_while_listing(self):
        import os
        cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)
        # Answers 'n': the plan is built either way, and the plan is what does the read.
        with patch("builtins.input", return_value="n"):
            cmd_uninit(argparse.Namespace(force=False))
        self.assertReadUnderTheLock()


class TestTheWriterSideIsLockedToo(RegistryReaderTestCase):
    """The review's first finding: `uninit` removes worktrees and prunes — the very
    mutations the readers are protected from — and did it with no lock at all, so the
    asserted invariant did not actually hold."""

    def test_uninit_removes_worktrees_under_the_lock(self):
        import os
        from lanekeeper import uninit as uninit_mod
        cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)

        depths = []
        original = WorktreeManager.remove_worktree

        def spy(inner_self, *a, **kw):
            depths.append(_git_lock_depth(self.root))
            return original(inner_self, *a, **kw)

        with patch.object(WorktreeManager, "remove_worktree", spy):
            with patch("builtins.input", return_value="y"):
                cmd_uninit(argparse.Namespace(force=False))
        self.assertTrue(depths, "no worktree was removed, so nothing was proven")
        self.assertTrue(all(d > 0 for d in depths),
                        f"uninit mutated .git/worktrees without the lock (depths: {depths})")

    def test_the_lock_is_released_before_our_own_directory_goes(self):
        # The lock file lives inside `.lanekeeper/`, and Windows will not delete a file
        # that is still open. Removing the home directory must happen after release.
        import os
        from lanekeeper import uninit as uninit_mod
        cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)
        with patch("builtins.input", return_value="y"):
            self.assertEqual(cmd_uninit(argparse.Namespace(force=False)), 0)
        self.assertFalse(paths.home(self.root).exists(),
                         "lanekeeper's directory survived, which is what a held lock file "
                         "would cause on Windows")


class TestAHeldLockIsNeverATraceback(RegistryReaderTestCase):
    """The review's other two findings: both new acquisitions were unguarded, so a lock
    held by somebody else turned a diagnostic and the escape hatch into crashes."""

    def setUp(self):
        super().setUp()
        self.patcher.stop()          # these tests want the real reader, held elsewhere
        import os
        cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)

    def test_doctor_reports_a_busy_repository_instead_of_crashing(self):
        from lanekeeper.lock import FileLockError
        with patch.object(StateManager, "git_lock",
                          side_effect=FileLockError("held elsewhere")):
            report = Doctor().diagnose()
        self.assertFalse(report.is_healthy)
        message = " ".join(c.message for c in report.checks)
        self.assertIn("worktrees", message.lower())
        busy = [c for c in report.checks if "worktrees" in c.message.lower()]
        self.assertTrue(busy)
        self.assertFalse(busy[0].repairable,
                         "waiting for another command is not something repair can fix")

    def test_uninit_still_shows_its_plan_when_the_lock_is_held(self):
        from lanekeeper.lock import FileLockError
        with patch.object(StateManager, "git_lock",
                          side_effect=FileLockError("held elsewhere")):
            with patch("builtins.input", return_value="n"):
                code = cmd_uninit(argparse.Namespace(force=False))
        # Aborted by the answer, not by the lock: the plan was built and shown.
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
