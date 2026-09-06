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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .config import Config, UnknownLaneError
from .invocation import invocation
from .lanes import LaneEngine, LaneValidationResult, LaneViolation
from . import paths
from .worktree import GitError, WorktreeManager

#: The lane name reserved for a change to the lane policy itself.
POLICY_LANE = "policy"

#: Label prefix the written workflow reads a lane from: `lane: checkout`.
DEFAULT_LABEL_PREFIX = "lane:"

#: Where the written workflow goes, relative to the repository root.
WORKFLOW_PATH = Path(".github") / "workflows" / "lanekeeper-gate.yml"


def codeowners_path_default() -> str:
    """Where CODEOWNERS goes when no configuration says otherwise.

    Imported lazily inside the function: `codeowners` reads `config`, `config` is
    imported here, and asking for it at module scope would close the circle.
    """
    from .codeowners import DEFAULT_PATH
    return DEFAULT_PATH


def policy_lane_paths(config: Optional[Config] = None) -> Tuple[str, ...]:
    """Everything a change under the `policy` lane may touch.

    The policy files themselves, plus the files that only ever change alongside them:
    the ignore rules `init` writes, the human record `divide --confirm` writes, the
    CODEOWNERS file generated from the lanes, and every workflow lanekeeper writes — the gate, and any other
    `lanekeeper-*.yml` in the workflows directory. On the first real project, a second
    lanekeeper workflow added to the install pull request turned its own gate red,
    because only the gate's file was listed.
    """
    return tuple(paths.policy_paths()) + (
        ".gitignore", "lanes.yaml", ".github/workflows/lanekeeper-*.yml",
        # Generated from the lanes, so it changes in the same pull request they do
        # (#42). Read from the configuration rather than hardcoded: a project that
        # keeps CODEOWNERS at the repository root would otherwise have its own policy
        # pull request denied by the gate. Not in `paths.policy_paths()`, though —
        # that is the set no lane may touch, and a repository whose own lane already
        # owned `.github/**` should not have that taken away by a feature it has not
        # turned on.
        config.codeowners.path if config is not None else codeowners_path_default())


class NoLaneError(ValueError):
    """Raised when a change cannot be checked because no single lane was named."""


@dataclass
class Whereabouts:
    """Where a check ran, so the report can say so (#77).

    `check` used to print the lane, the base and the head and never *where*. A person
    with two identical-looking editor windows — the main checkout and the worktree
    `lanekeeper open` made for them — ran it in the wrong one and got seven correct
    red lines about the policy files, which read as the gate being broken. The
    verdict was right about the question it was asked; nothing said it had been asked
    the wrong question. The tool put the second window on screen, so "which one am I
    in" is the tool's to answer.
    """

    root: Path
    #: From the worktree's own `.lane`, when this checkout is an agent's worktree.
    agent_id: str = ""
    lane: str = ""
    #: Agent worktrees that exist under the main checkout, when this *is* the main
    #: checkout: `agent-001 (.lanekeeper/worktrees/agent-001)`.
    worktrees: List[str] = field(default_factory=list)

    @property
    def is_worktree(self) -> bool:
        return bool(self.agent_id or self.lane)


@dataclass
class CheckReport:
    lane: str
    base: str
    head: str
    result: LaneValidationResult
    errors: List[str] = field(default_factory=list)
    where: Optional[Whereabouts] = None

    @property
    def passed(self) -> bool:
        return not self.errors and self.result.is_valid


def whereabouts(root: Path, worktree_dir: str = "") -> Whereabouts:
    """Reads `.lane` in the checkout, or lists the worktrees under it.

    Filesystem only, no git: `check` has no agent state and takes no lock, and the
    `.lane` files are exactly the record it needs — each worktree wrote its own.
    """
    where = Whereabouts(root=root)
    values = read_lane_file(root / ".lane")
    if values:
        where.agent_id = values.get("AGENT_ID", "")
        where.lane = values.get("LANE", "")
        return where
    base = root / (worktree_dir or paths.default_worktree_dir())
    try:
        for child in sorted(base.iterdir()) if base.is_dir() else []:
            found = read_lane_file(child / ".lane")
            if found:
                rel = child.relative_to(root).as_posix()
                where.worktrees.append(
                    f"{found.get('AGENT_ID') or child.name} ({rel}, lane "
                    f"'{found.get('LANE', '?')}')")
    except OSError:
        pass
    return where


def read_lane_file(path: Path) -> Dict[str, str]:
    """The `KEY='value'` pairs of a `.lane` file, unquoted. Empty when there is none."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    out: Dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, _, raw = line.partition("=")
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1].replace("'\"'\"'", "'")
        out[key.strip()] = value
    return out


def lane_from_branch(branch: str, lanes: Sequence[str], prefix: str = "parallel/") -> str:
    """The lane a lanekeeper-made branch name carries, or "" (#72).

    `spawn` names the branch from the agent's task, and for `spawn --ticket` the task
    is `#<n> <title>` — so the slug begins with the ticket number and, when the ticket
    carries a tag, the lane's own name: `parallel/agent-001/2-feat-02-automated-…`.
    A lane named after a bare ticket number is `issue-<n>`, and the number is there
    too. The branch is matched against the *declared* lanes rather than parsed on its
    own: without the list, nothing says where `feat-02` ends and `automated` begins.

    Deterministic and narrow. A branch somebody made by hand yields nothing, and
    nothing means the existing no-label refusal — never a guess.
    """
    text = (branch or "").strip()
    if text.startswith("refs/heads/"):
        text = text[len("refs/heads/"):]
    if prefix and text.startswith(prefix):
        text = text[len(prefix):]
    match = re.match(r"^agent-\d+/(?P<slug>.+)$", text)
    if not match:
        return ""
    slug = match.group("slug")
    number = re.match(r"^(\d+)(?:-|$)", slug)
    if not number:
        return ""
    rest = slug[len(number.group(1)):].lstrip("-")
    candidates = []
    for lane in lanes:
        name = lane.lower()
        if rest == name or rest.startswith(name + "-"):
            candidates.append(lane)
    if f"issue-{number.group(1)}" in lanes:
        candidates.append(f"issue-{number.group(1)}")
    if not candidates:
        return ""
    # A lane named `feat` and one named `feat-02` both prefix the slug; the longer name
    # is the one the slug was actually built from.
    return max(candidates, key=len)


def resolve_lane(explicit: str = "", labels_json: Optional[str] = None,
                 label_prefix: str = DEFAULT_LABEL_PREFIX, branch: str = "",
                 lanes: Sequence[str] = (), branch_prefix: str = "parallel/",
                 from_branch: bool = False) -> str:
    """Which lane a change claims, from the three places that can say (#72).

    Precedence is the whole design. An explicit `--lane` is the person at the
    keyboard. A label wins over the branch, because a reviewer overriding it is a
    deliberate act. The branch is the fallback when no label is present — and only
    when asked for, since it is an inference from a name. When a label and the branch
    both speak and disagree, that is the mislabelled pull request, the one case the
    tool can catch, and it fails naming both.
    """
    if explicit:
        return explicit
    candidate = lane_from_branch(branch, lanes, branch_prefix) if branch else ""
    derived = candidate if from_branch else ""
    labelled = ""
    if labels_json is not None:
        found = lanes_from_labels_json(labels_json, label_prefix)
        if len(found) > 1:
            # Two lanes on one change is two changes, whatever the branch says.
            raise NoLaneError(
                f"This change carries {len(found)} lane labels ({', '.join(found)}). A "
                f"change belongs to one lane; if it needs two, it is two changes.")
        labelled = found[0] if found else ""
    if labelled and derived and labelled != derived:
        raise NoLaneError(
            f"The label says lane '{labelled}' but the branch name says '{derived}'. One "
            f"of them is wrong, and a check against the wrong lane proves nothing: fix "
            f"the label or the branch before this is checked.")
    if labelled:
        return labelled
    if derived:
        return derived
    hint = ""
    if candidate:
        hint = (f" This branch looks like lane '{candidate}': add the label "
                f"'{label_prefix} {candidate}', or run with --lane-from-branch.")
    if labels_json is None:
        # Run by hand, with nothing said: the person, not a workflow, is asking.
        raise NoLaneError(
            f"Say which lane this change belongs to: --lane <name>, --labels-json with "
            f"the pull request's labels, or --lane-from-branch.{hint}")
    raise NoLaneError(
        f"This change carries no '{label_prefix} <name>' label, so there is no lane to "
        f"check it against. Add one label naming its lane.{hint}")


def lanes_from_labels_json(raw: str, prefix: str = DEFAULT_LABEL_PREFIX) -> List[str]:
    """Every lane the label list names, in order; none is an empty list, not an error."""
    try:
        labels = json.loads(raw)
    except ValueError as e:
        raise NoLaneError(f"The label list is not JSON: {e}") from e
    if not isinstance(labels, list):
        raise NoLaneError("The label list must be a JSON array of label names.")
    prefix = prefix.strip()
    found = []
    for label in labels:
        text = str(label).strip()
        if text.lower().startswith(prefix.lower()):
            name = text[len(prefix):].strip()
            if name:
                found.append(name)
    return found


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
        return _check_policy_change(files, config)
    lane = config.get_lane(lane_name)
    return LaneEngine.validate_files(files, lane, LaneEngine.shared_lanes(config),
                                     generated=config.generated)


def _check_policy_change(files: List[str],
                         config: Optional[Config] = None) -> LaneValidationResult:
    """A policy change may touch the policy files and nothing else."""
    allowed: List[str] = []
    violations: List[LaneViolation] = []
    permitted = policy_lane_paths(config)
    for f in files:
        norm = LaneEngine.normalize_path(f)
        if LaneEngine.is_bookkeeping(norm) or LaneEngine.is_generated(norm, config.generated
                                                                       if config else ()):
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
    where: Optional[Whereabouts] = None,
) -> CheckReport:
    """Checks the changes between `base` and `head` in the checkout at `root`.

    `include_working_tree` adds uncommitted and untracked files, for running the gate
    by hand before committing. In CI the checkout is clean and the diff is the change.
    """
    wt = WorktreeManager(root)
    errors: List[str] = []
    where = where if where is not None else whereabouts(root, config.worktree_dir)
    try:
        files = wt.diff_files(base, head, cwd=root)
        if include_working_tree:
            files = list(dict.fromkeys(files + wt.get_changed_files(root, base_branch=base)))
    except GitError as e:
        # Not an empty change: a change that could not be read. Say so and fail.
        errors.append(f"Could not read the change, so nothing was checked: {e}")
        return CheckReport(lane=lane_name, base=base, head=head, errors=errors, where=where,
                           result=LaneValidationResult(lane_name=lane_name, is_valid=False))

    try:
        result = check_files(config, lane_name, files)
    except UnknownLaneError as e:
        errors.append(f"{e} A change cannot be checked against a lane that is not declared.")
        return CheckReport(lane=lane_name, base=base, head=head, errors=errors, where=where,
                           result=LaneValidationResult(lane_name=lane_name, is_valid=False))

    inv = invocation()
    for v in result.violations:
        if v.reason == "policy":
            errors.append(
                f"{v.filepath}: this file defines the lanes. A change to it is made by a "
                f"person under the '{POLICY_LANE}' lane, on its own.")
        elif v.reason == "denied":
            errors.append(f"{v.filepath}: denied to lane '{lane_name}' "
                          f"(matched '{v.matched_pattern}').")
        elif v.reason == "shared":
            errors.append(
                f"{v.filepath}: shared code, in the '{v.shared_lane}' zone that belongs "
                f"to no lane on purpose. A change here affects every lane, so it is "
                f"raised and decided, not made inside this one.")
        elif lane_name == POLICY_LANE:
            errors.append(f"{v.filepath}: a policy change may touch only the policy files "
                          f"({', '.join(policy_lane_paths(config))}).")
        else:
            # The decision the gate cannot make, offered as the one command that
            # records it (#62). The person still says yes; they just stop typing YAML.
            errors.append(
                f"{v.filepath}: outside lane '{lane_name}'.\n"
                f"      If this file belongs in this lane: "
                f"{inv} allow --lane {lane_name} {v.filepath}")
    return CheckReport(lane=lane_name, base=base, head=head, result=result, errors=errors,
                       where=where)


def location_lines(report: CheckReport) -> List[str]:
    """Where the check ran, and the one warning that tells the two windows apart."""
    where = report.where
    if where is None:
        return []
    lines = []
    if where.is_worktree:
        who = f"{where.agent_id}'s worktree" if where.agent_id else "an agent worktree"
        lines.append(f"  in {where.root} — {who}, lane '{where.lane}'")
        if where.lane and where.lane != report.lane and report.lane != POLICY_LANE:
            lines.append(
                f"  ⚠️  This worktree's .lane says '{where.lane}', but the check was asked "
                f"about '{report.lane}'. If this is {where.agent_id or 'the agent'}'s work, "
                f"you probably meant --lane {where.lane}.")
    else:
        lines.append(f"  in {where.root} — the main checkout")
        if where.worktrees and report.lane != POLICY_LANE:
            lines.append(
                f"  ℹ️  Agent worktrees exist: {', '.join(where.worktrees)}. To check an "
                f"agent's work, run this from inside its worktree.")
    return lines


def render(report: CheckReport) -> str:
    lines = [f"🛡️  LANE CHECK — lane '{report.lane}', {report.base}...{report.head}"]
    lines += location_lines(report)
    lines.append("")
    n = len(report.result.allowed_files)
    if report.passed:
        noun = "file stays" if n == 1 else "files stay"
        lines.append(f"  ✓ All {n} changed {noun} inside the lane.")
        if report.result.generated_files:
            lines.append(f"  ({len(report.result.generated_files)} generated file(s) left "
                         f"out, as the policy says: "
                         f"{', '.join(report.result.generated_files)})")
        lines += ["", "✅ CHECK PASSED"]
    else:
        for err in report.errors:
            lines.append(f"  ✗ {err}")
        if report.result.generated_files:
            lines.append(f"  ({len(report.result.generated_files)} generated file(s) left "
                         f"out, as the policy says: "
                         f"{', '.join(report.result.generated_files)})")
        lines += ["", "❌ CHECK FAILED: this change leaves its lane."]
    return "\n".join(lines)


def github_summary(report: CheckReport) -> str:
    """The verdict as markdown for `$GITHUB_STEP_SUMMARY` (#79).

    The whole product is one line — `✗ README.md: outside lane 'feat-02'` — and in CI
    that line was behind a click, an Actions page and a scroll past `pip install`. The
    run page renders this above the log. A pass gets a line too: a reviewer should be
    able to see that the boundary was actually checked, not just that something was
    green.
    """
    lines = [f"### Lane check — `{report.lane}`", ""]
    n = len(report.result.allowed_files)
    if report.passed:
        noun = "file stays" if n == 1 else "files stay"
        lines.append(f"✅ **Passed.** All {n} changed {noun} inside lane `{report.lane}`.")
    else:
        lines.append("❌ **Failed: this change leaves its lane.**")
        lines.append("")
        for err in report.errors:
            first, _, rest = err.partition("\n")
            lines.append(f"- {first}")
            if rest.strip():
                lines.append(f"  {rest.strip()}")
    if report.result.generated_files:
        lines.append("")
        lines.append(f"_{len(report.result.generated_files)} generated file(s) left out, "
                     f"as the policy says: {', '.join(report.result.generated_files)}_")
    lines.append("")
    lines.append(f"_Compared `{report.base}...{report.head}`._")
    return "\n".join(lines) + "\n"


def annotations(report: CheckReport) -> List[str]:
    """Workflow commands that put each violation on the pull request's Files tab.

    `::error file=<path>::<message>` needs no permission beyond running: the runner
    reads it from the step's stdout. Only violations that name a file are annotated;
    a change that could not be read at all is one error against the run.
    """
    out: List[str] = []
    for err in report.errors:
        first = err.split("\n", 1)[0]
        path, sep, message = first.partition(": ")
        if not sep or "/" not in path and "." not in path and not path:
            continue
        if " " in path.strip():
            continue
        clean = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        out.append(f"::error file={path.strip()},title=Lane check::{clean}")
    return out


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
          HEAD_REF: ${{{{ github.head_ref }}}}
        # `--lane-from-branch`: a branch lanekeeper made carries its lane in its name,
        # so a forgotten label is not a red X. A label still wins, and a label that
        # disagrees with the branch fails. `--github` writes the verdict to the run
        # page and annotates each violated file on the Files tab.
        run: |
          lanekeeper check --labels-json "$LABELS" --label-prefix "{label_prefix}" \\
            --base "$BASE" --branch "$HEAD_REF" --lane-from-branch --github
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
