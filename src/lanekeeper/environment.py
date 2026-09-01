"""Environment and runtime state isolation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Optional
from .config import Config
from .state import AgentState

# Characters that would let a value escape its line in a .env file. Task descriptions
# are free-form user input, so every value is normalised to a single line and then
# POSIX single-quoted before it is written.
_WHITESPACE_RUN = re.compile(r"\s+")
_INVALID_KEY_CHARS = re.compile(r"[^A-Za-z0-9_]")
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class UnresolvedTemplateError(ValueError):
    """Raised when a URL template names a value this agent does not have."""

    def __init__(self, name: str, template: str, missing: str):
        self.name = name
        self.template = template
        self.missing = missing
        super().__init__(
            f"template for '{name}' references ${{{missing}}}, which this agent has no value for"
        )


def expand_template(name: str, template: str, values: Dict[str, str]) -> str:
    """Expands ``${NAME}`` placeholders against an agent's own generated values.

    Fails closed. A URL that is only partly expanded — ``http://127.0.0.1:${BACKEND_PORT}``
    written out literally — is worse than no variable at all: the frontend would accept it
    and fail at request time, far from the cause. A template naming a value the agent does
    not have is therefore dropped, not emitted.
    """
    missing = [m.group(1) for m in _PLACEHOLDER.finditer(template) if m.group(1) not in values]
    if missing:
        raise UnresolvedTemplateError(name, template, missing[0])
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], template)


def shell_quote(value: str) -> str:
    """POSIX single-quotes an arbitrary string so it survives `source` and dotenv parsers.

    Embedded newlines and tabs are collapsed to single spaces first: a multi-line value
    cannot be represented safely in a line-oriented .env file, and none of the values we
    emit (ids, lanes, seats, ports, task descriptions) carry meaning in their line breaks.

    >>> shell_quote('add "auth"')
    '\'add "auth"\''
    >>> shell_quote("it's fine")
    '\'it\'"\'"\'s fine\''
    """
    flattened = _WHITESPACE_RUN.sub(" ", str(value)).strip()
    # In POSIX sh a single-quoted string ends at the next quote, so a literal quote is
    # written by closing, emitting an escaped quote, and reopening: ' -> '"'"'
    escaped = flattened.replace("'", "'\"'\"'")
    return f"'{escaped}'"


def sanitize_env_key(key: str) -> str:
    """Coerces a config-derived name into a valid POSIX environment variable name."""
    cleaned = _INVALID_KEY_CHARS.sub("_", str(key)).upper()
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned


class EnvironmentManager:
    def __init__(self, config: Config):
        self.config = config

    def generate_env_vars(self, agent: AgentState) -> Dict[str, str]:
        env_vars: Dict[str, str] = {
            "AGENT_ID": agent.id,
            "AGENT_NAME": agent.name,
            "AGENT_SEAT": agent.seat,
            "AGENT_LANE": agent.lane,
            "AGENT_TASK": agent.task,
        }

        # Port mapping
        for category, port_val in agent.ports.items():
            key = sanitize_env_key(category)
            env_vars[f"{key}_PORT"] = str(port_val)
            if category == "backend":
                env_vars["PORT"] = str(port_val)
                env_vars["API_PORT"] = str(port_val)
            elif category == "frontend":
                env_vars["FRONTEND_PORT"] = str(port_val)
                env_vars["VITE_PORT"] = str(port_val)

        # Database isolation mapping
        if self.config.database.strategy == "per-agent":
            safe_id = agent.id.replace("-", "_")
            db_name = self.config.database.name_template.replace("${AGENT_ID}", safe_id)
            env_vars["DATABASE_NAME"] = db_name
            env_vars["DB_NAME"] = db_name

        # Service URLs. Ports alone do not connect a frontend to a backend: a browser
        # build tool exposes only its own prefixed variables to client code, so an
        # unprefixed API_PORT is invisible to the bundle and the frontend falls back to
        # whatever default is compiled into its source — usually another agent's server,
        # or a stranger's. The prefixes to write are chosen at `init` from the
        # repository's own dependencies and live in config; see `lanekeeper.frameworks`.
        env_vars["HOST"] = self.config.environment.host
        for name, template in sorted(self.config.environment.url_templates.items()):
            try:
                env_vars[sanitize_env_key(name)] = expand_template(name, template, env_vars)
            except UnresolvedTemplateError:
                # The project declares no such port category. Emitting a half-expanded
                # URL would be worse than omitting the variable.
                continue

        return env_vars

    def write_agent_environment(self, worktree_path: Path, agent: AgentState) -> None:
        worktree_path.mkdir(parents=True, exist_ok=True)
        env_vars = self.generate_env_vars(agent)

        # 1. Write .env file
        env_file = worktree_path / ".env"
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(f"# Generated by lanekeeper for {agent.id}\n")
            f.write("# Values are POSIX single-quoted; do not hand-edit without re-quoting.\n")
            for k, v in sorted(env_vars.items()):
                f.write(f"{sanitize_env_key(k)}={shell_quote(v)}\n")

        # 2. Write .lane file (seat & role declaration for AI agents). It also carries
        #    the boundary itself, so an agent told "read .lane" learns which paths it may
        #    touch without being handed the whole configuration.
        lane = self.config.lanes.get(agent.lane)
        lane_file = worktree_path / ".lane"
        with open(lane_file, "w", encoding="utf-8") as f:
            f.write(f"SEAT={shell_quote(agent.seat)}\n")
            f.write(f"ROLE={shell_quote(agent.seat.lower())}\n")
            f.write(f"LANE={shell_quote(agent.lane)}\n")
            f.write(f"AGENT_ID={shell_quote(agent.id)}\n")
            f.write(f"TASK={shell_quote(agent.task)}\n")
            if lane is not None:
                f.write(f"ALLOW={shell_quote(' '.join(lane.allow))}\n")
                f.write(f"DENY={shell_quote(' '.join(lane.deny))}\n")
