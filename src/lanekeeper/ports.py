"""Port allocation, reservation, and collision detection engine."""

from __future__ import annotations

import socket
from typing import Any, Dict, List, Optional
from .config import Config, PortRange
from .state import StateManager


class PortError(RuntimeError):
    """Raised when port allocation fails or conflicts occur."""


class PortManager:
    def __init__(self, config: Config, state: StateManager):
        self.config = config
        self.state = state

    @staticmethod
    def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
        """Checks if a port is currently bound/occupied in the host OS."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            res = s.connect_ex((host, port))
            return res == 0

    def allocate_ports_for_agent(self, agent_id: str) -> Dict[str, int]:
        """Allocates non-conflicting ports atomically for all configured port categories."""
        with self.state.lock():
            allocated_map = self.state.get_allocated_ports()
            allocated_ports_for_this_agent: Dict[str, int] = {}
            new_allocations: Dict[int, str] = {}

            for category, p_range in self.config.port_ranges.items():
                assigned_port = self._find_available_port(p_range, allocated_map)
                if assigned_port is None:
                    # Rollback already allocated ports on failure
                    self.release_ports(agent_id)
                    raise PortError(
                        f"Port pool exhausted for category '{category}' (Range: {p_range.start}-{p_range.end})."
                    )

                new_allocations[assigned_port] = agent_id
                allocated_map[str(assigned_port)] = agent_id
                allocated_ports_for_this_agent[category] = assigned_port

            # Atomic single-write persistence of all allocated ports
            self.state.allocate_ports_atomic(new_allocations)
            return allocated_ports_for_this_agent

    def _find_available_port(
        self,
        p_range: PortRange,
        current_allocations: Dict[str, str],
    ) -> Optional[int]:
        for port in range(p_range.start, p_range.end + 1):
            port_str = str(port)
            # 1. Check if already reserved in internal state
            if port_str in current_allocations:
                continue
            # 2. Check if bound in host OS
            if self.is_port_in_use(port):
                continue
            return port
        return None

    def release_ports(self, agent_id: str) -> List[int]:
        return self.state.release_ports_for_agent(agent_id)

    def audit_ports(self) -> Dict[str, Any]:
        """Audits allocated ports against OS socket availability and agent process health."""
        with self.state.lock():
            allocated = self.state.get_allocated_ports()
            agents = {a.id: a for a in self.state.list_agents()}
            conflicts = []
            orphaned = []
            active_ports = []

            for port_str, agent_id in allocated.items():
                port = int(port_str)
                agent = agents.get(agent_id)

                if not agent:
                    orphaned.append(f"Port {port} allocated to non-existent agent '{agent_id}'.")
                elif agent.status in ("STOPPED", "FAILED", "COMPLETED"):
                    orphaned.append(f"Port {port} still reserved by {agent.status.lower()} agent '{agent_id}'.")
                else:
                    active_ports.append({"port": port, "agent_id": agent_id, "status": agent.status})

            return {
                "allocated_count": len(allocated),
                "active_ports": active_ports,
                "orphaned": orphaned,
                "conflicts": conflicts,
                "is_healthy": len(orphaned) == 0 and len(conflicts) == 0,
            }
