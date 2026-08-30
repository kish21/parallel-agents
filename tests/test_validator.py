import subprocess
import tempfile
import unittest
from pathlib import Path

from parallel_agents.config import generate_default_config
from parallel_agents.state import AgentState, StateManager
from parallel_agents.validator import Validator
from parallel_agents.worktree import WorktreeManager


class TestValidator(unittest.TestCase):
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

        self.config = generate_default_config("ValidatorApp")
        self.state_mgr = StateManager(self.root)
        self.wt_mgr = WorktreeManager(self.root)
        self.validator = Validator(self.config, self.state_mgr, self.wt_mgr)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_validate_in_lane_pass(self):
        branch = self.wt_mgr.make_branch_name("agent-001", "Auth API")
        target_path = self.root / ".parallel-agents" / "worktrees" / "agent-001"
        wt_path = self.wt_mgr.create_worktree(target_path, branch)
        agent = AgentState(
            id="agent-001",
            name="backend-1",
            seat="SR1",
            lane="backend",
            task="Auth API",
            branch=branch,
            worktree_path=str(wt_path),
        )
        self.state_mgr.save_agent(agent)

        # In-lane change
        (wt_path / "backend").mkdir(parents=True, exist_ok=True)
        (wt_path / "backend" / "users.py").write_text("def get_user(): pass\n", encoding="utf-8")

        report = self.validator.validate_agent("agent-001")
        self.assertTrue(report.is_valid)
        self.assertTrue(report.lane_result.is_valid)

    def test_validate_out_of_lane_fail(self):
        branch = self.wt_mgr.make_branch_name("agent-002", "Login UI")
        target_path = self.root / ".parallel-agents" / "worktrees" / "agent-002"
        wt_path = self.wt_mgr.create_worktree(target_path, branch)
        agent = AgentState(
            id="agent-002",
            name="backend-2",
            seat="SR2",
            lane="backend",
            task="Login UI",
            branch=branch,
            worktree_path=str(wt_path),
        )
        self.state_mgr.save_agent(agent)

        # Out-of-lane change
        (wt_path / "frontend").mkdir(parents=True, exist_ok=True)
        (wt_path / "frontend" / "App.tsx").write_text("export default null;\n", encoding="utf-8")

        report = self.validator.validate_agent("agent-002")
        self.assertFalse(report.is_valid)
        self.assertFalse(report.lane_result.is_valid)
        self.assertEqual(len(report.lane_result.violations), 1)


if __name__ == "__main__":
    unittest.main()
