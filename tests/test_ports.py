import tempfile
import unittest
from pathlib import Path

from lanekeeper.config import generate_default_config
from lanekeeper.ports import PortError, PortManager
from lanekeeper.state import StateManager


class TestPortManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.config = generate_default_config("PortTestApp")
        self.state = StateManager(self.root)
        self.port_mgr = PortManager(self.config, self.state)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_allocate_ports_success(self):
        ports1 = self.port_mgr.allocate_ports_for_agent("agent-001")
        self.assertEqual(ports1["backend"], 8001)
        self.assertEqual(ports1["frontend"], 3001)

        ports2 = self.port_mgr.allocate_ports_for_agent("agent-002")
        self.assertEqual(ports2["backend"], 8002)
        self.assertEqual(ports2["frontend"], 3002)

    def test_ports_unique_across_agents(self):
        ports = []
        for i in range(1, 5):
            p = self.port_mgr.allocate_ports_for_agent(f"agent-00{i}")
            ports.append(p["backend"])
        self.assertEqual(len(ports), len(set(ports)))

    def test_release_ports(self):
        ports1 = self.port_mgr.allocate_ports_for_agent("agent-001")
        released = self.port_mgr.release_ports("agent-001")
        self.assertIn(8001, released)
        self.assertIn(3001, released)

        # Re-allocation should reuse the lowest released port
        ports_new = self.port_mgr.allocate_ports_for_agent("agent-new")
        self.assertEqual(ports_new["backend"], 8001)

    def test_audit_ports_clean_and_orphaned(self):
        from lanekeeper.state import AgentState, AgentStatus
        # Allocate port for agent-001
        self.port_mgr.allocate_ports_for_agent("agent-001")

        # Without agent record in state -> audit flags orphaned
        audit = self.port_mgr.audit_ports()
        self.assertFalse(audit["is_healthy"])
        self.assertEqual(len(audit["orphaned"]), 2)

        # Register running agent in state -> audit is healthy
        agent = AgentState(
            id="agent-001",
            name="worker-1",
            seat="SR1",
            lane="backend",
            task="Task",
            branch="parallel/b",
            worktree_path=str(self.root / "wt"),
            status=AgentStatus.RUNNING.value,
        )
        self.state.save_agent(agent)
        audit_healthy = self.port_mgr.audit_ports()
        self.assertTrue(audit_healthy["is_healthy"])
        self.assertEqual(len(audit_healthy["orphaned"]), 0)


if __name__ == "__main__":
    unittest.main()
