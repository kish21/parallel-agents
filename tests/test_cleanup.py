import subprocess
import tempfile
import unittest
from pathlib import Path

from parallel_agents.config import generate_default_config
from parallel_agents.ports import PortManager
from parallel_agents.state import AgentState, StateManager
from parallel_agents.worktree import WorktreeManager


class TestCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        # Git Repo
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "tester@test.com"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# Test Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.root, check=True)

        self.config = generate_default_config("CleanupApp")
        self.state_mgr = StateManager(self.root)
        self.wt_mgr = WorktreeManager(self.root)
        self.port_mgr = PortManager(self.config, self.state_mgr)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_cleanup_deletes_worktree_and_reclaims_ports(self):
        branch = self.wt_mgr.make_branch_name("agent-001", "Task 1")
        target_path = self.root / ".parallel-agents" / "worktrees" / "agent-001"
        wt_path = self.wt_mgr.create_worktree(target_path, branch)
        ports = self.port_mgr.allocate_ports_for_agent("agent-001")
        agent = AgentState(
            id="agent-001",
            name="backend-1",
            seat="SR1",
            lane="backend",
            task="Task 1",
            branch=branch,
            worktree_path=str(wt_path),
            ports=ports,
        )
        self.state_mgr.save_agent(agent)

        self.assertTrue(wt_path.exists())
        self.assertIn("8001", self.state_mgr.get_allocated_ports())

        # Cleanup
        self.wt_mgr.remove_worktree(wt_path, force=True)
        self.port_mgr.release_ports("agent-001")
        self.state_mgr.remove_agent("agent-001")

        self.assertFalse(wt_path.exists())
        self.assertNotIn("8001", self.state_mgr.get_allocated_ports())
        self.assertIsNone(self.state_mgr.get_agent("agent-001"))


if __name__ == "__main__":
    unittest.main()
