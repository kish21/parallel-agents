"""Configuration management for parallel-agents."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml


class UnknownLaneError(KeyError):
    """Raised when a lane is referenced that is not declared in the configuration.

    Lane lookup fails closed: an undeclared lane is a configuration error, never a
    silently-permissive lane. See ``Config.get_lane``.
    """

    def __init__(self, lane_name: str, known_lanes: List[str]):
        self.lane_name = lane_name
        self.known_lanes = sorted(known_lanes)
        known = ", ".join(self.known_lanes) if self.known_lanes else "(none declared)"
        super().__init__(
            f"Unknown lane '{lane_name}'. Declared lanes: {known}."
        )

    def __str__(self) -> str:
        # KeyError.__str__ wraps the message in repr quotes; restore the plain text.
        return self.args[0]


@dataclass
class LaneConfig:
    name: str
    allow: List[str] = field(default_factory=list)
    deny: List[str] = field(default_factory=list)


@dataclass
class PortRange:
    start: int
    end: int


@dataclass
class DatabaseConfig:
    strategy: str = "per-agent"
    name_template: str = "app_${AGENT_ID}"


@dataclass
class QualityCommand:
    """A quality command, optionally satisfying a capability gate.

    `satisfies` is what makes the `author-required` state meaningful: a seat that cannot
    perform a capability natively may still proceed if the verified script written for it
    ran and passed.
    """

    command: str
    satisfies: Optional[str] = None


@dataclass
class QualityConfig:
    commands: List[QualityCommand] = field(default_factory=list)

    def satisfying(self, capability: str) -> List[QualityCommand]:
        return [c for c in self.commands if c.satisfies == capability]


@dataclass
class CapabilityGate:
    """Paths whose modification requires a named capability."""

    capability: str
    paths: List[str] = field(default_factory=list)


@dataclass
class GitConfig:
    protected_branches: List[str] = field(default_factory=lambda: ["main", "master"])
    branch_prefix: str = "parallel/"


@dataclass
class Config:
    version: int = 1
    project_name: str = "parallel-project"
    max_agents: int = 4
    worktree_dir: str = ".parallel-agents/worktrees"
    lanes: Dict[str, LaneConfig] = field(default_factory=dict)
    port_ranges: Dict[str, PortRange] = field(default_factory=dict)
    git: GitConfig = field(default_factory=GitConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    capability_gates: Dict[str, CapabilityGate] = field(default_factory=dict)

    def get_lane(self, lane_name: str) -> LaneConfig:
        """Returns the declared lane, or raises UnknownLaneError.

        This is the only supported way to resolve a lane. It deliberately has no
        permissive fallback: an unrecognised lane must stop the operation rather
        than produce a lane that allows every path.
        """
        lane = self.lanes.get(lane_name)
        if lane is None:
            raise UnknownLaneError(lane_name, list(self.lanes.keys()))
        return lane

    def has_lane(self, lane_name: str) -> bool:
        return lane_name in self.lanes

    @classmethod
    def default(cls, project_name: str = "my-project") -> Config:
        return cls(
            version=1,
            project_name=project_name,
            max_agents=4,
            worktree_dir=".parallel-agents/worktrees",
            lanes={
                "backend": LaneConfig(
                    name="backend",
                    allow=["backend/**", "src/backend/**", "app/**", "tests/backend/**"],
                    deny=["frontend/**", "src/frontend/**", "infra/**", "secrets/**", ".github/**"],
                ),
                "frontend": LaneConfig(
                    name="frontend",
                    allow=["frontend/**", "src/frontend/**", "web/**", "tests/frontend/**"],
                    deny=["backend/**", "src/backend/**", "database/migrations/**", "infra/**"],
                ),
                "data": LaneConfig(
                    name="data",
                    allow=["database/**", "migrations/**", "models/**"],
                    deny=["frontend/**"],
                ),
                "platform": LaneConfig(
                    name="platform",
                    allow=["infra/**", "scripts/**", ".github/**"],
                    deny=[],
                ),
            },
            port_ranges={
                "backend": PortRange(start=8001, end=8099),
                "frontend": PortRange(start=3001, end=3099),
            },
            git=GitConfig(
                protected_branches=["main", "master"],
                branch_prefix="parallel/",
            ),
            quality=QualityConfig(commands=[]),
            database=DatabaseConfig(strategy="per-agent", name_template="app_${AGENT_ID}"),
            # The mechanical form of the rule in 01-working-agreement.md: stop when the
            # change touches money, auth, tenant isolation, or a migration.
            capability_gates={
                "security_review": CapabilityGate(
                    capability="security_review",
                    paths=["**/auth/**", "**/authentication/**", "**/payments/**",
                           "**/billing/**", "**/tenant/**", "**/tenants/**", "secrets/**"],
                ),
                "database_migrations": CapabilityGate(
                    capability="database_migrations",
                    paths=["database/migrations/**", "migrations/**"],
                ),
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "project": {"name": self.project_name},
            "defaults": {
                "max_agents": self.max_agents,
                "worktree_dir": self.worktree_dir,
            },
            "lanes": [
                {
                    "name": lane.name,
                    "allow": lane.allow,
                    "deny": lane.deny,
                }
                for lane in self.lanes.values()
            ],
            "ports": {
                name: {"start": p_range.start, "end": p_range.end}
                for name, p_range in self.port_ranges.items()
            },
            "git": {
                "protected_branches": self.git.protected_branches,
                "branch_prefix": self.git.branch_prefix,
            },
            "quality": {
                "commands": [
                    c.command if c.satisfies is None
                    else {"command": c.command, "satisfies": c.satisfies}
                    for c in self.quality.commands
                ]
            },
            "capability_gates": {
                name: {"paths": gate.paths}
                for name, gate in self.capability_gates.items()
            },
            "database": {
                "strategy": self.database.strategy,
                "name_template": self.database.name_template,
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Config:
        project_data = data.get("project", {})
        defaults_data = data.get("defaults", {})
        lanes_data = data.get("lanes", [])
        ports_data = data.get("ports", {})
        git_data = data.get("git", {})
        quality_data = data.get("quality", {})
        db_data = data.get("database", {})
        gates_data = data.get("capability_gates", {}) or {}

        lanes = {}
        if isinstance(lanes_data, list):
            for l_item in lanes_data:
                l_name = l_item.get("name", "unknown")
                lanes[l_name] = LaneConfig(
                    name=l_name,
                    allow=l_item.get("allow", []),
                    deny=l_item.get("deny", []),
                )
        elif isinstance(lanes_data, dict):
            for l_name, l_item in lanes_data.items():
                lanes[l_name] = LaneConfig(
                    name=l_name,
                    allow=l_item.get("allow", []),
                    deny=l_item.get("deny", []),
                )

        port_ranges = {}
        for p_name, p_val in ports_data.items():
            port_ranges[p_name] = PortRange(
                start=p_val.get("start", 8000),
                end=p_val.get("end", 8999),
            )

        return cls(
            version=data.get("version", 1),
            project_name=project_data.get("name", "my-project"),
            max_agents=defaults_data.get("max_agents", 4),
            worktree_dir=defaults_data.get("worktree_dir", ".parallel-agents/worktrees"),
            lanes=lanes,
            port_ranges=port_ranges,
            git=GitConfig(
                protected_branches=git_data.get("protected_branches", ["main", "master"]),
                branch_prefix=git_data.get("branch_prefix", "parallel/"),
            ),
            quality=QualityConfig(commands=_parse_quality_commands(quality_data.get("commands", []))),
            database=DatabaseConfig(
                strategy=db_data.get("strategy", "per-agent"),
                name_template=db_data.get("name_template", "app_${AGENT_ID}"),
            ),
            capability_gates={
                str(name): CapabilityGate(
                    capability=str(name),
                    paths=[str(p) for p in (spec or {}).get("paths", []) or []],
                )
                for name, spec in gates_data.items()
            },
        )


def _parse_quality_commands(raw: Any) -> List[QualityCommand]:
    """Accepts plain strings (the original format) and {command, satisfies} objects."""
    parsed: List[QualityCommand] = []
    for item in raw or []:
        if isinstance(item, str):
            parsed.append(QualityCommand(command=item))
        elif isinstance(item, dict):
            cmd = item.get("command")
            if not cmd:
                continue
            satisfies = item.get("satisfies")
            parsed.append(QualityCommand(command=str(cmd),
                                         satisfies=str(satisfies) if satisfies else None))
    return parsed


CONFIG_PATH = Path(".parallel-agents/config.yaml")


def generate_default_config(project_name: str = "my-project") -> Config:
    """Helper to generate a standard default Config object."""
    return Config.default(project_name)


def load_config(root_dir: Optional[Path] = None) -> Config:
    root = root_dir or Path.cwd()
    cfg_file = root / CONFIG_PATH
    if not cfg_file.exists():
        raise FileNotFoundError(
            f"No parallel-agents configuration found at {cfg_file}. Run 'parallel-agents init' first."
        )
    with open(cfg_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config.from_dict(data)


def save_config(config: Config, root_dir: Optional[Path] = None) -> Path:
    root = root_dir or Path.cwd()
    cfg_file = root / CONFIG_PATH
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(config.to_dict(), f, sort_keys=False, default_flow_style=False)
    return cfg_file
