import tempfile
import unittest
from pathlib import Path

from lanekeeper.config import generate_default_config
from lanekeeper.ports import PortManager
from lanekeeper.state import AgentState, AgentStatus, StateManager


class TestPortAudit(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.config = generate_default_config("PortAuditApp")
        self.state = StateManager(self.root)
        self.port_mgr = PortManager(self.config, self.state)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_port_audit(self):
        """Proves PortManager.audit_ports() flags orphaned and dead allocations and validates healthy ones."""
        # 1. Allocate ports without agent state -> audit detects orphaned
        self.port_mgr.allocate_ports_for_agent("agent-001")
        audit = self.port_mgr.audit_ports()
        self.assertFalse(audit["is_healthy"])
        self.assertEqual(len(audit["orphaned"]), 2)
        self.assertIn("non-existent agent 'agent-001'", audit["orphaned"][0])

        # 2. Register agent as RUNNING -> audit becomes healthy
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
        self.assertEqual(audit_healthy["allocated_count"], 2)

        # 3. Mark agent as FAILED -> audit flags reserved port by failed agent
        agent.status = AgentStatus.FAILED.value
        self.state.save_agent(agent)
        audit_failed = self.port_mgr.audit_ports()
        self.assertFalse(audit_failed["is_healthy"])
        self.assertEqual(len(audit_failed["orphaned"]), 2)
        self.assertIn("reserved by failed agent 'agent-001'", audit_failed["orphaned"][0])


if __name__ == "__main__":
    unittest.main()
