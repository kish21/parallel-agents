import tempfile
import unittest
from pathlib import Path

from lanekeeper.state import AgentState, AgentStatus, StateManager


class TestStateManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.state_mgr = StateManager(self.root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_save_and_get_agent(self):
        agent = AgentState(
            id="agent-001",
            name="backend-1",
            seat="SR1",
            lane="backend",
            task="Implement Auth",
            branch="parallel/agent-001/auth",
            worktree_path=str(self.root / "worktrees" / "agent-001"),
            status=AgentStatus.RUNNING.value,
            ports={"backend": 8001},
        )
        self.state_mgr.save_agent(agent)

        retrieved = self.state_mgr.get_agent("agent-001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "backend-1")
        self.assertEqual(retrieved.status, "RUNNING")
        self.assertEqual(retrieved.ports["backend"], 8001)

    def test_list_and_remove_agent(self):
        a1 = AgentState(
            id="agent-001",
            name="backend-1",
            seat="SR1",
            lane="backend",
            task="Task 1",
            branch="b1",
            worktree_path="wt1",
        )
        a2 = AgentState(
            id="agent-002",
            name="frontend-1",
            seat="JR1",
            lane="frontend",
            task="Task 2",
            branch="b2",
            worktree_path="wt2",
        )
        self.state_mgr.save_agent(a1)
        self.state_mgr.save_agent(a2)

        agents = self.state_mgr.list_agents()
        self.assertEqual(len(agents), 2)

        removed = self.state_mgr.remove_agent("agent-001")
        self.assertTrue(removed)
        self.assertEqual(len(self.state_mgr.list_agents()), 1)

    def test_port_allocations_tracking(self):
        self.state_mgr.allocate_port(8001, "agent-001")
        self.state_mgr.allocate_port(3001, "agent-001")
        self.state_mgr.allocate_port(8002, "agent-002")

        allocated = self.state_mgr.get_allocated_ports()
        self.assertEqual(allocated["8001"], "agent-001")
        self.assertEqual(allocated["8002"], "agent-002")

        released = self.state_mgr.release_ports_for_agent("agent-001")
        self.assertIn(8001, released)
        self.assertIn(3001, released)
        self.assertNotIn("8001", self.state_mgr.get_allocated_ports())
        self.assertIn("8002", self.state_mgr.get_allocated_ports())


if __name__ == "__main__":
    unittest.main()
