import concurrent.futures
import tempfile
import unittest
from pathlib import Path

from parallel_agents.lock import StateLock
from parallel_agents.state import AgentState, AgentStatus, StateManager


class TestStateLockIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.state_mgr = StateManager(self.root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_state_lock(self):
        """Proves StateLock prevents race conditions across 20 competing threads."""
        state_mgr = self.state_mgr

        def increment_and_save(idx):
            with state_mgr.lock():
                agent = AgentState(
                    id=f"agent-{idx:03d}",
                    name=f"worker-{idx}",
                    seat="SR1",
                    lane="backend",
                    task=f"Task {idx}",
                    branch=f"parallel/agent-{idx:03d}/t",
                    worktree_path=str(self.root / f"wt-{idx}"),
                    status=AgentStatus.RUNNING.value,
                )
                state_mgr.save_agent(agent)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(increment_and_save, i) for i in range(1, 21)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        agents = state_mgr.list_agents()
        self.assertEqual(len(agents), 20, "StateLock failed: missing state entries")
        ids = [a.id for a in agents]
        self.assertEqual(len(set(ids)), 20, "StateLock failed: duplicate agent IDs")


if __name__ == "__main__":
    unittest.main()
