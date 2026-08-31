"""Port allocation, reservation, and collision detection engine."""

from __future__ import annotations

import socket
from typing import Any, Dict, List, Optional
from .config import Config, PortRange
from .state import AgentStatus, StateManager

# Agent statuses that mean "this agent is finished and must not hold reservations".
TERMINAL_STATUSES = (
    AgentStatus.STOPPED.value,
    AgentStatus.FAILED.value,
    AgentStatus.COMPLETED.value,
)


class PortError(RuntimeError):
    """Raised when port allocation fails or conflicts occur."""


class PortManager:
    def __init__(self, config: Config, state: StateManager):
        self.config = config
        self.state = state

    @staticmethod
    def is_port_in_use(port: int, host: str = "127.0.0.1", timeout: float = 0.2) -> bool:
        """Checks if a port currently accepts TCP connections on the given host.

        This is a liveness probe, not a reservation. A free result is a point-in-time
        observation: another process can bind the port immediately afterwards. The
        authoritative reservation is the ledger in ``ports.json``, which is written under
        the state lock; this probe only avoids handing out a port that is *visibly* taken.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0

    def allocate_ports_for_agent(self, agent_id: str) -> Dict[str, int]:
        """Allocates non-conflicting ports atomically for all configured port categories.

        Either every category is reserved and persisted in a single write, or nothing is
        persisted at all — the ledger is only touched once the full set is resolved.
        """
        with self.state.lock():
            allocated_map = self.state.get_allocated_ports()
            allocated_ports_for_this_agent: Dict[str, int] = {}
            new_allocations: Dict[int, str] = {}

            for category, p_range in self.config.port_ranges.items():
                assigned_port = self._find_available_port(p_range, allocated_map)
                if assigned_port is None:
                    # Nothing has been written to the ledger yet, so abandoning the
                    # in-memory maps *is* the rollback. Calling release_ports() here would
                    # be actively wrong: it would delete this agent's pre-existing, valid
                    # reservations from an earlier successful allocation.
                    raise PortError(
                        f"Port pool exhausted for category '{category}' "
                        f"(Range: {p_range.start}-{p_range.end})."
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
            # 1. Check if already reserved in the ledger
            if str(port) in current_allocations:
                continue
            # 2. Check if bound in the host OS by an unmanaged process
            if self.is_port_in_use(port):
                continue
            return port
        return None

    def release_ports(self, agent_id: str) -> List[int]:
        return self.state.release_ports_for_agent(agent_id)

    def audit_ports(self, check_os: bool = True) -> Dict[str, Any]:
        """Audits the port ledger against agent state and live OS socket occupancy.

        Returns three problem classes:

        * ``orphaned`` — a reservation held by an agent that no longer exists or has
          reached a terminal status. When ``check_os`` is set, a reservation whose port is
          still bound is reported as a leaked process rather than a stale record.
        * ``conflicts`` — the ledger and the agents' own recorded ports disagree. This is
          the dangerous class: it means a port could be handed to a second agent.
        * ``active_ports`` — healthy reservations held by live agents.

        ``check_os`` performs one TCP probe per reserved port; disable it for fast,
        purely-logical audits.
        """
        with self.state.lock():
            allocated = self.state.get_allocated_ports()
            agents = {a.id: a for a in self.state.list_agents()}
            conflicts: List[str] = []
            orphaned: List[str] = []
            active_ports: List[Dict[str, Any]] = []

            for port_str, agent_id in sorted(allocated.items(), key=lambda kv: int(kv[0])):
                port = int(port_str)
                agent = agents.get(agent_id)
                bound = self.is_port_in_use(port) if check_os else False

                if not agent:
                    orphaned.append(
                        f"Port {port} allocated to non-existent agent '{agent_id}'"
                        + (" and is still bound by a live process." if bound else ".")
                    )
                elif agent.metadata.get("cleanup_failed"):
                    # Held back on purpose: this agent's worktree could not be removed, so
                    # its reservation is the opposite of stale. Reporting it as an orphan
                    # would invite a repair that hands a port back while it is still being
                    # served. The situation is reported once, by the doctor's cleanup check.
                    active_ports.append(
                        {"port": port, "agent_id": agent_id, "status": agent.status, "bound": bound}
                    )
                elif agent.status in TERMINAL_STATUSES:
                    detail = (
                        f"Port {port} still reserved by {agent.status.lower()} agent '{agent_id}'"
                    )
                    orphaned.append(
                        detail + (" and is still bound by a live process (leaked server)." if bound else ".")
                    )
                else:
                    active_ports.append(
                        {"port": port, "agent_id": agent_id, "status": agent.status, "bound": bound}
                    )

            # Cross-check: every port an agent believes it owns must be reserved to it in
            # the ledger. Drift here means the ledger could re-issue a port that an agent
            # is already serving on.
            for agent in agents.values():
                # A finished agent's recorded ports are history, not a claim. Once its
                # reservations are released the two records legitimately differ, and
                # reporting that as drift would make the release itself un-auditable.
                if agent.status in TERMINAL_STATUSES:
                    continue
                for category, port in agent.ports.items():
                    ledger_owner = allocated.get(str(port))
                    if ledger_owner is None:
                        conflicts.append(
                            f"Port {port} ({category}) is used by agent '{agent.id}' but is "
                            f"absent from the ledger; it may be re-issued to another agent."
                        )
                    elif ledger_owner != agent.id:
                        conflicts.append(
                            f"Port {port} ({category}) is recorded by agent '{agent.id}' but "
                            f"the ledger assigns it to '{ledger_owner}'."
                        )

            return {
                "allocated_count": len(allocated),
                "active_ports": active_ports,
                "orphaned": orphaned,
                "conflicts": conflicts,
                "is_healthy": not orphaned and not conflicts,
            }
