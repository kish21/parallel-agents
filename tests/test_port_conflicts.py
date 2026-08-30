"""Tests for port ledger conflict detection.

`audit_ports` previously hardcoded `conflicts = []` and never called `is_port_in_use`,
so the ledger/agent-state drift the README advertised as detectable was never detected.
These tests pin the real implementation.
"""

import shutil
import socket
import tempfile
import unittest
from pathlib import Path

from parallel_agents.config import Config
from parallel_agents.ports import PortManager
from parallel_agents.state import AgentState, AgentStatus, StateManager


class PortAuditTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.state = StateManager(self.tmp)
        self.cfg = Config.default("proj")
        self.mgr = PortManager(self.cfg, self.state)

    def _agent(self, agent_id, status=AgentStatus.RUNNING.value, ports=None):
        agent = AgentState(
            id=agent_id, name=agent_id, seat="JR1", lane="backend", task="t",
            branch=f"parallel/{agent_id}/t", worktree_path=str(self.tmp / agent_id),
            status=status, ports=ports or {},
        )
        self.state.save_agent(agent)
        return agent


class TestLedgerDriftIsDetected(PortAuditTestCase):
    def test_clean_ledger_is_healthy(self):
        self._agent("agent-001", ports={"backend": 8001})
        self.state.allocate_port(8001, "agent-001")
        audit = self.mgr.audit_ports(check_os=False)
        self.assertTrue(audit["is_healthy"], audit)
        self.assertEqual(audit["conflicts"], [])
        self.assertEqual(len(audit["active_ports"]), 1)

    def test_port_missing_from_ledger_is_a_conflict(self):
        """An agent serving on an unreserved port: the ledger could re-issue it."""
        self._agent("agent-001", ports={"backend": 8001})
        # deliberately do NOT record it in the ledger
        audit = self.mgr.audit_ports(check_os=False)
        self.assertFalse(audit["is_healthy"])
        self.assertEqual(len(audit["conflicts"]), 1)
        self.assertIn("8001", audit["conflicts"][0])
        self.assertIn("absent from the ledger", audit["conflicts"][0])

    def test_ledger_assigning_port_to_a_different_agent_is_a_conflict(self):
        self._agent("agent-001", ports={"backend": 8001})
        self._agent("agent-002", ports={"backend": 8002})
        self.state.allocate_port(8001, "agent-002")  # wrong owner
        self.state.allocate_port(8002, "agent-002")
        audit = self.mgr.audit_ports(check_os=False)
        self.assertFalse(audit["is_healthy"])
        self.assertTrue(any("agent-001" in c and "agent-002" in c for c in audit["conflicts"]))

    def test_orphaned_port_from_unknown_agent(self):
        self.state.allocate_port(8055, "ghost-agent")
        audit = self.mgr.audit_ports(check_os=False)
        self.assertFalse(audit["is_healthy"])
        self.assertTrue(any("ghost-agent" in o for o in audit["orphaned"]))

    def test_terminal_agent_still_holding_a_port_is_orphaned(self):
        for status in (AgentStatus.STOPPED.value, AgentStatus.FAILED.value,
                       AgentStatus.COMPLETED.value):
            with self.subTest(status=status):
                state = StateManager(self.tmp / status)
                mgr = PortManager(self.cfg, state)
                agent = AgentState(
                    id="agent-001", name="a", seat="JR1", lane="backend", task="t",
                    branch="b", worktree_path="p", status=status, ports={"backend": 8001},
                )
                state.save_agent(agent)
                state.allocate_port(8001, "agent-001")
                audit = mgr.audit_ports(check_os=False)
                self.assertFalse(audit["is_healthy"])
                self.assertTrue(any(status.lower() in o for o in audit["orphaned"]), audit)


class TestOsProbeIsRealNotDecorative(PortAuditTestCase):
    def test_is_port_in_use_detects_a_bound_socket(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            bound_port = srv.getsockname()[1]
            self.assertTrue(PortManager.is_port_in_use(bound_port))
        # After close the port is no longer accepting connections.
        self.assertFalse(PortManager.is_port_in_use(bound_port))

    def test_allocator_skips_a_port_bound_by_a_foreign_process(self):
        """A port nothing reserved, but which an unmanaged process holds, must be skipped."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            bound_port = srv.getsockname()[1]

            cfg = Config.default("proj")
            cfg.port_ranges = {"backend": type(cfg.port_ranges["backend"])(
                start=bound_port, end=bound_port + 2)}
            mgr = PortManager(cfg, self.state)
            allocated = mgr.allocate_ports_for_agent("agent-001")
            self.assertNotEqual(allocated["backend"], bound_port)

    def test_leaked_server_on_an_orphaned_port_is_reported(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            bound_port = srv.getsockname()[1]
            self._agent("agent-001", status=AgentStatus.STOPPED.value)
            self.state.allocate_port(bound_port, "agent-001")
            audit = self.mgr.audit_ports(check_os=True)
            self.assertTrue(any("leaked server" in o for o in audit["orphaned"]), audit["orphaned"])


class TestAllocationRollback(PortAuditTestCase):
    def test_failed_reallocation_does_not_destroy_the_agents_own_reservations(self):
        """Pins the old rollback bug directly.

        The previous implementation called `release_ports(agent_id)` when a category could
        not be satisfied. Nothing had been persisted yet, so that released the agent's
        *existing, valid* reservations from an earlier successful allocation — a failed
        second call silently freed the ports the agent was already serving on, leaving them
        available for another agent to claim.
        """
        rng = type(Config.default("p").port_ranges["backend"])
        good = Config.default("proj")
        good.port_ranges = {"backend": rng(start=8001, end=8010)}
        allocated = PortManager(good, self.state).allocate_ports_for_agent("agent-001")
        self.assertEqual(self.state.get_allocated_ports().get(str(allocated["backend"])), "agent-001")

        # The same agent is re-allocated against a config with an unsatisfiable category.
        broken = Config.default("proj")
        broken.port_ranges = {"backend": rng(start=8001, end=8010),
                              "frontend": rng(start=9001, end=9000)}
        with self.assertRaises(Exception):
            PortManager(broken, self.state).allocate_ports_for_agent("agent-001")

        # The original reservation must survive the failed call.
        self.assertEqual(
            self.state.get_allocated_ports().get(str(allocated["backend"])), "agent-001",
            "a failed re-allocation released the agent's pre-existing ports",
        )

    def test_partial_failure_persists_nothing(self):
        """Category two failing must not leave category one written to the ledger."""
        cfg = Config.default("proj")
        rng = type(cfg.port_ranges["backend"])
        cfg.port_ranges = {"backend": rng(start=8001, end=8010),
                           "frontend": rng(start=9001, end=9000)}  # empty range
        mgr = PortManager(cfg, self.state)
        with self.assertRaises(Exception):
            mgr.allocate_ports_for_agent("agent-001")
        self.assertEqual(self.state.get_allocated_ports(), {})


if __name__ == "__main__":
    unittest.main()
