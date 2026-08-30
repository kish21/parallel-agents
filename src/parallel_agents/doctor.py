"""Health diagnostics and self-repair engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from .adapters.process_adapter import ProcessAdapter
from .config import Config, load_config
from .ports import PortManager
from .state import AgentState, AgentStatus, StateManager
from .worktree import WorktreeManager


@dataclass
class DiagnosticCheck:
    name: str
    passed: bool
    message: str
    details: Optional[str] = None


@dataclass
class DoctorReport:
    checks: List[DiagnosticCheck] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def problem_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)


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
                )
            )
            return report

        # 3. Worktree Integrity Check
        agents = self.state.list_agents()
        git_worktrees = {wt.path.resolve(): wt for wt in self.worktree_mgr.list_worktrees()}

        wt_problems = []
        for a in agents:
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
                    message=f"All {len(agents)} agent worktrees are intact.",
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

        # 4. Port Allocations & Conflicts Check
        port_mgr = PortManager(cfg, self.state)
        allocated_ports = self.state.get_allocated_ports()
        port_problems = []

        agent_map = {a.id: a for a in agents}
        for port_str, assigned_agent in allocated_ports.items():
            if assigned_agent not in agent_map:
                port_problems.append(f"Port {port_str} reserved by non-existent agent '{assigned_agent}'.")

        if not port_problems:
            report.checks.append(
                DiagnosticCheck(
                    name="Port allocations",
                    passed=True,
                    message=f"{len(allocated_ports)} ports allocated cleanly.",
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

        # 5. Agent Process Liveness Check
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

    def repair(self, agent_id_or_name: Optional[str] = None) -> List[str]:
        actions_taken = []
        agents = self.state.list_agents()

        target_agents = [
            a for a in agents if (agent_id_or_name is None or a.id == agent_id_or_name or a.name == agent_id_or_name)
        ]

        # 1. Fix dead process states
        for a in target_agents:
            if a.status == AgentStatus.RUNNING.value and a.pid:
                if not self.adapter.is_alive(a):
                    a.status = AgentStatus.FAILED.value
                    a.pid = None
                    self.state.save_agent(a)
                    actions_taken.append(f"Updated agent '{a.id}' status to FAILED (process had died).")

        # 2. Prune Git worktrees
        self.worktree_mgr.prune()
        actions_taken.append("Pruned stale Git worktree registrations.")

        # 3. Clean orphaned port records
        allocated_ports = self.state.get_allocated_ports()
        all_agent_ids = {a.id for a in self.state.list_agents()}
        for port_str, assigned_agent in list(allocated_ports.items()):
            if assigned_agent not in all_agent_ids:
                self.state.release_ports_for_agent(assigned_agent)
                actions_taken.append(f"Released orphaned port {port_str} (belonged to unknown agent '{assigned_agent}').")

        return actions_taken
