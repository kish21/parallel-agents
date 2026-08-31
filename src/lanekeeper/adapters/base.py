"""Abstract AgentAdapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional
from ..state import AgentState, AgentStatus


class AgentAdapter(ABC):
    """Abstract interface for managing agent processes and harnesses."""

    @abstractmethod
    def start(
        self,
        agent: AgentState,
        worktree_path: Path,
        command: Optional[str] = None,
    ) -> AgentState:
        """Starts an agent process in its designated worktree."""
        pass

    @abstractmethod
    def stop(self, agent: AgentState) -> AgentState:
        """Stops a running agent process."""
        pass

    @abstractmethod
    def restart(self, agent: AgentState, worktree_path: Path) -> AgentState:
        """Restarts an agent process."""
        pass

    @abstractmethod
    def is_alive(self, agent: AgentState) -> bool:
        """Checks if the agent process is currently running."""
        pass

    @abstractmethod
    def get_logs(self, agent: AgentState, tail: int = 50) -> List[str]:
        """Retrieves recent logs for the agent."""
        pass
