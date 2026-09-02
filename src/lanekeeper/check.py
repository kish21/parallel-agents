"""`lanekeeper check`: the boundary check as a pull-request gate.

`validate` answers "did *this agent* stay in its lane?" and needs the agent's state
record and worktree. A pull request has neither: CI checks out a branch, and all it
knows is which lane the change claims to belong to. `check` is the same lane engine
handed a lane name and a diff, so it can run anywhere there is a checkout — a CI job,
a pre-push hook, a reviewer's terminal.

Nothing here decides which lane a change is in. That comes from the person or the
process that opened the pull request: a `--lane` flag, or a `lane: <name>` label read by
the workflow this module writes. A change with no lane is refused, never waved through —
the gate cannot check a change against a lane it was not told.

The one reserved lane name is ``policy``. The lane policy and the seat cards are denied
to every lane (see `LaneEngine.is_policy`), so a change to them needs its own rule, and
the rule is mechanical: a policy change may touch the policy files and nothing else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from .config import Config, UnknownLaneError
from .lanes import LaneEngine, LaneValidationResult, LaneViolation
from . import paths
from .worktree import GitError, WorktreeManager

#: The lane name reserved for a change to the lane policy itself.
POLICY_LANE = "policy"

#: Label prefix the written workflow reads a lane from: `lane: checkout`.
DEFAULT_LABEL_PREFIX = "lane:"

#: Where the written workflow goes, relative to the repository root.
WORKFLOW_PATH = Path(".github") / "workflows" / "lanekeeper-gate.yml"


def policy_lane_paths() -> Tuple[str, ...]:
    """Everything a change under the `policy` lane may touch.

    The policy files themselves, plus the files that only ever change alongside them:
    the ignore rules `init` writes, the human record `divide --confirm` writes, and
    every workflow lanekeeper itself writes — the gate, and any other
    `lanekeeper-*.yml` in the workflows directory. On the first real project, a second
    lanekeeper workflow added to the install pull request turned its own gate red,
    because only the gate's file was listed.
    """
    return tuple(paths.policy_paths()) + (
        ".gitignore", "lanes.yaml", ".github/workflows/lanekeeper-*.yml")


class NoLaneError(ValueError):
    """Raised when a change cannot be checked because no single lane was named."""


@dataclass
class CheckReport:
    lane: str
    base: str
    head: str
    result: LaneValidationResult
    errors: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors and self.result.is_valid


def lane_from_labels(labels: List[str], prefix: str = DEFAULT_LABEL_PREFIX) -> str:
    """The one lane a set of pull-request labels names.

    Exactly one, because two lanes on one change means the change is two changes, and
    none means the gate has nothing to check against. Both are refused with the reason.
    """
    prefix = prefix.strip()
    lanes = []
    for label in labels:
        text = str(label).strip()
        if text.lower().startswith(prefix.lower()):
            name = text[len(prefix):].strip()
            if name:
                lanes.append(name)
    if len(lanes) == 1:
        return lanes[0]
    if not lanes:
        raise NoLaneError(
            f"This change carries no '{prefix} <name>' label, so there is no lane to "
            f"check it against. Add one label naming its lane.")
    raise NoLaneError(
        f"This change carries {len(lanes)} lane labels ({', '.join(lanes)}). A change "
        f"belongs to one lane; if it needs two, it is two changes.")


def lane_from_labels_json(raw: str, prefix: str = DEFAULT_LABEL_PREFIX) -> str:
    """As `lane_from_labels`, from the JSON list the workflow passes in."""
    try:
        labels = json.loads(raw)
    except ValueError as e:
        raise NoLaneError(f"The label list is not JSON: {e}") from e
    if not isinstance(labels, list):
        raise NoLaneError("The label list must be a JSON array of label names.")
    return lane_from_labels([str(x) for x in labels], prefix)


def check_files(config: Config, lane_name: str, files: List[str]) -> LaneValidationResult:
    """The lane engine's verdict on a list of changed paths, for a named lane.

    Raises `UnknownLaneError` for a lane the configuration does not declare: a change
    claiming a lane that does not exist has no boundary, and no boundary is not a pass.
    """
    if lane_name == POLICY_LANE:
        return _check_policy_change(files)
    lane = config.get_lane(lane_name)
    return LaneEngine.validate_files(files, lane)


def _check_policy_change(files: List[str]) -> LaneValidationResult:
    """A policy change may touch the policy files and nothing else."""
    allowed: List[str] = []
    violations: List[LaneViolation] = []
    permitted = policy_lane_paths()
    for f in files:
        norm = LaneEngine.normalize_path(f)
        if LaneEngine.is_bookkeeping(norm):
            continue
        if LaneEngine.is_policy(norm) or any(
                LaneEngine.match_glob(norm, p) for p in permitted):
            allowed.append(norm)
        else:
            violations.append(LaneViolation(filepath=norm, reason="not_allowed"))
    return LaneValidationResult(
        lane_name=POLICY_LANE, is_valid=not violations,
        allowed_files=allowed, violations=violations)


def check_checkout(
    config: Config,
    root: Path,
    lane_name: str,
    base: str,
    head: str = "HEAD",
    include_working_tree: bool = False,
) -> CheckReport:
    """Checks the changes between `base` and `head` in the checkout at `root`.

    `include_working_tree` adds uncommitted and untracked files, for running the gate
    by hand before committing. In CI the checkout is clean and the diff is the change.
    """
    wt = WorktreeManager(root)
    errors: List[str] = []
    try:
        files = wt.diff_files(base, head, cwd=root)
        if include_working_tree:
            files = list(dict.fromkeys(files + wt.get_changed_files(root, base_branch=base)))
    except GitError as e:
        # Not an empty change: a change that could not be read. Say so and fail.
        errors.append(f"Could not read the change, so nothing was checked: {e}")
        return CheckReport(lane=lane_name, base=base, head=head, errors=errors,
                           result=LaneValidationResult(lane_name=lane_name, is_valid=False))

    try:
        result = check_files(config, lane_name, files)
    except UnknownLaneError as e:
        errors.append(f"{e} A change cannot be checked against a lane that is not declared.")
        return CheckReport(lane=lane_name, base=base, head=head, errors=errors,
                           result=LaneValidationResult(lane_name=lane_name, is_valid=False))

    for v in result.violations:
        if v.reason == "policy":
            errors.append(
                f"{v.filepath}: this file defines the lanes. A change to it is made by a "
                f"person under the '{POLICY_LANE}' lane, on its own.")
        elif v.reason == "denied":
            errors.append(f"{v.filepath}: denied to lane '{lane_name}' "
                          f"(matched '{v.matched_pattern}').")
        elif lane_name == POLICY_LANE:
            errors.append(f"{v.filepath}: a policy change may touch only the policy files "
                          f"({', '.join(policy_lane_paths())}).")
        else:
            errors.append(f"{v.filepath}: outside lane '{lane_name}'.")
    return CheckReport(lane=lane_name, base=base, head=head, result=result, errors=errors)


def render(report: CheckReport) -> str:
    lines = [f"🛡️  LANE CHECK — lane '{report.lane}', {report.base}...{report.head}", ""]
    n = len(report.result.allowed_files)
    if report.passed:
        lines.append(f"  ✓ All {n} changed file{'s' if n != 1 else ''} stay inside the lane.")
        lines += ["", "✅ CHECK PASSED"]
    else:
        for err in report.errors:
            lines.append(f"  ✗ {err}")
        lines += ["", "❌ CHECK FAILED: this change leaves its lane."]
    return "\n".join(lines)


def workflow_text(label_prefix: str = DEFAULT_LABEL_PREFIX) -> str:
    """The GitHub Actions workflow that runs this check on every pull request.

    It fails closed: no lane label, no pass. The lane is read from the pull request's
    labels because that is the one thing a reviewer can see and change without a
    checkout, and it is the same `lane:` label family `bootstrap.sh` creates.
    """
    return f"""\
name: Lane gate

# Runs the lanekeeper boundary check on every pull request. The change must carry
# exactly one `{label_prefix} <name>` label naming the lane it belongs to; the check then
# fails if any changed file is outside that lane. Written by `lanekeeper check
# --write-workflow`; edit freely, it is not regenerated.

on:
  pull_request:
    types: [opened, synchronize, reopened, labeled, unlabeled]

concurrency:
  group: lane-gate-${{{{ github.event.pull_request.number }}}}
  cancel-in-progress: true

jobs:
  lane:
    name: Change stays inside its lane
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # The whole history, so the merge base with the target branch exists.
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install lanekeeper
        run: python -m pip install --upgrade pip lanekeeper

      - name: Check the change against its lane
        env:
          LABELS: ${{{{ toJSON(github.event.pull_request.labels.*.name) }}}}
          BASE: origin/${{{{ github.base_ref }}}}
        run: |
          lanekeeper check --labels-json "$LABELS" --label-prefix "{label_prefix}" --base "$BASE"
"""


def write_workflow(root: Path, label_prefix: str = DEFAULT_LABEL_PREFIX,
                   force: bool = False) -> Optional[Path]:
    """Writes the workflow into the repository. Returns None if one is already there."""
    target = root / WORKFLOW_PATH
    if target.exists() and not force:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(workflow_text(label_prefix), encoding="utf-8")
    return target
