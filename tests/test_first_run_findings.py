"""What the owner hit running the deep-test protocol on Windows against 0.7.5.

Every one of these is a sentence the tool said, or failed to say, to somebody using
it for the first time. None is a hole in the gate; together they are the difference
between a tool that explains itself and one that has to be explained.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper import ticket as ticket_mod
from lanekeeper.config import Config, LaneConfig, save_config
from lanekeeper.trackers.base import TrackedIssue

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402


def _lane(**kw):
    fields = dict(name="feat-02", paths=("src/services/cluster.ts", "src/domain/contracts.ts"),
                  source=ticket_mod.Source.TICKET,
                  issue=TrackedIssue("2", "[FEAT-02] Clustering engine"))
    fields.update(kw)
    return ticket_mod.TicketLane(**fields)


class BareRepoTestCase(unittest.TestCase):
    """A repository that has never seen lanekeeper — the first thirty seconds."""

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


class TestTheFirstAdviceIsNotTheWrongPath(BareRepoTestCase):
    """Findings 1 and 2: both messages sent a new user to `init`, which writes
    technology-layer lanes — the path the tool argues against."""

    def test_status_points_at_the_ticket_path(self):
        res = run_cli(["status"], cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        out = res.stdout + res.stderr
        self.assertIn("spawn --ticket", out)
        self.assertNotIn("Run 'lanekeeper init' first", out)

    def test_doctor_points_at_the_ticket_path(self):
        res = run_cli(["doctor"], cwd=self.root)
        out = res.stdout + res.stderr
        self.assertIn("spawn --ticket", out)
        self.assertNotIn("Run 'lanekeeper init' first", out)

    def test_init_is_still_named_but_with_what_it_costs(self):
        res = run_cli(["status"], cwd=self.root)
        out = res.stdout + res.stderr
        self.assertIn("technology-layer", out)


class TestDoctorDoesNotSendYouToACommandThatCannotHelp(BareRepoTestCase):
    """Finding 3: `repair` reconciles agents and ports; it cannot create a config."""

    def test_a_missing_configuration_does_not_offer_repair(self):
        res = run_cli(["doctor"], cwd=self.root)
        out = res.stdout + res.stderr
        self.assertIn("problem(s) detected", out)
        self.assertNotIn("lanekeeper repair", out)


class TestTheGateHasANameThatSaysWhatItDoes(BareRepoTestCase):
    """Finding 8: `check --write-workflow` writes a file and checks nothing."""

    def setUp(self):
        super().setUp()
        cfg = Config.default("p")
        cfg.capability_gates = {}
        cfg.lanes = {"feat-02": LaneConfig("feat-02", allow=["src/**"])}
        save_config(cfg, self.root)

    def test_install_gate_writes_the_workflow(self):
        res = run_cli(["install-gate"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertTrue((self.root / ".github/workflows/lanekeeper-gate.yml").exists())
        again = run_cli(["install-gate"], cwd=self.root)
        self.assertEqual(again.returncode, 0, output_of(again))
        self.assertIn("already exists", again.stdout)

    def test_the_old_flag_still_works(self):
        res = run_cli(["check", "--write-workflow"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertTrue((self.root / ".github/workflows/lanekeeper-gate.yml").exists())

    def test_the_missing_gate_message_names_the_new_command(self):
        text = ticket_mod.next_steps(_lane(), gate_workflow_exists=False)
        self.assertIn("lanekeeper install-gate", text)
        self.assertNotIn("--write-workflow", text)


class TestItSaysHowToActuallyDoTheWork(unittest.TestCase):
    """Finding 5, the one that stopped a first-time user dead: a beautifully prepared
    worktree, and nothing anywhere saying what to do in it."""

    def test_the_prompt_carries_the_task_and_every_allowed_file(self):
        prompt = ticket_mod.agent_prompt(_lane())
        self.assertIn("#2", prompt)
        self.assertIn("Clustering engine", prompt)
        for path in ("src/services/cluster.ts", "src/domain/contracts.ts"):
            self.assertIn(path, prompt)
        self.assertIn("stop and say so", prompt)

    def test_how_to_work_names_the_three_things_to_do(self):
        text = ticket_mod.how_to_work(_lane(), Path("/repo/.lanekeeper/worktrees/agent-001"),
                                      "agent-001")
        self.assertIn("does not write code", text)
        self.assertIn("coding agent", text)
        self.assertIn("lanekeeper check --lane feat-02", text)
        self.assertIn(".lane", text)

    def test_a_ticket_with_no_title_still_makes_a_usable_prompt(self):
        prompt = ticket_mod.agent_prompt(_lane(issue=TrackedIssue("9", "")))
        self.assertIn("issue #9", prompt)


class TestTheCommitWarningNamesTheRightCulprit(unittest.TestCase):
    """Finding 7: an uncommitted policy is not visible inside the agent's worktree at
    all, so the agent cannot sweep it up. The person doing `git add -A` can."""

    def test_it_does_not_blame_the_agent(self):
        text = ticket_mod.next_steps(_lane(policy_uncommitted=True),
                                     gate_workflow_exists=True, base="main")
        self.assertIn("Commit the policy here", text)
        self.assertNotIn("agent's branch, and", text.split("denies it")[0])
        self.assertIn("git add .lanekeeper", text)

    def test_an_uncommitted_policy_is_invisible_inside_the_worktree(self):
        """The behaviour the old wording got wrong, pinned so it cannot drift back."""
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for cmd in (["git", "init", "-q", "-b", "main", "."],
                    ["git", "config", "user.email", "t@t.c"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=root, check=True)
        (root / "a.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True)
        (root / ".lanekeeper").mkdir()
        (root / ".lanekeeper" / "config.yaml").write_text("lanes: {}", encoding="utf-8")
        subprocess.run(["git", "worktree", "add", "-q", "-b", "agent", "wt"],
                       cwd=root, check=True)
        self.assertFalse((root / "wt" / ".lanekeeper").exists(),
                         "an uncommitted policy must not reach the agent's worktree")


if __name__ == "__main__":
    unittest.main()
