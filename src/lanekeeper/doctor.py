"""Health diagnostics and self-repair engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from .adapters.process_adapter import ProcessAdapter
from .capabilities import CapabilityRegistry
from .config import Config, load_config
from .ports import PortManager, TERMINAL_STATUSES
from .state import AgentState, AgentStatus, StateManager
from .worktree import WorktreeManager


@dataclass
class DiagnosticCheck:
    name: str
    passed: bool
    message: str
    details: Optional[str] = None
    #: Whether `repair` can actually resolve this. A check that reports a problem only a
    #: human can decide on must not tell the operator to run a command that will report
    #: success and change nothing — that loop is what made the previous doctor useless.
    repairable: bool = True


@dataclass
class DoctorReport:
    checks: List[DiagnosticCheck] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def problem_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    @property
    def has_repairable_problems(self) -> bool:
        return any(not c.passed and c.repairable for c in self.checks)


class Doctor:
    def __init__(
        self,
        root_dir: Optional[Path] = None,
        config: Optional[Config] = None,
        state: Optional[StateManager] = None,
    ):
        self.root_dir = root_dir or Path.cwd()
        self.config = config
        self.state = state or StateManager(self.root_dir)
        self.worktree_mgr = WorktreeManager(self.root_dir)
        self.adapter = ProcessAdapter(self.root_dir)

    def diagnose(self) -> DoctorReport:
        report = DoctorReport()

        # 1. Git Repository Check
        if self.worktree_mgr.is_git_repo():
            report.checks.append(
                DiagnosticCheck(
                    name="Git repository",
                    passed=True,
                    message="Valid Git repository detected.",
                )
            )
        else:
            report.checks.append(
                DiagnosticCheck(
                    name="Git repository",
                    passed=False,
                    message="Not inside a valid Git repository.",
                )
            )

        # 2. Configuration Check
        try:
            cfg = self.config or load_config(self.root_dir)
            report.checks.append(
                DiagnosticCheck(
                    name="Configuration",
                    passed=True,
                    message=f"Valid config (Project: {cfg.project_name}, Max agents: {cfg.max_agents}).",
                )
            )
        except Exception as e:
            report.checks.append(
                DiagnosticCheck(
                    name="Configuration",
                    passed=False,
                    message=f"Configuration error: {e}",
                    # `repair` reconciles agent state and ports, both of which need a
                    # configuration to load. Offering it here sent a first-time user to
                    # a command that cannot create the very file that is missing.
                    repairable=False,
                )
            )
            return report

        # 3. Worktree Integrity Check
        agents = self.state.list_agents()
        git_worktrees = {wt.path.resolve(): wt for wt in self.worktree_mgr.list_worktrees()}

        # Only live agents are expected to have a worktree. A STOPPED or FAILED agent
        # whose directory is gone is a finished agent, not a fault; reporting it as one
        # left `doctor` permanently red with nothing anyone could do about it.
        live_agents = [a for a in agents if a.status not in TERMINAL_STATUSES]

        wt_problems = []
        for a in live_agents:
            wt_path = Path(a.worktree_path).resolve()
            if not wt_path.exists():
                wt_problems.append(f"Agent '{a.id}' worktree missing on disk: {wt_path}")
            elif wt_path not in git_worktrees:
                wt_problems.append(f"Agent '{a.id}' worktree folder exists but is not registered in Git.")

        if not wt_problems:
            report.checks.append(
                DiagnosticCheck(
                    name="Worktrees",
                    passed=True,
                    message=f"All {len(live_agents)} active agent worktrees are intact.",
                )
            )
        else:
            report.checks.append(
                DiagnosticCheck(
                    name="Worktrees",
                    passed=False,
                    message=f"{len(wt_problems)} worktree issue(s) detected.",
                    details="\n".join(wt_problems),
                )
            )

        # 3b. Directories under the worktree root that no agent claims.
        #
        # These are invisible to every other check precisely because nothing in state
        # names them, and a leftover directory blocks the next spawn that resolves to the
        # same path. Reported, never deleted: it may hold uncommitted work.
        orphan_dirs = self.orphan_worktree_dirs(cfg, agents)
        if not orphan_dirs:
            report.checks.append(
                DiagnosticCheck(
                    name="Worktree directory",
                    passed=True,
                    message="No unclaimed directories under the worktree root.",
                )
            )
        else:
            details = [
                f"{d} belongs to no agent. It may hold uncommitted work, so lanekeeper "
                f"will not delete it — review it and remove it yourself."
                for d in orphan_dirs
            ]
            report.checks.append(
                DiagnosticCheck(
                    name="Worktree directory",
                    passed=False,
                    message=f"{len(orphan_dirs)} unclaimed directory/directories under the worktree root.",
                    details="\n".join(details),
                    repairable=False,
                )
            )

        # 3c. Agents whose cleanup could not finish.
        #
        # Reported on its own rather than folded into the port or worktree checks, because
        # the resolution is neither of theirs: something outside lanekeeper is holding a
        # file open, and only the operator can stop it.
        unfinished = [a for a in agents if a.metadata.get("cleanup_failed")]
        if not unfinished:
            report.checks.append(
                DiagnosticCheck(
                    name="Cleanup", passed=True, message="No agent has an unfinished cleanup.",
                )
            )
        else:
            details = []
            for a in unfinished:
                bound = sorted(p for p in a.ports.values() if PortManager.is_port_in_use(p))
                note = f" Port(s) {', '.join(str(p) for p in bound)} are still being served." if bound else ""
                details.append(
                    f"Agent '{a.id}' could not be cleaned up: {a.metadata['cleanup_failed']}."
                    f"{note} Its worktree and ports were kept. Stop whatever is running in "
                    f"{a.worktree_path}, then run 'lanekeeper cleanup {a.id} --force' again."
                )
            report.checks.append(
                DiagnosticCheck(
                    name="Cleanup",
                    passed=False,
                    message=f"{len(unfinished)} agent(s) have an unfinished cleanup.",
                    details="\n".join(details),
                    repairable=False,
                )
            )

        # 4. Port Allocations & Conflicts Check
        port_mgr = PortManager(cfg, self.state)
        port_audit = port_mgr.audit_ports()
        port_problems = port_audit.get("orphaned", []) + port_audit.get("conflicts", [])

        if not port_problems:
            report.checks.append(
                DiagnosticCheck(
                    name="Port allocations",
                    passed=True,
                    message=f"{port_audit.get('allocated_count', 0)} ports allocated cleanly.",
                )
            )
        else:
            report.checks.append(
                DiagnosticCheck(
                    name="Port allocations",
                    passed=False,
                    message=f"{len(port_problems)} port allocation issue(s) detected.",
                    details="\n".join(port_problems),
                )
            )

        # 5. Capability Card Health
        #
        # A configured gate that cannot be evaluated is worse than no gate: it blocks work
        # without expressing a policy. These checks catch the ways that happens.
        try:
            registry = CapabilityRegistry.load(self.root_dir)
            card_problems = []

            if cfg.capability_gates and registry.is_empty:
                card_problems.append(
                    f"{len(cfg.capability_gates)} capability gate(s) configured but no cards declared; "
                    f"every validation will fail closed.")

            for a in agents:
                if cfg.capability_gates and not registry.has_seat(a.seat):
                    card_problems.append(f"Agent '{a.id}' has seat '{a.seat}' with no capability card.")

            for seat, card in registry.cards.items():
                for lane in card.max_allowed_lane_scope:
                    if lane not in cfg.lanes:
                        card_problems.append(
                            f"Seat '{seat}' scope names lane '{lane}', which is not declared in config.")
                for gate_name in cfg.capability_gates:
                    if not card.declares(gate_name):
                        card_problems.append(
                            f"Seat '{seat}' does not rate '{gate_name}'; it is treated as unavailable.")

            # A lane no seat may enter cannot be worked at all.
            if registry.cards:
                for lane in cfg.lanes:
                    if not any(c.allows_lane(lane) for c in registry.cards.values()):
                        card_problems.append(f"No declared seat is permitted in lane '{lane}'.")

            if not card_problems:
                msg = (f"{len(registry)} capability card(s), {len(cfg.capability_gates)} gate(s) consistent."
                       if registry.cards else "No capability gates or cards configured.")
                report.checks.append(DiagnosticCheck(name="Capability cards", passed=True, message=msg))
            else:
                report.checks.append(DiagnosticCheck(
                    name="Capability cards", passed=False,
                    message=f"{len(card_problems)} capability card issue(s) detected.",
                    details="\n".join(card_problems)))
        except Exception as e:
            report.checks.append(DiagnosticCheck(
                name="Capability cards", passed=False, message=f"Capability card error: {e}"))

        # 6. Agent Process Liveness Check
        proc_problems = []
        for a in agents:
            if a.status == AgentStatus.RUNNING.value and a.pid:
                if not self.adapter.is_alive(a):
                    proc_problems.append(f"Agent '{a.id}' marked RUNNING but PID {a.pid} is dead.")

        if not proc_problems:
            report.checks.append(
                DiagnosticCheck(
                    name="Agent processes",
                    passed=True,
                    message="All active agent process states are consistent.",
                )
            )
        else:
            report.checks.append(
                DiagnosticCheck(
                    name="Agent processes",
                    passed=False,
                    message=f"{len(proc_problems)} stale process state(s) detected.",
                    details="\n".join(proc_problems),
                )
            )

        return report

    def orphan_worktree_dirs(self, cfg: Config, agents: List[AgentState]) -> List[Path]:
        """Directories under the worktree root that no agent in state claims."""
        root = (self.root_dir / cfg.worktree_dir)
        if not root.is_dir():
            return []
        claimed = {Path(a.worktree_path).resolve() for a in agents}
        try:
            children = sorted(p for p in root.iterdir() if p.is_dir())
        except OSError:
            return []
        return [p for p in children if p.resolve() not in claimed]

    def repair(self, agent_id_or_name: Optional[str] = None) -> List[str]:
        """Brings state back in line with the machine, and converges.

        The previous version reported success while leaving `doctor` red, and in one case
        made things worse: marking a dead agent FAILED turned its live port reservations
        into orphans, which step 3 then declined to release because it only considered
        agents missing from state entirely. `doctor` said "run repair", repair said
        "complete", and nothing ever changed. Every state this pass can create, it now
        also resolves — so a second run is a no-op and the only problems `doctor` still
        reports afterwards are the ones it explicitly marks as not repairable.
        """
        actions_taken = []
        agents = self.state.list_agents()

        def targeted(agent: AgentState) -> bool:
            return (agent_id_or_name is None
                    or agent.id == agent_id_or_name
                    or agent.name == agent_id_or_name)

        target_agents = [a for a in agents if targeted(a)]

        # 1. Fix dead process states
        for a in target_agents:
            if a.status == AgentStatus.RUNNING.value and a.pid:
                if not self.adapter.is_alive(a):
                    a.status = AgentStatus.FAILED.value
                    a.pid = None
                    self.state.save_agent(a)
                    actions_taken.append(f"Updated agent '{a.id}' status to FAILED (process had died).")

        # 2. Reconcile agents whose worktree is gone. A live agent with no working
        # directory cannot do anything; leaving it RUNNING kept doctor red forever.
        for a in target_agents:
            if a.status in TERMINAL_STATUSES or a.metadata.get("cleanup_failed"):
                continue
            if not Path(a.worktree_path).exists():
                a.status = AgentStatus.FAILED.value
                a.pid = None
                self.state.save_agent(a)
                actions_taken.append(
                    f"Updated agent '{a.id}' status to FAILED (worktree no longer on disk).")

        # 3. Prune Git worktrees (repository-mutating: serialise with spawn/cleanup)
        with self.state.git_lock():
            self.worktree_mgr.prune()
        actions_taken.append("Pruned stale Git worktree registrations.")

        # 4. Release every reservation no live agent is entitled to: ports belonging to an
        # agent that no longer exists, and ports still held by one that has finished.
        # These are the same class of leak and must be cleared in the same pass that can
        # create them, or repair cannot converge.
        remaining = {a.id: a for a in self.state.list_agents()}
        for port_str, assigned_agent in sorted(self.state.get_allocated_ports().items()):
            agent = remaining.get(assigned_agent)
            if agent is None:
                released = self.state.release_ports_for_agent(assigned_agent)
                if released:
                    actions_taken.append(
                        f"Released port(s) {', '.join(str(p) for p in sorted(released))} "
                        f"(belonged to unknown agent '{assigned_agent}').")
            elif agent.metadata.get("cleanup_failed"):
                # Deliberately retained; see cmd_cleanup. Handing this port back while its
                # worktree still exists is the exact leak the retention prevents.
                continue
            elif agent.status in TERMINAL_STATUSES and targeted(agent):
                released = self.state.release_ports_for_agent(assigned_agent)
                if released:
                    # Clear the agent's own record too. The ledger and the agent must
                    # agree, or the next audit reports the difference as a conflict —
                    # trading one permanent complaint for another.
                    agent.ports = {}
                    self.state.save_agent(agent)
                    actions_taken.append(
                        f"Released port(s) {', '.join(str(p) for p in sorted(released))} "
                        f"held by {agent.status.lower()} agent '{assigned_agent}'.")

        return actions_taken
