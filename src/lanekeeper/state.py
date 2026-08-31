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

STATE_DIR = Path(".lanekeeper/state")
AGENTS_FILE = STATE_DIR / "agents.json"
PORTS_FILE = STATE_DIR / "ports.json"


class StateManager:
    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or Path.cwd()
        self.state_dir = self.root_dir / STATE_DIR
        self.agents_file = self.root_dir / AGENTS_FILE
        self.ports_file = self.root_dir / PORTS_FILE
        self._ensure_storage()

    def lock(self) -> StateLock:
        return StateLock(self.state_dir)

    def _ensure_storage(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if not self.agents_file.exists():
            self._write_json(self.agents_file, {})
        if not self.ports_file.exists():
            self._write_json(self.ports_file, {})

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

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
        """Atomically finds and reserves the next sequential agent ID under the state lock."""
        with self.lock():
            data = self._read_json(self.agents_file)
            existing_ids = set(data.keys())
            idx = 1
            while f"agent-{idx:03d}" in existing_ids:
                idx += 1
            return f"agent-{idx:03d}"

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
