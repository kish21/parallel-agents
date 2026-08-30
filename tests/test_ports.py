import tempfile
import unittest
from pathlib import Path

from parallel_agents.config import generate_default_config
from parallel_agents.ports import PortError, PortManager
from parallel_agents.state import StateManager


class TestPortManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.config = generate_default_config("PortTestApp")
        self.state = StateManager(self.root)
        self.port_mgr = PortManager(self.config, self.state)

    def tearDown(self):
        self.tmp_dir.cleanup()

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


if __name__ == "__main__":
    unittest.main()
