import subprocess
import tempfile
import unittest
from pathlib import Path

from lanekeeper.capabilities import default_cards, save_card
from lanekeeper.config import generate_default_config
from lanekeeper.doctor import Doctor
from lanekeeper.state import AgentState, StateManager
from lanekeeper.worktree import WorktreeManager


class TestDoctor(unittest.TestCase):
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

        self.config = generate_default_config("DoctorApp")
        # Gates ship enabled; a gate with no cards is a doctor problem by design.
        for card in default_cards(sorted(self.config.lanes)):
            save_card(card, self.root)
        self.state_mgr = StateManager(self.root)
        self.doctor = Doctor(self.root, self.config, self.state_mgr)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_clean_doctor_diagnosis(self):
        report = self.doctor.diagnose()
        self.assertTrue(report.is_healthy)
        self.assertEqual(report.problem_count, 0)

    def test_doctor_detects_missing_worktree(self):
        # Register an agent pointing to a non-existent worktree
        agent = AgentState(
            id="agent-ghost",
            name="ghost-agent",
            seat="SR1",
            lane="backend",
            task="Ghost task",
            branch="parallel/ghost",
            worktree_path=str(self.root / "non_existent_wt"),
        )
        self.state_mgr.save_agent(agent)

        report = self.doctor.diagnose()
        self.assertFalse(report.is_healthy)


if __name__ == "__main__":
    unittest.main()
