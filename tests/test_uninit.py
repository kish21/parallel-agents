"""Taking lanekeeper back out of a repository — issue #26.

Trying the tool on a project somebody cares about has to be reversible, or it does
not get tried. These tests are about residue: what is left on disk, in `git status`
and in `git branch` after `uninit`, and the one thing that must survive it — a branch
holding commits nobody has merged.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper import paths
from lanekeeper import uninit as uninit_mod
from lanekeeper.capabilities import default_cards, save_card
from lanekeeper.cli import GITIGNORE_BEGIN, GITIGNORE_END, ensure_gitignore
from lanekeeper.check import WORKFLOW_PATH
from lanekeeper.config import generate_default_config, save_config
from lanekeeper.state import AgentState, StateManager
from lanekeeper.worktree import WorktreeManager

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import cli_env, output_of, run_cli  # noqa: E402


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=str(root), check=True,
                          capture_output=True, text=True, encoding="utf-8")


class InstalledRepoTestCase(unittest.TestCase):
    """A repository that has been through `init` and had one agent spawned in it."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        _git(self.root, "init", "-q", "-b", "main", ".")
        _git(self.root, "config", "user.email", "t@t.c")
        _git(self.root, "config", "user.name", "t")
        (self.root / "README.md").write_text("# repo\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "init")

        self.config = generate_default_config("Uninitable")
        save_config(self.config, self.root)
        for card in default_cards(sorted(self.config.lanes)):
            save_card(card, self.root)
        ensure_gitignore(self.root)
        workflow = self.root / WORKFLOW_PATH
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text("name: lanekeeper\n", encoding="utf-8")

        self.wt_mgr = WorktreeManager(self.root)
        self.state_mgr = StateManager(self.root)

    def spawn_agent(self, agent_id="agent-001", status="STOPPED"):
        branch = self.wt_mgr.make_branch_name(agent_id, "a task")
        target = self.root / paths.worktrees_dir() / agent_id
        wt_path = self.wt_mgr.create_worktree(target, branch)
        agent = AgentState(
            id=agent_id, name="agent-1", seat="SR1",
            lane=sorted(self.config.lanes)[0], task="a task",
            branch=branch, worktree_path=str(wt_path), status=status,
        )
        self.state_mgr.save_agent(agent)
        return agent

    def porcelain(self):
        res = subprocess.run(["git", "status", "--porcelain"], cwd=str(self.root),
                             capture_output=True, text=True, encoding="utf-8")
        return res.stdout.strip()

    def agent_branches(self):
        res = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/"],
            cwd=str(self.root), capture_output=True, text=True, encoding="utf-8")
        return [b for b in res.stdout.split() if b.startswith("parallel/")]


class TestUninitLeavesNothingBehind(InstalledRepoTestCase):
    """The definition of done on #26: git status clean, no agent branches left."""

    def test_removes_everything_it_wrote(self):
        agent = self.spawn_agent()
        wt_path = Path(agent.worktree_path)
        self.assertTrue(wt_path.exists())

        res = run_cli(["uninit", "--force"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))

        self.assertFalse(paths.home(self.root).exists(), "lanekeeper's directory survived")
        self.assertFalse((self.root / WORKFLOW_PATH).exists(), "the gate workflow survived")
        self.assertFalse(wt_path.exists(), "the worktree survived")
        self.assertEqual(self.agent_branches(), [], "an agent branch survived")
        gitignore = self.root / ".gitignore"
        if gitignore.exists():
            self.assertNotIn(GITIGNORE_BEGIN, gitignore.read_text(encoding="utf-8"))
        self.assertEqual(self.porcelain(), "", "the working tree is not clean")

    def test_says_what_it_removed(self):
        self.spawn_agent()
        res = run_cli(["uninit", "--force"], cwd=self.root)
        out = res.stdout + res.stderr
        self.assertIn("worktree", out, output_of(res))
        self.assertIn(paths.display_home(self.root), out, output_of(res))
        self.assertIn(".gitignore", out, output_of(res))


class TestUnmergedWorkIsNeverDeleted(InstalledRepoTestCase):
    """`--force` answers "are you sure"; it does not decide that somebody's commits
    do not matter."""

    def test_a_branch_with_unmerged_commits_survives_force(self):
        agent = self.spawn_agent()
        wt = Path(agent.worktree_path)
        (wt / "work.txt").write_text("unmerged work\n", encoding="utf-8")
        _git(wt, "add", "work.txt")
        _git(wt, "commit", "-qm", "work")

        res = run_cli(["uninit", "--force"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn(agent.branch, self.agent_branches(),
                      "an unmerged branch was deleted")
        out = res.stdout + res.stderr
        self.assertIn("nobody has merged", out, output_of(res))
        self.assertIn("git branch -D", out, output_of(res))


class TestLiveAgentsStopIt(InstalledRepoTestCase):
    def test_refuses_and_names_the_agent(self):
        agent = self.spawn_agent(status="RUNNING")
        res = run_cli(["uninit"], cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        out = res.stdout + res.stderr
        self.assertIn(agent.id, out)
        self.assertIn("--force", out)
        self.assertTrue(paths.home(self.root).exists(), "it removed things anyway")


class TestItAsksFirst(InstalledRepoTestCase):
    def test_answering_no_removes_nothing(self):
        self.spawn_agent()
        proc = subprocess.run(
            [sys.executable, "-m", "lanekeeper.cli", "uninit"],
            cwd=str(self.root), input="n\n", capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=cli_env())
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("This will remove:", proc.stdout)
        self.assertTrue(paths.home(self.root).exists())

    def test_nothing_answered_is_not_yes(self):
        self.spawn_agent()
        proc = subprocess.run(
            [sys.executable, "-m", "lanekeeper.cli", "uninit"],
            cwd=str(self.root), input="", capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=cli_env())
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertTrue(paths.home(self.root).exists())


class TestNothingToRemove(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        _git(self.root, "init", "-q", "-b", "main", ".")
        _git(self.root, "config", "user.email", "t@t.c")
        _git(self.root, "config", "user.name", "t")

    def test_says_so_and_succeeds(self):
        res = run_cli(["uninit"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("Nothing to remove", res.stdout)


class TestTheGitignoreBlock(unittest.TestCase):
    """Only between the markers. What the person wrote around it is theirs."""

    def test_keeps_everything_outside_the_markers(self):
        text = (
            "node_modules/\n"
            "\n"
            f"{GITIGNORE_BEGIN}\n"
            "/.lanekeeper/*\n"
            f"{GITIGNORE_END}\n"
            "\n"
            "dist/\n"
        )
        out = uninit_mod.strip_gitignore_block(text, GITIGNORE_BEGIN, GITIGNORE_END)
        self.assertNotIn(".lanekeeper", out)
        self.assertIn("node_modules/", out)
        self.assertIn("dist/", out)

    def test_a_file_without_the_block_is_untouched(self):
        text = "node_modules/\ndist/\n"
        self.assertEqual(
            uninit_mod.strip_gitignore_block(text, GITIGNORE_BEGIN, GITIGNORE_END), text)


if __name__ == "__main__":
    unittest.main()
