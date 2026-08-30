import subprocess
import tempfile
import unittest
from pathlib import Path

from parallel_agents.config import generate_default_config
from parallel_agents.worktree import WorktreeManager


class TestWorktreeManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        # Initialize Git repo
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "tester@test.com"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# Test Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.root, check=True)

        self.config = generate_default_config("WorktreeTestApp")
        self.wt_mgr = WorktreeManager(self.root)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_branch_name_generation(self):
        branch = self.wt_mgr.make_branch_name("agent-001", "Add Stripe Webhook")
        self.assertEqual(branch, "parallel/agent-001/add-stripe-webhook")

    def test_create_and_remove_worktree(self):
        branch = self.wt_mgr.make_branch_name("agent-001", "Build API")
        target_path = self.root / ".parallel-agents" / "worktrees" / "agent-001"
        wt_path = self.wt_mgr.create_worktree(target_path, branch)
        self.assertTrue(wt_path.exists())
        self.assertTrue((wt_path / ".git").exists())
        self.assertEqual(branch, "parallel/agent-001/build-api")

        # Check uncommitted status
        self.assertFalse(self.wt_mgr.has_uncommitted_changes(wt_path))

        # Add uncommitted file
        (wt_path / "new_file.txt").write_text("Hello", encoding="utf-8")
        self.assertTrue(self.wt_mgr.has_uncommitted_changes(wt_path))

        # Remove worktree
        self.wt_mgr.remove_worktree(wt_path, force=True)
        self.assertFalse(wt_path.exists())


if __name__ == "__main__":
    unittest.main()
