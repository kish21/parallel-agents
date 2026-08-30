"""Validation runner for lane compliance and quality commands."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from .config import Config, LaneConfig, UnknownLaneError
from .lanes import LaneEngine, LaneValidationResult
from .state import AgentState, StateManager
from .worktree import WorktreeManager


@dataclass
class QualityCommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    passed: bool


@dataclass
class ValidationReport:
    agent_id: str
    agent_name: str
    lane: str
    is_valid: bool
    worktree_valid: bool
    lane_result: LaneValidationResult
    quality_results: List[QualityCommandResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class Validator:
    def __init__(
        self,
        config: Config,
        state: StateManager,
        worktree_mgr: WorktreeManager,
    ):
        self.config = config
        self.state = state
        self.worktree_mgr = worktree_mgr

    def validate_agent(self, agent_id_or_name: str) -> ValidationReport:
        agent = self.state.get_agent(agent_id_or_name)
        if not agent:
            raise ValueError(f"Agent '{agent_id_or_name}' not found.")

        worktree_path = Path(agent.worktree_path)
        worktree_valid = worktree_path.exists()
        errors: List[str] = []

        if not worktree_valid:
            errors.append(f"Worktree path does not exist: {worktree_path}")
            lane_res = LaneValidationResult(lane_name=agent.lane, is_valid=False)
            return ValidationReport(
                agent_id=agent.id,
                agent_name=agent.name,
                lane=agent.lane,
                is_valid=False,
                worktree_valid=False,
                lane_result=lane_res,
                errors=errors,
            )

        # 1. Lane Path Validation
        #
        # An agent carrying a lane that is not declared in the configuration cannot be
        # validated at all: there is no policy to check it against. Report that as a
        # failure. Substituting an empty allow/deny lane here would silently pass every
        # file, turning a config typo into a total loss of lane enforcement.
        try:
            lane_config = self.config.get_lane(agent.lane)
        except UnknownLaneError as e:
            errors.append(
                f"{e} Agent '{agent.id}' cannot be validated against an undeclared lane."
            )
            return ValidationReport(
                agent_id=agent.id,
                agent_name=agent.name,
                lane=agent.lane,
                is_valid=False,
                worktree_valid=worktree_valid,
                lane_result=LaneValidationResult(lane_name=agent.lane, is_valid=False),
                errors=errors,
            )

        changed_files = self.worktree_mgr.get_changed_files(worktree_path)
        lane_result = LaneEngine.validate_files(changed_files, lane_config)

        if not lane_result.is_valid:
            for v in lane_result.violations:
                if v.reason == "denied":
                    errors.append(f"Forbidden file modified (matched deny pattern '{v.matched_pattern}'): {v.filepath}")
                else:
                    errors.append(f"Out-of-lane file modified (not in allowed paths for lane '{agent.lane}'): {v.filepath}")

        # 2. Quality Commands Execution
        quality_results: List[QualityCommandResult] = []
        for cmd in self.config.quality.commands:
            try:
                res = subprocess.run(
                    cmd,
                    cwd=worktree_path,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                q_passed = (res.returncode == 0)
                quality_results.append(
                    QualityCommandResult(
                        command=cmd,
                        exit_code=res.returncode,
                        stdout=res.stdout.strip(),
                        stderr=res.stderr.strip(),
                        passed=q_passed,
                    )
                )
                if not q_passed:
                    errors.append(f"Quality command failed ('{cmd}'): exit code {res.returncode}")
            except Exception as e:
                quality_results.append(
                    QualityCommandResult(
                        command=cmd,
                        exit_code=-1,
                        stdout="",
                        stderr=str(e),
                        passed=False,
                    )
                )
                errors.append(f"Quality command error ('{cmd}'): {e}")

        overall_valid = (len(errors) == 0) and lane_result.is_valid and worktree_valid
        return ValidationReport(
            agent_id=agent.id,
            agent_name=agent.name,
            lane=agent.lane,
            is_valid=overall_valid,
            worktree_valid=worktree_valid,
            lane_result=lane_result,
            quality_results=quality_results,
            errors=errors,
        )
