"""Unit tests for PortManager and collision prevention."""

import tempfile
import unittest
from pathlib import Path
from parallel_agents.config import Config, PortRange
from parallel_agents.ports import PortError, PortManager
from parallel_agents.state import StateManager


class TestPortManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.state = StateManager(self.root)
        self.config = Config(
            port_ranges={
                "backend": PortRange(start=8001, end=8003),
                "frontend": PortRange(start=3001, end=3003),
            }
        )
        self.port_mgr = PortManager(self.config, self.state)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_allocate_ports_success(self):
        ports_1 = self.port_mgr.allocate_ports_for_agent("agent-001")
        self.assertEqual(ports_1["backend"], 8001)
        self.assertEqual(ports_1["frontend"], 3001)

        ports_2 = self.port_mgr.allocate_ports_for_agent("agent-002")
        self.assertEqual(ports_2["backend"], 8002)
        self.assertEqual(ports_2["frontend"], 3002)

        # Verify state persistence
        allocated = self.state.get_allocated_ports()
        self.assertEqual(allocated["8001"], "agent-001")
        self.assertEqual(allocated["3001"], "agent-001")
        self.assertEqual(allocated["8002"], "agent-002")
        self.assertEqual(allocated["3002"], "agent-002")

    def test_release_ports(self):
        self.port_mgr.allocate_ports_for_agent("agent-001")
        released = self.port_mgr.release_ports("agent-001")
        self.assertEqual(sorted(released), [3001, 8001])

        # Next allocation can re-use 8001
        ports_new = self.port_mgr.allocate_ports_for_agent("agent-002")
        self.assertEqual(ports_new["backend"], 8001)
        self.assertEqual(ports_new["frontend"], 3001)

    def test_port_exhaustion_raises_error(self):
        self.port_mgr.allocate_ports_for_agent("agent-001")  # 8001
        self.port_mgr.allocate_ports_for_agent("agent-002")  # 8002
        self.port_mgr.allocate_ports_for_agent("agent-003")  # 8003

        with self.assertRaises(PortError):
            self.port_mgr.allocate_ports_for_agent("agent-004")  # Pool exhausted


if __name__ == "__main__":
    unittest.main()
