"""Configuration management for lanekeeper."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional
import yaml
from . import paths


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
class EnvironmentConfig:
    """How an agent's generated `.env` describes the services it should talk to.

    `url_templates` maps a variable name to a template expanded against that agent's own
    generated values (`${HOST}`, `${BACKEND_PORT}`, `${FRONTEND_PORT}`, `${AGENT_ID}`,
    ...). Ports alone cannot wire a frontend to a backend, because browser build tools
    only expose variables carrying their own prefix; the prefixed names are chosen from
    the repository's declared dependencies at `init` time and kept here as editable
    configuration. See `lanekeeper.frameworks`.
    """

    host: str = "127.0.0.1"
    url_templates: Dict[str, str] = field(default_factory=dict)


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
class GitHubTrackerConfig:
    """How to read GitHub Issues. Every value here is settable, including the
    executable, so the call can be pointed at a wrapper or stubbed in a test."""

    repo: str = ""            # blank: the repository this directory belongs to
    state: str = "open"
    limit: int = 500
    command: str = "gh"


@dataclass
class IntakeThresholds:
    """The numbers step 1 judges by, kept out of the code that applies them.

    They are judgement calls on a heuristic, not constants: a project with a coarse
    backlog and a project with fine-grained tickets need different answers, and the
    person who knows which is which is the user, not this module.
    """

    thin_issue_count: int = 3        # fewer tickets than this reads as thin
    feature_match_score: float = 0.5  # share of a feature's words a ticket must carry
    duplicate_title_score: float = 0.85
    #: Distinct top-level directories one ticket may name before it reads as several
    #: pieces of work. It was 3, which is exactly what a correctly written feature
    #: slice spans (backend, frontend, tests) — so the default flagged the very model
    #: the ticket form now teaches. A slice that also touches docs or a migrations
    #: root reaches five; past that it really is several tickets. See #38.
    broad_ticket_areas: int = 5
    tidy_flag_ratio: float = 0.5     # share of flagged tickets that stops the run
    duplicate_report_limit: int = 10  # closest near-duplicate pairs worth showing


@dataclass
class IntakeConfig:
    """Step 1 of `lanekeeper start`: where the work is written down, and what to
    compare it against. See docs/start-step1-intake.md."""

    tracker: str = "github"
    github: GitHubTrackerConfig = field(default_factory=GitHubTrackerConfig)
    # In order of preference. The first that yields features is the one used.
    spec_sources: List[str] = field(
        default_factory=lambda: ["PRODUCT.md", "docs/PRODUCT.md", "README.md"]
    )
    spec_sections: List[str] = field(
        default_factory=lambda: ["Scope", "Plan", "Features"]
    )
    thresholds: IntakeThresholds = field(default_factory=IntakeThresholds)


@dataclass
class DivideThresholds:
    """The numbers step 2 divides by, kept out of the code that applies them.

    Every one of them is a judgement about somebody else's repository, which is the
    definition of a setting rather than a constant.
    """

    min_group_tickets: int = 2       # tickets sharing a feature name before it is a group
    min_slice_files: int = 2         # files under a directory before it counts as one
    min_slice_roots: int = 2         # top-level roots a name must appear under
    overlap_report_limit: int = 20   # most overlapping pairs worth printing
    unclaimed_examples: int = 5      # example unclaimed files worth naming


@dataclass
class DivideConfig:
    """Step 2 of `lanekeeper start`: how the written-down work is divided up.

    See docs/start-step2-divide.md. The word lists are what stop a feature name being
    read out of a directory that names a technology layer, and they are settable because
    no fixed list is right for every repository.
    """

    #: The only implemented value. It exists so that when an advisor is added it arrives
    #: switched off: the division is a mechanical answer, and an answer that changes
    #: between runs would not be one.
    advisor: str = "none"
    #: Relative to lanekeeper's own directory.
    draft_path: str = "start/lanes.draft.yaml"
    #: Relative to the repository root. The confirmed file, checked in and hand-edited.
    lane_file: str = "lanes.yaml"
    #: The heading a ticket states its boundary under, as the issue form labels it.
    #: Matched as a prefix, case-insensitively, so "Allowed File Paths (globs)" counts.
    #: Settable because a project whose form words the field differently should not have
    #: to rename the field to be understood.
    path_headings: List[str] = field(default_factory=lambda: ["allowed file paths"])
    #: The heading carrying the ticket's own feature name, when the filer gave one.
    lane_headings: List[str] = field(default_factory=lambda: ["lane"])
    #: Directories that hold code but never name a feature.
    containers: List[str] = field(default_factory=lambda: [
        "src", "app", "apps", "packages", "modules", "lib", "libs", "cmd", "internal",
        "backend", "frontend", "web", "client", "server", "api", "services", "service",
        "tests", "test", "spec", "docs", "scripts", "infra", "infrastructure", "deploy",
    ])
    #: Buckets that group by kind rather than by feature.
    generic_dirs: List[str] = field(default_factory=lambda: [
        "components", "component", "pages", "page", "views", "routes", "hooks", "utils",
        "util", "helpers", "schemas", "schema", "models", "model", "db", "database",
        "migrations", "static", "assets", "styles", "types", "config", "common",
        "shared", "core", "domains", "features", "providers", "adapters", "handlers",
        "controllers", "middleware", "public", "templates",
    ])
    #: Directories whose children are features by construction.
    feature_containers: List[str] = field(default_factory=lambda: [
        "domains", "features", "modules", "packages", "apps",
    ])
    thresholds: DivideThresholds = field(default_factory=DivideThresholds)


@dataclass
class GitConfig:
    protected_branches: List[str] = field(default_factory=lambda: ["main", "master"])
    branch_prefix: str = "parallel/"


@dataclass
class Config:
    version: int = 1
    project_name: str = "parallel-project"
    max_agents: int = 4
    worktree_dir: str = field(default_factory=paths.default_worktree_dir)
    lanes: Dict[str, LaneConfig] = field(default_factory=dict)
    port_ranges: Dict[str, PortRange] = field(default_factory=dict)
    git: GitConfig = field(default_factory=GitConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    capability_gates: Dict[str, CapabilityGate] = field(default_factory=dict)
    intake: IntakeConfig = field(default_factory=IntakeConfig)
    divide: DivideConfig = field(default_factory=DivideConfig)

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
            worktree_dir=paths.default_worktree_dir(),
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
            # Overwritten by `init` with the prefixes this repository's frontends read.
            # The unprefixed pair is the safe floor: server-side code reads it directly.
            environment=EnvironmentConfig(
                host="127.0.0.1",
                url_templates={
                    "API_URL": "http://${HOST}:${BACKEND_PORT}",
                    "BACKEND_URL": "http://${HOST}:${BACKEND_PORT}",
                    "FRONTEND_URL": "http://${HOST}:${FRONTEND_PORT}",
                },
            ),
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
            "environment": {
                "host": self.environment.host,
                "url_templates": dict(self.environment.url_templates),
            },
            "intake": {
                "tracker": self.intake.tracker,
                "github": {
                    "repo": self.intake.github.repo,
                    "state": self.intake.github.state,
                    "limit": self.intake.github.limit,
                    "command": self.intake.github.command,
                },
                "spec_sources": list(self.intake.spec_sources),
                "spec_sections": list(self.intake.spec_sections),
                "thresholds": {
                    "thin_issue_count": self.intake.thresholds.thin_issue_count,
                    "feature_match_score": self.intake.thresholds.feature_match_score,
                    "duplicate_title_score": self.intake.thresholds.duplicate_title_score,
                    "broad_ticket_areas": self.intake.thresholds.broad_ticket_areas,
                    "tidy_flag_ratio": self.intake.thresholds.tidy_flag_ratio,
                    "duplicate_report_limit": self.intake.thresholds.duplicate_report_limit,
                },
            },
            "divide": {
                "advisor": self.divide.advisor,
                "draft_path": self.divide.draft_path,
                "lane_file": self.divide.lane_file,
                "path_headings": list(self.divide.path_headings),
                "lane_headings": list(self.divide.lane_headings),
                "containers": list(self.divide.containers),
                "generic_dirs": list(self.divide.generic_dirs),
                "feature_containers": list(self.divide.feature_containers),
                "thresholds": {
                    "min_group_tickets": self.divide.thresholds.min_group_tickets,
                    "min_slice_files": self.divide.thresholds.min_slice_files,
                    "min_slice_roots": self.divide.thresholds.min_slice_roots,
                    "overlap_report_limit": self.divide.thresholds.overlap_report_limit,
                    "unclaimed_examples": self.divide.thresholds.unclaimed_examples,
                },
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
        env_data = data.get("environment", {}) or {}
        gates_data = data.get("capability_gates", {}) or {}
        # Absent from every configuration written before v0.7. A missing section is a
        # fully-defaulted one, so an existing project keeps working untouched.
        intake_data = data.get("intake", {}) or {}
        divide_data = data.get("divide", {}) or {}

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
            worktree_dir=defaults_data.get("worktree_dir", paths.default_worktree_dir()),
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
            environment=EnvironmentConfig(
                host=str(env_data.get("host", "127.0.0.1")),
                url_templates={
                    str(k): str(v)
                    for k, v in (env_data.get("url_templates", {}) or {}).items()
                },
            ),
            capability_gates={
                str(name): CapabilityGate(
                    capability=str(name),
                    paths=[str(p) for p in (spec or {}).get("paths", []) or []],
                )
                for name, spec in gates_data.items()
            },
            intake=_parse_intake(intake_data),
            divide=_parse_divide(divide_data),
        )


class InvalidIntakeSettingError(ValueError):
    """Raised when a value in the `intake` section cannot be used as written.

    Named rather than generic: the alternative to a clear message is a traceback out of
    `load_config` on a command a user runs before anything else works.
    """

    def __init__(self, key: str, value, expected: str):
        super().__init__(
            f"intake.{key} must be {expected}, but the configuration says {value!r}."
        )


class InvalidDivideSettingError(ValueError):
    """Raised when a value in the `divide` section cannot be used as written.

    Same reason as its intake counterpart: `start` is the first command a new user runs,
    and a traceback out of it is not a message.
    """

    def __init__(self, key: str, value, expected: str):
        super().__init__(
            f"divide.{key} must be {expected}, but the configuration says {value!r}."
        )


def _typed(raw: Dict[str, Any], key: str, default, caster, expected: str, prefix: str,
           error=InvalidIntakeSettingError):
    """One configured value, defaulted when absent and explained when unusable."""
    if key not in raw or raw[key] is None:
        return default
    try:
        return caster(raw[key])
    except (TypeError, ValueError):
        raise error(f"{prefix}{key}", raw[key], expected) from None


def _parse_intake(raw: Dict[str, Any]) -> IntakeConfig:
    """Builds the intake section, defaulting every value that is absent.

    Each key is read independently rather than all-or-nothing, so a user who sets one
    threshold in their configuration does not silently lose the others. An explicitly
    empty list is honoured rather than replaced by the default: "compare against
    nothing" is a legitimate thing to ask for.
    """
    defaults = IntakeConfig()
    gh_raw = raw.get("github", {}) or {}
    th_raw = raw.get("thresholds", {}) or {}

    github = GitHubTrackerConfig(
        repo=str(gh_raw.get("repo") or ""),
        state=str(gh_raw.get("state") or defaults.github.state),
        limit=_typed(gh_raw, "limit", defaults.github.limit, int, "a whole number",
                     "github."),
        command=str(gh_raw.get("command") or defaults.github.command),
    )
    thresholds = IntakeThresholds(
        thin_issue_count=_typed(th_raw, "thin_issue_count",
                                defaults.thresholds.thin_issue_count, int,
                                "a whole number", "thresholds."),
        feature_match_score=_typed(th_raw, "feature_match_score",
                                   defaults.thresholds.feature_match_score, float,
                                   "a number between 0 and 1", "thresholds."),
        duplicate_title_score=_typed(th_raw, "duplicate_title_score",
                                     defaults.thresholds.duplicate_title_score, float,
                                     "a number between 0 and 1", "thresholds."),
        broad_ticket_areas=_typed(th_raw, "broad_ticket_areas",
                                  defaults.thresholds.broad_ticket_areas, int,
                                  "a whole number", "thresholds."),
        tidy_flag_ratio=_typed(th_raw, "tidy_flag_ratio",
                               defaults.thresholds.tidy_flag_ratio, float,
                               "a number between 0 and 1", "thresholds."),
        duplicate_report_limit=_typed(th_raw, "duplicate_report_limit",
                                      defaults.thresholds.duplicate_report_limit, int,
                                      "a whole number", "thresholds."),
    )
    sources = raw.get("spec_sources")
    sections = raw.get("spec_sections")
    return IntakeConfig(
        tracker=str(raw.get("tracker") or defaults.tracker),
        github=github,
        spec_sources=[str(s) for s in (defaults.spec_sources if sources is None else sources)],
        spec_sections=[str(s) for s in (defaults.spec_sections if sections is None else sections)],
        thresholds=thresholds,
    )


def _parse_divide(raw: Dict[str, Any]) -> DivideConfig:
    """Builds the divide section, defaulting every value that is absent.

    Absent from every configuration written before v0.7, so a missing section is a fully
    defaulted one. An explicitly empty word list is honoured: a user who wants every
    directory name treated as a feature name is entitled to say so.
    """
    defaults = DivideConfig()
    th_raw = raw.get("thresholds", {}) or {}

    advisor = str(raw.get("advisor") or defaults.advisor)
    if advisor != "none":
        # There is no advisor. Accepting the setting and ignoring it would promise a
        # behaviour that does not exist, which is the defect this project keeps fixing.
        raise InvalidDivideSettingError(
            "advisor", raw.get("advisor"),
            "'none' — dividing the work is a mechanical answer, and no other advisor "
            "is implemented",
        )

    thresholds = DivideThresholds(
        min_group_tickets=_typed(th_raw, "min_group_tickets",
                                 defaults.thresholds.min_group_tickets, int,
                                 "a whole number", "thresholds.",
                                 InvalidDivideSettingError),
        min_slice_files=_typed(th_raw, "min_slice_files",
                               defaults.thresholds.min_slice_files, int,
                               "a whole number", "thresholds.",
                               InvalidDivideSettingError),
        min_slice_roots=_typed(th_raw, "min_slice_roots",
                               defaults.thresholds.min_slice_roots, int,
                               "a whole number", "thresholds.",
                               InvalidDivideSettingError),
        overlap_report_limit=_typed(th_raw, "overlap_report_limit",
                                    defaults.thresholds.overlap_report_limit, int,
                                    "a whole number", "thresholds.",
                                    InvalidDivideSettingError),
        unclaimed_examples=_typed(th_raw, "unclaimed_examples",
                                  defaults.thresholds.unclaimed_examples, int,
                                  "a whole number", "thresholds.",
                                  InvalidDivideSettingError),
    )

    def _words(key: str, fallback: List[str]) -> List[str]:
        value = raw.get(key)
        if value is None:
            return list(fallback)
        if not isinstance(value, list):
            raise InvalidDivideSettingError(key, value, "a list of words")
        return [str(item).strip().lower() for item in value if str(item).strip()]

    return DivideConfig(
        advisor=advisor,
        draft_path=_inside_the_project(raw, "draft_path", defaults.draft_path),
        lane_file=_inside_the_project(raw, "lane_file", defaults.lane_file),
        path_headings=_words("path_headings", defaults.path_headings),
        lane_headings=_words("lane_headings", defaults.lane_headings),
        containers=_words("containers", defaults.containers),
        generic_dirs=_words("generic_dirs", defaults.generic_dirs),
        feature_containers=_words("feature_containers", defaults.feature_containers),
        thresholds=thresholds,
    )


def _inside_the_project(raw: Dict[str, Any], key: str, default: str) -> str:
    """A configured path that stays where it was promised to stay.

    Both of these are joined onto the repository root and then written to. An absolute
    path, or one that climbs out with `..`, would have this command writing files
    outside the project it was pointed at — the same rule `LANEKEEPER_HOME` already
    enforces, and for the same reason.
    """
    value = str(raw.get(key) or default)
    candidate = PurePosixPath(value.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts or ":" in value[:3]:
        raise InvalidDivideSettingError(
            key, raw.get(key),
            "a path inside this project, not an absolute one and not one that climbs "
            "out of it with '..'")
    return value


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


def generate_default_config(project_name: str = "my-project") -> Config:
    """Helper to generate a standard default Config object."""
    return Config.default(project_name)


def load_config(root_dir: Optional[Path] = None) -> Config:
    root = root_dir or Path.cwd()
    cfg_file = paths.config_path(root)
    if not cfg_file.exists():
        raise FileNotFoundError(
            f"No lanekeeper configuration found at {cfg_file}. Run 'lanekeeper init' first."
        )
    with open(cfg_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config.from_dict(data)


def save_config(config: Config, root_dir: Optional[Path] = None) -> Path:
    root = root_dir or Path.cwd()
    cfg_file = paths.config_path(root)
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(config.to_dict(), f, sort_keys=False, default_flow_style=False)
    return cfg_file
