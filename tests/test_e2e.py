"""End-to-End integration tests for parallel-agents in isolated temporary Git repos."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from parallel_agents.cli import (
    cmd_cleanup,
    cmd_doctor,
    cmd_init,
    cmd_inspect,
    cmd_spawn,
    cmd_status,
    cmd_validate,
)
from parallel_agents.config import load_config
from parallel_agents.state import StateManager
from parallel_agents.worktree import WorktreeManager


class TestParallelAgentsE2E(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.tmp_dir.name)
        self.orig_cwd = os.getcwd()
        os.chdir(self.repo_dir)

        # 1. Initialize git repo with main branch and initial commit
        subprocess.run(["git", "init", "-b", "main"], cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.repo_dir, check=True)
        subprocess.run(["git", "config", "user.email", "tester@test.com"], cwd=self.repo_dir, check=True)

        readme_file = self.repo_dir / "README.md"
        readme_file.write_text("# Test Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo_dir, check=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], cwd=self.repo_dir, check=True)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        self.tmp_dir.cleanup()

    def test_full_agent_lifecycle_and_lane_isolation(self):
        # 1. Init
        class Args:
            name = "e2e-project"
            force = False
        self.assertEqual(cmd_init(Args()), 0)

        cfg = load_config(self.repo_dir)
        self.assertEqual(cfg.project_name, "e2e-project")

        # 2. Doctor Check
        self.assertEqual(cmd_doctor(Args()), 0)

        # 3. Spawn Agent 1 (Backend)
        class SpawnArgs1:
            name = "backend-1"
            lane = "backend"
            task = "Implement user auth"
            seat = "SR1"
            command = None
            force = False

        self.assertEqual(cmd_spawn(SpawnArgs1()), 0)

        # 4. Spawn Agent 2 (Frontend)
        class SpawnArgs2:
            name = "frontend-1"
            lane = "frontend"
            task = "Build login view"
            seat = "JR1"
            command = None
            force = False

        self.assertEqual(cmd_spawn(SpawnArgs2()), 0)

        # 5. Verify Isolation in State & Git
        state_mgr = StateManager(self.repo_dir)
        agents = state_mgr.list_agents()
        self.assertEqual(len(agents), 2)

        agent_1 = state_mgr.get_agent("agent-001")
        agent_2 = state_mgr.get_agent("agent-002")
        self.assertIsNotNone(agent_1)
        self.assertIsNotNone(agent_2)

        # Worktree path separation
        self.assertNotEqual(agent_1.worktree_path, agent_2.worktree_path)
        self.assertTrue(Path(agent_1.worktree_path).exists())
        self.assertTrue(Path(agent_2.worktree_path).exists())

        # Port separation
        self.assertEqual(agent_1.ports["backend"], 8001)
        self.assertEqual(agent_1.ports["frontend"], 3001)
        self.assertEqual(agent_2.ports["backend"], 8002)
        self.assertEqual(agent_2.ports["frontend"], 3002)

        # Environment files created
        self.assertTrue((Path(agent_1.worktree_path) / ".env").exists())
        self.assertTrue((Path(agent_1.worktree_path) / ".lane").exists())

        # 6. Test In-Lane Modification -> Validate Passes
        wt1_path = Path(agent_1.worktree_path)
        backend_file = wt1_path / "backend" / "auth.py"
        backend_file.parent.mkdir(parents=True, exist_ok=True)
        backend_file.write_text("def authenticate(): return True\n", encoding="utf-8")

        class ValArgs1:
            agent = "agent-001"
        self.assertEqual(cmd_validate(ValArgs1()), 0)

        # 7. Test Out-of-Lane Modification -> Validate Fails
        forbidden_file = wt1_path / "frontend" / "App.tsx"
        forbidden_file.parent.mkdir(parents=True, exist_ok=True)
        forbidden_file.write_text("export const App = () => null;\n", encoding="utf-8")

        self.assertEqual(cmd_validate(ValArgs1()), 2)

        # 8. Cleanup Agent 1
        class CleanupArgs:
            agent = "agent-001"
            force = True

        self.assertEqual(cmd_cleanup(CleanupArgs()), 0)

        # Verify ports released and worktree removed
        self.assertFalse(wt1_path.exists())
        self.assertIsNone(state_mgr.get_agent("agent-001"))
        allocated = state_mgr.get_allocated_ports()
        self.assertNotIn("8001", allocated)
        self.assertNotIn("3001", allocated)


if __name__ == "__main__":
    unittest.main()
