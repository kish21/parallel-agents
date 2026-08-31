import tempfile
import unittest
from pathlib import Path

from lanekeeper.config import generate_default_config
from lanekeeper.environment import EnvironmentManager
from lanekeeper.state import AgentState


class TestEnvironmentManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.worktree = Path(self.tmp_dir.name)
        self.config = generate_default_config("EnvApp")
        self.env_mgr = EnvironmentManager(self.config)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_setup_environment_files(self):
        agent = AgentState(
            id="agent-001",
            name="backend-1",
            seat="SR1",
            lane="backend",
            task="API Auth",
            branch="parallel/agent-001/auth",
            worktree_path=str(self.worktree),
            ports={"backend": 8001, "frontend": 3001},
        )

        self.env_mgr.write_agent_environment(self.worktree, agent)
        env_file = self.worktree / ".env"
        lane_file = self.worktree / ".lane"
        self.assertTrue(env_file.exists())
        self.assertTrue(lane_file.exists())

        env_content = env_file.read_text(encoding="utf-8")
        self.assertIn("PORT='8001'", env_content)
        self.assertIn("BACKEND_PORT='8001'", env_content)
        self.assertIn("FRONTEND_PORT='3001'", env_content)
        self.assertIn("AGENT_ID='agent-001'", env_content)
        self.assertIn("DATABASE_NAME='app_agent_001'", env_content)

        lane_content = lane_file.read_text(encoding="utf-8")
        self.assertIn("SEAT='SR1'", lane_content)
        self.assertIn("ROLE='sr1'", lane_content)
        self.assertIn("LANE='backend'", lane_content)


if __name__ == "__main__":
    unittest.main()
