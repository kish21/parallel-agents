"""Generic process-based AgentAdapter implementation."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import List, Optional
from .base import AgentAdapter
from ..state import AgentState, AgentStatus
from .. import paths



class ProcessAdapter(AgentAdapter):
    """Manages agents executing as background CLI processes or manual seats."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or Path.cwd()
        self.logs_dir = paths.logs_dir(self.root_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_path(self, agent_id: str) -> Path:
        return self.logs_dir / f"{agent_id}.log"

    def is_alive(self, agent: AgentState) -> bool:
        if not agent.pid:
            return False
        try:
            if sys.platform == "win32":
                # Windows PID check
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                SYNCHRONIZE = 0x00100000
                handle = ctypes.windll.kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, agent.pid
                )
                if handle == 0:
                    return False
                exit_code = ctypes.c_ulong()
                ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                ctypes.windll.kernel32.CloseHandle(handle)
                # STILL_ACTIVE = 259
                return exit_code.value == 259
            else:
                # Unix PID check
                os.kill(agent.pid, 0)
                return True
        except Exception:
            return False

    def start(
        self,
        agent: AgentState,
        worktree_path: Path,
        command: Optional[str] = None,
    ) -> AgentState:
        log_path = self._get_log_path(agent.id)

        if command:
            with open(log_path, "a", encoding="utf-8") as log_f:
                log_f.write(f"\n--- Starting Agent {agent.id} ({command}) ---\n")
                proc = subprocess.Popen(
                    command,
                    cwd=worktree_path,
                    shell=True,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                )
                agent.pid = proc.pid
                agent.status = AgentStatus.RUNNING.value
        else:
            # Standalone seat waiting for developer or IDE connection
            with open(log_path, "a", encoding="utf-8") as log_f:
                log_f.write(
                    f"\n--- Agent {agent.id} initialized in {worktree_path} (Ready for IDE/CLI session) ---\n"
                )
            agent.pid = None
            agent.status = AgentStatus.RUNNING.value

        return agent

    def stop(self, agent: AgentState) -> AgentState:
        if agent.pid and self.is_alive(agent):
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(agent.pid)], capture_output=True)
                else:
                    os.kill(agent.pid, signal.SIGTERM)
            except Exception:
                pass

        agent.pid = None
        agent.status = AgentStatus.STOPPED.value
        log_path = self._get_log_path(agent.id)
        if log_path.exists():
            with open(log_path, "a", encoding="utf-8") as log_f:
                log_f.write(f"\n--- Agent {agent.id} stopped ---\n")
        return agent

    def restart(self, agent: AgentState, worktree_path: Path) -> AgentState:
        self.stop(agent)
        return self.start(agent, worktree_path)

    def get_logs(self, agent: AgentState, tail: int = 50) -> List[str]:
        log_path = self._get_log_path(agent.id)
        if not log_path.exists():
            return [f"No logs recorded yet for agent {agent.id}."]
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                return [line.rstrip() for line in lines[-tail:]]
        except Exception as e:
            return [f"Error reading logs for {agent.id}: {e}"]
