"""What the second real trial found: the flow around the gate, not the gate itself.

Running the tester sheet on a fresh clone of a real project (kish21/mini-issue-tracker,
its three product-playbook tickets served through a stand-in `gh`) produced a green
gate and two ways to reach a red one that were nobody's mistake:

1. `spawn --ticket` writes the policy into the main checkout and then branches the
   agent from a commit that does not carry it, so a `check` run in the worktree found
   no policy at all.
2. The same uncommitted policy is swept into the agent's first `git add -A`, and the
   gate denies a policy change under an ordinary lane — correctly, and confusingly.

Both are fixed by telling the truth earlier rather than by loosening the gate.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper import check, ticket as ticket_mod
from lanekeeper.config import Config, LaneConfig, save_config
from lanekeeper.lanes import LaneValidationResult
from lanekeeper.trackers.base import TrackedIssue
from lanekeeper.worktree import WorktreeManager

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402


class RepoTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for cmd in (["git", "init", "-q", "-b", "main", "."],
                    ["git", "config", "user.email", "t@t.c"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.root, check=True)
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.root, check=True)

    def write_policy(self):
        cfg = Config.default("p")
        cfg.capability_gates = {}
        cfg.lanes = {"feat-02": LaneConfig("feat-02", allow=["src/services/**"])}
        save_config(cfg, self.root)
        return cfg


class TestTheWorktreeCanStillBeChecked(RepoTestCase):
    """Finding 1: `check` in a worktree branched before the policy was committed."""

    def setUp(self):
        super().setUp()
        self.write_policy()  # written, deliberately not committed
        self.worktree = self.root / "wt"
        subprocess.run(["git", "worktree", "add", "-q", "-b", "agent", str(self.worktree)],
                       cwd=self.root, check=True)
        (self.worktree / "src" / "services").mkdir(parents=True)
        (self.worktree / "src" / "services" / "cluster.ts").write_text("y", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.worktree, check=True)
        subprocess.run(["git", "commit", "-qm", "in lane"], cwd=self.worktree, check=True)

    def test_the_policy_is_read_from_the_main_checkout_and_said_so(self):
        res = run_cli(["check", "--lane", "feat-02", "--base", "main"], cwd=self.worktree)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("no policy of its own", res.stdout)
        self.assertIn("CHECK PASSED", res.stdout)

    def test_a_stray_file_still_fails_when_the_policy_is_borrowed(self):
        (self.worktree / "src" / "stray.py").write_text("z", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.worktree, check=True)
        subprocess.run(["git", "commit", "-qm", "stray"], cwd=self.worktree, check=True)
        res = run_cli(["check", "--lane", "feat-02", "--base", "main"], cwd=self.worktree)
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("src/stray.py", res.stdout)

    def test_a_checkout_with_no_policy_anywhere_still_fails_closed(self):
        """The borrowed policy is a worktree's, never an excuse to pass without one."""
        elsewhere = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, elsewhere, ignore_errors=True)
        for cmd in (["git", "init", "-q", "-b", "main", "."],
                    ["git", "config", "user.email", "t@t.c"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=elsewhere, check=True)
        (elsewhere / "a.py").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=elsewhere, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=elsewhere, check=True)
        res = run_cli(["check", "--lane", "feat-02", "--base", "main"], cwd=elsewhere)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("no policy to check against", res.stderr)

    def test_main_worktree_root_finds_the_main_checkout_from_the_worktree(self):
        found = subprocess.run(
            [sys.executable, "-c",
             "from lanekeeper.worktree import WorktreeManager as W; print(W.main_worktree_root())"],
            cwd=self.worktree, capture_output=True, text=True,
            env={**__import__("os").environ,
                 "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})
        self.assertEqual(Path(found.stdout.strip()).resolve(), self.root.resolve(),
                         found.stdout + found.stderr)


class TestTheUncommittedPolicyIsCalledOut(RepoTestCase):
    """Finding 2: the policy `spawn --ticket` wrote is not committed yet."""

    def test_an_uncommitted_policy_is_seen(self):
        self.write_policy()
        self.assertTrue(ticket_mod.policy_is_uncommitted(self.root))

    def test_a_committed_policy_is_not(self):
        self.write_policy()
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "policy"], cwd=self.root, check=True)
        self.assertFalse(ticket_mod.policy_is_uncommitted(self.root))

    def test_a_git_that_cannot_answer_is_treated_as_clean(self):
        def broken(argv):
            raise OSError("no git here")
        self.assertFalse(ticket_mod.policy_is_uncommitted(self.root, runner=broken))

    def test_next_steps_names_the_commit_before_the_label(self):
        lane = ticket_mod.TicketLane(
            name="feat-02", paths=("src/services/**",), source=ticket_mod.Source.TICKET,
            issue=TrackedIssue("2", "t"), policy_uncommitted=True)
        text = ticket_mod.next_steps(lane, gate_workflow_exists=True, base="main")
        self.assertIn("Commit the policy here, on 'main'", text)
        self.assertIn("git add .lanekeeper", text)
        self.assertLess(text.index("Commit the policy"), text.index("label it"))

    def test_a_committed_policy_says_nothing_about_committing(self):
        lane = ticket_mod.TicketLane(
            name="feat-02", paths=("src/services/**",), source=ticket_mod.Source.TICKET,
            issue=TrackedIssue("2", "t"))
        text = ticket_mod.next_steps(lane, gate_workflow_exists=True)
        self.assertNotIn("Commit the policy", text)
        self.assertIn("label it 'lane: feat-02'", text)


class TestTheSmallThingsTheTrialShowed(unittest.TestCase):
    def test_one_file_stays_and_two_files_stay(self):
        def rendered(files):
            return check.render(check.CheckReport(
                lane="feat-02", base="main", head="HEAD",
                result=LaneValidationResult(lane_name="feat-02", is_valid=True,
                                            allowed_files=files)))
        self.assertIn("All 1 changed file stays inside", rendered(["a.py"]))
        self.assertIn("All 2 changed files stay inside", rendered(["a.py", "b.py"]))

    def test_a_branch_name_does_not_end_in_a_separator(self):
        long_title = "#2 [FEAT-02]: Automated Semantic Clustering Engine with Gemini"
        name = WorktreeManager.make_branch_name(
            WorktreeManager(Path(".")), "agent-001", long_title)
        self.assertFalse(name.endswith("-"), name)
        self.assertTrue(name.startswith("parallel/agent-001/"))


if __name__ == "__main__":
    unittest.main()
