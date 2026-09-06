"""Nothing in lanekeeper ever looked at the remote, and two findings from the deep-test
run were that blind spot from opposite sides.

#65: `cleanup` deleted two branches as "fully merged" that were pushed and open in
pull requests, because `git branch -d` accepts merged-into-upstream and nothing
checked against the base. #78: `spawn --ticket` created a branch name that already
existed on the remote as an open pull request's head, and the collision surfaced at
`git push`, after the work was done.

Every test here has a real remote: a bare repository on disk as `origin`. Until these
existed no test in the suite ever pushed anywhere, which is why the first was invisible.
No network is touched.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper.config import Config, LaneConfig, save_config
from lanekeeper.worktree import WorktreeManager

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import cli_env, output_of, run_cli  # noqa: E402


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


class RemoteTestCase(unittest.TestCase):
    def setUp(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        self.origin = base / "origin.git"
        _git(base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.root = base / "clone"
        self.root.mkdir()
        _git(self.root, "init", "-q", "-b", "main", ".")
        _git(self.root, "config", "user.email", "t@t.c")
        _git(self.root, "config", "user.name", "t")
        _git(self.root, "remote", "add", "origin", str(self.origin))
        (self.root / "src").mkdir()
        (self.root / "src" / "a.py").write_text("x\n", encoding="utf-8")
        cfg = Config.default("p")
        cfg.capability_gates = {}
        cfg.lanes = {"feat-02": LaneConfig("feat-02", allow=["src/**"])}
        save_config(cfg, self.root)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "init")
        _git(self.root, "push", "-q", "-u", "origin", "main")
        self.mgr = WorktreeManager(self.root)

    def spawn(self, *extra):
        res = run_cli(["spawn", "--lane", "feat-02", "--task", "#2 [FEAT-02] Thing", *extra],
                      cwd=self.root)
        return res

    def worktree(self, agent="agent-001"):
        return self.root / ".lanekeeper" / "worktrees" / agent

    def commit_in(self, wt, name="work.py"):
        (wt / "src" / name).write_text("new\n", encoding="utf-8")
        _git(wt, "add", "-A")
        _git(wt, "commit", "-qm", "work")


# --- #65 --------------------------------------------------------------------------


class TestCleanupKeepsAPushedUnmergedBranch(RemoteTestCase):
    def test_pushed_but_not_merged_is_kept_and_says_where_the_commits_are(self):
        res = self.spawn()
        self.assertEqual(res.returncode, 0, output_of(res))
        wt = self.worktree()
        self.commit_in(wt)
        branch = _git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        _git(wt, "push", "-q", "-u", "origin", "HEAD")

        res = run_cli(["cleanup", "agent-001", "--force"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertTrue(self.mgr.branch_exists(branch), "a pushed, unmerged branch was deleted")
        self.assertNotIn("fully merged", res.stdout)
        self.assertIn(f"Kept branch {branch}: not merged into main", res.stdout)
        self.assertIn("pushed to origin/", res.stdout)

    def test_not_pushed_anywhere_is_kept_with_the_stronger_warning(self):
        self.spawn()
        wt = self.worktree()
        self.commit_in(wt)
        branch = _git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        res = run_cli(["cleanup", "agent-001", "--force"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertTrue(self.mgr.branch_exists(branch))
        self.assertIn("not pushed anywhere", res.stdout)
        self.assertIn("git branch -D", res.stdout)

    def test_merged_into_the_base_is_deleted_and_the_base_is_named(self):
        self.spawn()
        wt = self.worktree()
        self.commit_in(wt)
        branch = _git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        _git(wt, "push", "-q", "-u", "origin", "HEAD")
        _git(self.root, "merge", "-q", branch)
        res = run_cli(["cleanup", "agent-001", "--force"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertFalse(self.mgr.branch_exists(branch))
        self.assertIn(f"Deleted branch {branch} (merged into main)", res.stdout)

    def test_the_helpers_answer_the_question_directly(self):
        self.spawn()
        wt = self.worktree()
        self.commit_in(wt)
        branch = _git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        self.assertFalse(self.mgr.branch_is_merged(branch, "main"))
        self.assertIsNone(self.mgr.branch_is_pushed(branch))
        _git(wt, "push", "-q", "-u", "origin", "HEAD")
        self.assertTrue(self.mgr.branch_is_pushed(branch))
        self.commit_in(wt, "more.py")
        self.assertFalse(self.mgr.branch_is_pushed(branch))
        self.assertIn("not every commit", self.mgr.describe_kept_branch(branch, "main"))
        # `delete_branch` without force refuses exactly what `-d` would have accepted.
        _git(wt, "push", "-q", "origin", "HEAD")
        self.assertTrue(self.mgr.branch_is_pushed(branch))
        _git(self.root, "worktree", "remove", "--force", str(wt))
        self.assertFalse(self.mgr.delete_branch(branch))
        self.assertTrue(self.mgr.branch_exists(branch))
        self.assertTrue(self.mgr.delete_branch(branch, force=True))


class TestUninitAppliesTheSameRule(RemoteTestCase):
    def test_a_pushed_unmerged_branch_survives_uninit_force(self):
        self.spawn()
        wt = self.worktree()
        self.commit_in(wt)
        branch = _git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        _git(wt, "push", "-q", "-u", "origin", "HEAD")
        res = run_cli(["uninit", "--force"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertTrue(self.mgr.branch_exists(branch), "uninit deleted a pushed branch")
        self.assertIn("not merged into main", res.stdout)
        self.assertIn("pushed to origin/", res.stdout)


# --- #78 --------------------------------------------------------------------------


class TestSpawnLooksAtTheRemoteFirst(RemoteTestCase):
    def _push_remote_branch(self):
        """The earlier session's work: the same lanekeeper-made name, pushed, open."""
        self.spawn()
        wt = self.worktree()
        self.commit_in(wt)
        branch = _git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        _git(wt, "push", "-q", "-u", "origin", "HEAD")
        sha = _git(wt, "rev-parse", "HEAD").stdout.strip()
        # Cleaned up locally, as it was on the real run: the lane looks free.
        res = run_cli(["cleanup", "agent-001", "--force"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        _git(self.root, "branch", "-D", branch)
        # The counter goes on, so the next agent would be agent-002; make it spawn under
        # the same id by resetting the ledger, which is what a fresh clone looks like.
        shutil.rmtree(self.root / ".lanekeeper" / "state")
        return branch, sha

    def test_it_refuses_names_the_sha_and_the_three_ways_forward_and_creates_nothing(self):
        branch, sha = self._push_remote_branch()
        res = self.spawn()
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn(f"Branch '{branch}' already exists on origin at {sha[:10]}", res.stderr)
        for choice in ("--remote-branch continue", "--remote-branch rename",
                       "--remote-branch ignore"):
            self.assertIn(choice, res.stderr)
        self.assertIn("Nothing was created", res.stderr)
        self.assertFalse(self.worktree().exists())
        status = run_cli(["status"], cwd=self.root)
        self.assertIn("No active agents", status.stdout, "the reservation was rolled back")

    def test_continue_resumes_the_remote_branch(self):
        branch, sha = self._push_remote_branch()
        res = self.spawn("--remote-branch", "continue")
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("Continuing the work", res.stdout)
        head = _git(self.worktree(), "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(head, sha)
        self.assertEqual(self.mgr.branch_upstream(branch), f"origin/{branch}")

    def test_rename_starts_fresh_under_the_proposed_name(self):
        branch, sha = self._push_remote_branch()
        res = self.spawn("--remote-branch", "rename")
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn(f"'{branch}-2'", res.stdout)
        head_branch = _git(self.worktree(), "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        self.assertEqual(head_branch, f"{branch}-2")
        self.assertIn(f"{branch}-2", run_cli(["inspect", "agent-001"], cwd=self.root).stdout)

    def test_ignore_proceeds_and_says_what_it_is_overriding(self):
        branch, sha = self._push_remote_branch()
        res = self.spawn("--remote-branch", "ignore")
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("although origin already has a branch of that name", res.stdout)
        self.assertIn("non-fast-forward", res.stdout)

    def test_an_unreachable_remote_is_a_note_and_never_blocks(self):
        _git(self.root, "remote", "set-url", "origin", str(self.root.parent / "gone.git"))
        res = self.spawn()
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("Could not ask origin", res.stdout)
        self.assertTrue(self.worktree().exists())

    def test_no_remote_at_all_says_nothing(self):
        _git(self.root, "remote", "remove", "origin")
        res = self.spawn()
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertNotIn("Could not ask", res.stdout)

    def test_the_lookup_is_injected_not_live(self):
        """No `gh`, no GitHub: the remote is a directory and the tracker is asked
        through its interface, which the null tracker answers with None."""
        from lanekeeper.trackers import NullTracker
        self.assertIsNone(NullTracker().pull_request_for_branch("x"))


if __name__ == "__main__":
    unittest.main()
