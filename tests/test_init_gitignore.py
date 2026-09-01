"""Tests that `init` protects the repository from its own runtime state.

Agent worktrees live at .lanekeeper/worktrees/ *inside* the repository. Without
ignore rules, an agent running `git add -A` sweeps every other agent's worktree and the
shared state files into its own commit — the exact cross-agent contamination this tool
exists to prevent.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper.cli import GITIGNORE_BEGIN, ensure_gitignore


def git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


# `unittest discover` imports these as top-level modules, so a package-relative import
# would not resolve. Put the tests directory on the path explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402


class TestEnsureGitignore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_creates_gitignore_when_absent(self):
        self.assertTrue(ensure_gitignore(self.tmp))
        self.assertIn(GITIGNORE_BEGIN, (self.tmp / ".gitignore").read_text())

    def test_is_idempotent(self):
        self.assertTrue(ensure_gitignore(self.tmp))
        self.assertFalse(ensure_gitignore(self.tmp), "second call must not duplicate the block")
        self.assertEqual((self.tmp / ".gitignore").read_text().count(GITIGNORE_BEGIN), 1)

    def test_preserves_existing_rules(self):
        (self.tmp / ".gitignore").write_text("node_modules/\n*.log\n", encoding="utf-8")
        ensure_gitignore(self.tmp)
        content = (self.tmp / ".gitignore").read_text()
        self.assertIn("node_modules/", content)
        self.assertIn("*.log", content)
        self.assertIn(GITIGNORE_BEGIN, content)

    def test_appends_cleanly_to_file_without_trailing_newline(self):
        (self.tmp / ".gitignore").write_text("node_modules/", encoding="utf-8")
        ensure_gitignore(self.tmp)
        lines = (self.tmp / ".gitignore").read_text().splitlines()
        self.assertIn("node_modules/", lines)
        self.assertIn(GITIGNORE_BEGIN, lines)


class TestInitProtectsTheRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        git(["init", "-q", "-b", "main", "."], self.tmp)
        git(["config", "user.email", "t@t.c"], self.tmp)
        git(["config", "user.name", "t"], self.tmp)
        (self.tmp / "README.md").write_text("x", encoding="utf-8")
        git(["add", "-A"], self.tmp)
        git(["commit", "-qm", "init"], self.tmp)
        self.assertEqual(run_cli(["init", "--name", "proj"], self.tmp).returncode, 0)

    def test_runtime_state_is_ignored_but_config_is_tracked(self):
        self.assertEqual(
            run_cli(["spawn", "--lane", "backend", "--name", "b1", "--task", "x"], self.tmp).returncode,
            0)

        # The lane policy is the team contract: it must remain committable.
        self.assertNotEqual(
            git(["check-ignore", "-q", ".lanekeeper/config.yaml"], self.tmp).returncode, 0,
            "config.yaml must NOT be ignored — it is the shared lane policy")
        (self.tmp / ".lanekeeper" / "capabilities").mkdir(parents=True, exist_ok=True)
        (self.tmp / ".lanekeeper" / "capabilities" / "JR1.json").write_text("{}", encoding="utf-8")
        self.assertNotEqual(
            git(["check-ignore", "-q", ".lanekeeper/capabilities/JR1.json"], self.tmp).returncode, 0,
            "the seat cards must NOT be ignored — the gate reads them; the first real "
            "project could not commit them")

        # Everything else under .lanekeeper is machine-local.
        for ignored in [".lanekeeper/state/agents.json",
                        ".lanekeeper/state/ports.json",
                        ".lanekeeper/worktrees/agent-001/README.md"]:
            with self.subTest(path=ignored):
                self.assertEqual(
                    git(["check-ignore", "-q", ignored], self.tmp).returncode, 0,
                    f"{ignored} must be ignored")

    def test_git_add_all_does_not_stage_worktrees_or_state(self):
        self.assertEqual(
            run_cli(["spawn", "--lane", "backend", "--name", "b1", "--task", "x"], self.tmp).returncode,
            0)
        staged = git(["add", "-A", "--dry-run"], self.tmp).stdout
        self.assertNotIn("worktrees", staged, f"`git add -A` would stage agent worktrees:\n{staged}")
        self.assertNotIn("state/", staged, f"`git add -A` would stage runtime state:\n{staged}")
        self.assertIn("config.yaml", staged)


if __name__ == "__main__":
    unittest.main()
