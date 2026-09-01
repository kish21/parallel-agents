"""State persistence and agent lifecycle tracking."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class AgentStatus(str, Enum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"


@dataclass
class AgentState:
    id: str
    name: str
    seat: str
    lane: str
    task: str
    branch: str
    worktree_path: str
    status: str = AgentStatus.CREATED.value
    ports: Dict[str, int] = field(default_factory=dict)
    pid: Optional[int] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentState:
        return cls(**data)


from .lock import StateLock
from . import paths

AGENTS_FILENAME = "agents.json"
PORTS_FILENAME = "ports.json"
COUNTER_FILENAME = "counter.json"


class StateCorruptError(RuntimeError):
    """Raised when a state file exists but cannot be read as the record it should be.

    It used to be read as empty. That is the most dangerous possible reading: an
    unreadable ``ports.json`` meant every port was free, and the next ``save_agent``
    wrote a ledger containing one agent over the top of the file that had held four.
    """


class StateManager:
    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or Path.cwd()
        self.state_dir = paths.state_dir(self.root_dir)
        self.agents_file = self.state_dir / AGENTS_FILENAME
        self.ports_file = self.state_dir / PORTS_FILENAME
        self.counter_file = self.state_dir / COUNTER_FILENAME
        self._ensure_storage()

    def lock(self) -> StateLock:
        """Serialises reads and writes of the JSON state files."""
        return StateLock(self.state_dir)

    def git_lock(self) -> StateLock:
        """Serialises repository-mutating git commands (worktree and branch creation).

        Deliberately a *different* lock file from ``lock()``. Git worktree creation
        mutates shared repository state (refs, the index, .git/worktrees) and is not safe
        to run concurrently against one repository, but it is slow — holding the state
        lock across it would block every `status` and `validate` for its duration.
        """
        return StateLock(self.state_dir, lock_name=".git.lock", timeout_seconds=120.0)

    def _ensure_storage(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if not self.agents_file.exists():
            self._write_json(self.agents_file, {})
        if not self.ports_file.exists():
            self._write_json(self.ports_file, {})

    @staticmethod
    def _read_json(path: Path, strict: bool = True) -> Dict[str, Any]:
        """Reads a state file. A missing file is empty; a damaged one is an error.

        ``strict=False`` is for a file whose contents are advisory and reconciled
        against another source on every read (the id counter). The agent and port
        ledgers are never read that way.
        """
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            if not strict:
                return {}
            raise StateCorruptError(
                f"{path} cannot be read ({e}). Nothing was changed. Restore it from the "
                f"copy you trust, or if it is empty, delete it and run 'lanekeeper repair'."
            ) from e
        if not isinstance(data, dict):
            if not strict:
                return {}
            raise StateCorruptError(
                f"{path} does not hold a record (found {type(data).__name__}). "
                f"Nothing was changed.")
        return data

    @staticmethod
    def _write_json(path: Path, data: Dict[str, Any]) -> None:
        import uuid
        temp_path = path.parent / f"{path.name}.{uuid.uuid4().hex}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_path.replace(path)

    def get_agent(self, agent_id_or_name: str) -> Optional[AgentState]:
        agents = self.list_agents()
        for agent in agents:
            if agent.id == agent_id_or_name or agent.name == agent_id_or_name:
                return agent
        return None

    def list_agents(self) -> List[AgentState]:
        with self.lock():
            data = self._read_json(self.agents_file)
            return [AgentState.from_dict(val) for val in data.values()]

    def save_agent(self, agent: AgentState) -> None:
        with self.lock():
            agent.updated_at = datetime.now(timezone.utc).isoformat()
            data = self._read_json(self.agents_file)
            data[agent.id] = agent.to_dict()
            self._write_json(self.agents_file, data)

    def remove_agent(self, agent_id: str) -> bool:
        with self.lock():
            data = self._read_json(self.agents_file)
            if agent_id in data:
                del data[agent_id]
                self._write_json(self.agents_file, data)
                return True
            return False

    def allocate_next_agent_id(self) -> str:
        """Atomically reserves the next agent ID under the state lock.

        Monotonic: an ID is never reused, even after the agent that held it is removed
        from state. Reuse looked harmless while every id was a dictionary key, but an
        agent id also names a directory. When a `cleanup` failed to delete a worktree —
        a running dev server holding a file open is enough on Windows — and removed the
        state record anyway, the next spawn drew the same id, resolved the same path, and
        `git worktree add` failed on a directory that already existed. Nothing in state
        referred to that directory any more, so `doctor` could not see it and `repair`
        could not clear it: spawning stayed broken until someone deleted it by hand.

        The high-water mark is persisted, and reconciled against the ids currently in
        state on every call, so a missing or truncated counter file can only ever cause
        the sequence to resume — never to go backwards.
        """
        with self.lock():
            agents = self._read_json(self.agents_file)
            counter = self._read_json(self.counter_file, strict=False)

            try:
                last_issued = int(counter.get("last_agent_index", 0))
            except (TypeError, ValueError):
                last_issued = 0

            highest_in_state = 0
            for agent_id in agents:
                _, _, suffix = str(agent_id).rpartition("-")
                if suffix.isdigit():
                    highest_in_state = max(highest_in_state, int(suffix))

            next_index = max(last_issued, highest_in_state) + 1
            self._write_json(self.counter_file, {"last_agent_index": next_index})
            return f"agent-{next_index:03d}"

    def get_allocated_ports(self) -> Dict[str, str]:
        """Returns map of port_number (str) -> agent_id."""
        with self.lock():
            data = self._read_json(self.ports_file)
            return {str(k): str(v) for k, v in data.items()}

    def allocate_port(self, port: int, agent_id: str) -> None:
        with self.lock():
            data = self._read_json(self.ports_file)
            data[str(port)] = agent_id
            self._write_json(self.ports_file, data)

    def allocate_ports_atomic(self, port_map: Dict[int, str]) -> None:
        """Atomically records multiple port allocations in a single disk write under the lock."""
        with self.lock():
            data = self._read_json(self.ports_file)
            for port, agent_id in port_map.items():
                data[str(port)] = agent_id
            self._write_json(self.ports_file, data)

    def release_ports_for_agent(self, agent_id: str) -> List[int]:
        with self.lock():
            data = self._read_json(self.ports_file)
            released = []
            new_data = {}
            for port_str, assigned_agent in data.items():
                if assigned_agent == agent_id:
                    released.append(int(port_str))
                else:
                    new_data[port_str] = assigned_agent
            self._write_json(self.ports_file, new_data)
            return released
