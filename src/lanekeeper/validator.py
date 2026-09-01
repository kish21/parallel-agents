"""Validation runner for lane compliance, capability gates, and quality commands."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .capabilities import (
    CapabilityCard,
    CapabilityRegistry,
    CapabilityState,
    UnknownSeatError,
)
from .config import Config, UnknownLaneError
from .lanes import LaneEngine, LaneValidationResult
from . import paths
from .state import StateManager
from .worktree import GitError, WorktreeManager


@dataclass
class QualityCommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    passed: bool
    satisfies: Optional[str] = None


@dataclass
class CapabilityViolation:
    """A file the seat is not competent to have modified."""

    filepath: str
    capability: str
    state: str
    detail: str


@dataclass
class ValidationReport:
    agent_id: str
    agent_name: str
    lane: str
    is_valid: bool
    worktree_valid: bool
    lane_result: LaneValidationResult
    seat: str = ""
    quality_results: List[QualityCommandResult] = field(default_factory=list)
    capability_violations: List[CapabilityViolation] = field(default_factory=list)
    gates_evaluated: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class Validator:
    def __init__(
        self,
        config: Config,
        state: StateManager,
        worktree_mgr: WorktreeManager,
        capabilities: Optional[CapabilityRegistry] = None,
    ):
        self.config = config
        self.state = state
        self.worktree_mgr = worktree_mgr
        # Loaded lazily from the worktree manager's root so existing callers keep working.
        self.capabilities = (
            capabilities
            if capabilities is not None
            else CapabilityRegistry.load(self.worktree_mgr.root_dir)
        )

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _matches_any(path: str, patterns: List[str]) -> Optional[str]:
        """Returns the first matching pattern, or None.

        A pattern ending in '/' is a directory prefix (the form used by the card examples
        in docs/legacy/03-orchestration.md). `match_glob` reads it that way for lanes and gates alike,
        so the two no longer disagree about what `secrets/` means.
        """
        for pattern in patterns:
            if LaneEngine.match_glob(path, pattern):
                return pattern
        return None

    def _any_lane_allows(self, path: str) -> bool:
        return any(
            self._matches_any(path, lane.allow)
            for lane in self.config.lanes.values() if lane.allow
        )

    def _run_quality_commands(self) -> List[QualityCommandResult]:
        results: List[QualityCommandResult] = []
        for cmd in self.config.quality.commands:
            try:
                res = subprocess.run(
                    cmd.command, cwd=self._cwd, shell=True,
                    capture_output=True, text=True, timeout=300,
                )
                results.append(QualityCommandResult(
                    command=cmd.command, exit_code=res.returncode,
                    stdout=(res.stdout or "").strip(), stderr=(res.stderr or "").strip(),
                    passed=res.returncode == 0, satisfies=cmd.satisfies,
                ))
            except Exception as e:
                results.append(QualityCommandResult(
                    command=cmd.command, exit_code=-1, stdout="", stderr=str(e),
                    passed=False, satisfies=cmd.satisfies,
                ))
        return results

    def _capability_satisfied_by_script(
        self, capability: str, quality_results: List[QualityCommandResult]
    ) -> bool:
        """True when a verified script for this capability ran and passed.

        This is what `author-required` means operationally: the harness may proceed
        because a procedure written for it was executed, not because it improvised one.
        """
        relevant = [q for q in quality_results if q.satisfies == capability]
        return bool(relevant) and all(q.passed for q in relevant)

    def _check_capabilities(
        self,
        card: CapabilityCard,
        changed_files: List[str],
        quality_results: List[QualityCommandResult],
    ) -> List[CapabilityViolation]:
        violations: List[CapabilityViolation] = []

        for filepath in changed_files:
            # 1. Per-seat forbidden paths override everything, including the lane's allow.
            forbidden = self._matches_any(filepath, card.forbidden_paths)
            if forbidden:
                violations.append(CapabilityViolation(
                    filepath=filepath, capability="(forbidden_paths)", state="forbidden",
                    detail=f"seat '{card.seat}' declares this path forbidden "
                           f"(matched '{forbidden}')",
                ))
                continue

            # 2. Capability gates.
            for name, gate in sorted(self.config.capability_gates.items()):
                if not self._matches_any(filepath, gate.paths):
                    continue
                state = card.state_for(name)

                if state is CapabilityState.NATIVE:
                    continue

                if state is CapabilityState.AUTHOR_REQUIRED:
                    if self._capability_satisfied_by_script(name, quality_results):
                        continue
                    violations.append(CapabilityViolation(
                        filepath=filepath, capability=name, state=state.value,
                        detail=f"seat '{card.seat}' is author-required for '{name}' and no "
                               f"verified script satisfying it passed. Add a quality command "
                               f"with `satisfies: {name}`, or escalate to a native seat.",
                    ))
                    continue

                # UNAVAILABLE — the hard stop.
                undeclared = "" if card.declares(name) else " (capability not rated on the card)"
                violations.append(CapabilityViolation(
                    filepath=filepath, capability=name, state=state.value,
                    detail=f"seat '{card.seat}' cannot perform '{name}'{undeclared}. "
                           f"This change must be escalated to a seat rated native for it.",
                ))

        return violations

    # ------------------------------------------------------------------ main

    def validate_agent(self, agent_id_or_name: str) -> ValidationReport:
        agent = self.state.get_agent(agent_id_or_name)
        if not agent:
            raise ValueError(f"Agent '{agent_id_or_name}' not found.")

        worktree_path = Path(agent.worktree_path)
        self._cwd = worktree_path
        worktree_valid = worktree_path.exists()
        errors: List[str] = []

        def failed(lane_result=None, **extra):
            return ValidationReport(
                agent_id=agent.id, agent_name=agent.name, lane=agent.lane, seat=agent.seat,
                is_valid=False, worktree_valid=worktree_valid,
                lane_result=lane_result or LaneValidationResult(lane_name=agent.lane, is_valid=False),
                errors=errors, **extra,
            )

        if not worktree_valid:
            errors.append(f"Worktree path does not exist: {worktree_path}")
            return failed()

        # 1. Lane path validation. An agent carrying a lane that is not declared cannot be
        #    validated at all — substituting an empty policy would pass every file.
        try:
            lane_config = self.config.get_lane(agent.lane)
        except UnknownLaneError as e:
            errors.append(f"{e} Agent '{agent.id}' cannot be validated against an undeclared lane.")
            return failed()

        # A diff that cannot be computed is a failed validation, not an empty one. The
        # empty list is what a clean branch returns, and nothing downstream could tell
        # "nothing changed" from "I could not look".
        try:
            changed_files = self.worktree_mgr.get_changed_files(worktree_path)
        except GitError as e:
            errors.append(
                f"Could not read this agent's changes, so nothing was checked: {e}")
            return failed()
        lane_result = LaneEngine.validate_files(changed_files, lane_config)

        # A file that no declared lane would accept is a symptom of a lane configuration
        # that does not describe this repository — not of the agent doing something wrong.
        # Blaming the file sends the user hunting through their diff instead of their config.
        orphaned = [
            v.filepath for v in lane_result.violations
            if v.reason == "not_allowed" and not self._any_lane_allows(v.filepath)
        ]
        for v in lane_result.violations:
            if v.reason == "policy":
                errors.append(
                    f"Lane policy modified: {v.filepath}. No lane may change the file that "
                    f"defines the lanes; make that change on the main checkout, not in an "
                    f"agent's branch.")
            elif v.reason == "denied":
                errors.append(
                    f"Forbidden file modified (matched deny pattern '{v.matched_pattern}'): {v.filepath}")
            else:
                errors.append(
                    f"Out-of-lane file modified (not in allowed paths for lane '{agent.lane}'): {v.filepath}")
        if orphaned:
            errors.append(
                f"No declared lane allows {len(orphaned)} of these paths (e.g. {orphaned[0]}). "
                f"Your lanes may not match this project's layout — check the 'lanes' section of "
                f"{paths.display_config_path()}, or re-run 'lanekeeper init --force' to "
                f"regenerate them from the repository's actual structure."
            )

        # 2. Quality commands.
        quality_results = self._run_quality_commands()
        for q in quality_results:
            if not q.passed:
                errors.append(f"Quality command failed ('{q.command}'): exit code {q.exit_code}")

        # 3. Capability gates.
        #
        # Gating applies only where the operator declared gates. If none are configured
        # there is nothing to enforce. But once gates exist, a seat without a card fails
        # closed: an unevaluable seat must not pass a gated path.
        capability_violations: List[CapabilityViolation] = []
        gates_evaluated: List[str] = []

        if self.config.capability_gates:
            gates_evaluated = sorted(self.config.capability_gates)
            try:
                card = self.capabilities.get(agent.seat)
            except UnknownSeatError as e:
                errors.append(
                    f"{e} Capability gates are configured ({', '.join(gates_evaluated)}), so "
                    f"agent '{agent.id}' cannot be validated without a card for its seat."
                )
                return failed(lane_result=lane_result, quality_results=quality_results,
                              gates_evaluated=gates_evaluated)

            # Lane scope is part of the card's contract.
            if not card.allows_lane(agent.lane):
                errors.append(
                    f"Seat '{agent.seat}' is not permitted in lane '{agent.lane}' "
                    f"(max_allowed_lane_scope: {', '.join(card.max_allowed_lane_scope)})."
                )

            capability_violations = self._check_capabilities(
                card, lane_result.allowed_files + [v.filepath for v in lane_result.violations],
                quality_results,
            )
            for cv in capability_violations:
                errors.append(f"Capability gate '{cv.capability}' on {cv.filepath}: {cv.detail}")

        overall_valid = not errors and lane_result.is_valid and worktree_valid
        return ValidationReport(
            agent_id=agent.id, agent_name=agent.name, lane=agent.lane, seat=agent.seat,
            is_valid=overall_valid, worktree_valid=worktree_valid, lane_result=lane_result,
            quality_results=quality_results, capability_violations=capability_violations,
            gates_evaluated=gates_evaluated, errors=errors,
        )
