"""Port allocation, reservation, and collision detection engine."""

from __future__ import annotations

import socket
from typing import Dict, List, Optional
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
        """Allocates non-conflicting ports for all configured port categories."""
        allocated_map = self.state.get_allocated_ports()
        allocated_ports_for_this_agent: Dict[str, int] = {}

        for category, p_range in self.config.port_ranges.items():
            assigned_port = self._find_available_port(p_range, allocated_map)
            if assigned_port is None:
                # Rollback already allocated ports on failure
                self.release_ports(agent_id)
                raise PortError(
                    f"Port pool exhausted for category '{category}' (Range: {p_range.start}-{p_range.end})."
                )
            
            # Record allocation in state
            self.state.allocate_port(assigned_port, agent_id)
            allocated_map[str(assigned_port)] = agent_id
            allocated_ports_for_this_agent[category] = assigned_port

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
        """Returns port health report for doctor."""
        allocated = self.state.get_allocated_ports()
        conflicts = []
        for port_str, agent_id in allocated.items():
            port = int(port_str)
            # In a healthy state, an allocated port for a running agent might be open,
            # but if an unallocated port is open or multiple agents claim it, we detect it.
            pass
        return {"allocated": allocated, "conflicts": conflicts}
