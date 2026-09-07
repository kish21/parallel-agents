"""One ticket, one agent: the boundary read from the ticket itself.

The guided path — `start`, `divide`, the board — assumes a backlog worth dividing up
front. A person with a backlog already written does not want a division; they want to
hand ticket #12 to an agent and know the agent cannot leave it. `spawn --ticket 12` is
that, and this module is what makes a ticket enough on its own:

- the ticket's own file list (the *Allowed File Paths* or *Target Modules* section)
  is the lane's boundary — a lane can be a single ticket, bounded by what it names;
- a ticket that names no files has nothing to enforce, so the paths come from the
  person (`--allow`) or from an advisor the person confirms (`--propose`), and never
  from a guess;
- the lane is written into the policy under the ticket's own name, so `check` in CI
  reads the same boundary the agent was given.

Nothing here decides *which* files a ticket should touch. That is the filer's, the
person's, or an advisor's answer, and the last of those is shown before it is used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .capabilities import CapabilityRegistry, save_card
from .config import Config, LaneConfig, save_config
from .deps import DependencyStep
from .divide import boundary, names
from .divide.collision import patterns_intersect
from .invocation import fallback_line, invocation
from .lanes import LaneEngine
from . import paths
from .trackers.base import TrackedIssue


class Source(Enum):
    TICKET = "the ticket's own file list"
    FLAG = "--allow"
    PROPOSED = "the advisor's proposal"
    EXISTING = "the lane already in the policy"

    @property
    def paths_from(self) -> str:
        """What `config.yaml` records about where the paths came from (#70)."""
        return {Source.TICKET: "ticket", Source.FLAG: "flag",
                Source.PROPOSED: "proposed"}.get(self, "")


class NoBoundaryError(ValueError):
    """The ticket names no files and nobody supplied any: nothing to enforce."""


@dataclass
class TicketLane:
    """The lane one ticket resolves to, and where its boundary came from."""

    name: str
    paths: Tuple[str, ...]
    source: Source
    issue: TrackedIssue
    #: Existing lanes whose patterns could match a file this lane claims. Reported,
    #: never blocked on: two tickets that share a file is the person's call to make.
    collisions: List[Tuple[str, str, str]] = field(default_factory=list)
    #: Lines in the ticket's file list that were not read as paths.
    ignored_lines: Tuple[str, ...] = ()
    #: Whether the policy this lane now lives in is still uncommitted. The agent works
    #: in a worktree branched from a commit that does not carry it, so until the person
    #: commits it their first `git add -A` sweeps the policy into the agent's branch —
    #: where the gate denies it, because a policy change is its own lane.
    policy_uncommitted: bool = False

    @property
    def task(self) -> str:
        return f"#{self.issue.ref} {self.issue.title}".strip()


def lane_name(issue: TrackedIssue, explicit: str = "") -> str:
    """The ticket's tag (`[FEAT-02]` → `feat-02`), else `issue-<ref>`."""
    if explicit:
        return explicit
    return names.tag(issue.title) or f"issue-{issue.ref}"


def resolve(config: Config, issue: TrackedIssue, explicit_lane: str = "",
            allow: Sequence[str] = (), proposed: Sequence[str] = ()) -> TicketLane:
    """The lane this ticket goes into.

    A lane already in the policy under that name is reused as it is: the second agent
    on a ticket, or a re-run after a failed spawn, must not rewrite the boundary the
    first one is working under. Otherwise the boundary is, in order, what the person
    typed, what the ticket says, or what the advisor proposed and the person accepted.
    """
    name = lane_name(issue, explicit_lane)
    read = boundary.read(issue, config.divide)
    if config.has_lane(name):
        lane = config.get_lane(name)
        return TicketLane(name, tuple(lane.allow), Source.EXISTING, issue,
                          ignored_lines=read.ignored_lines)
    if allow:
        paths, source = tuple(_clean(allow)), Source.FLAG
    elif read.paths:
        paths, source = tuple(read.paths), Source.TICKET
    elif proposed:
        paths, source = tuple(_clean(proposed)), Source.PROPOSED
    else:
        raise NoBoundaryError(
            f"Ticket #{issue.ref} ({issue.title!r}) names no files, so there is no "
            f"boundary to give an agent. Say which files it may touch with "
            f"--allow 'src/checkout/**' (repeatable), or let Claude Code propose them "
            f"with --propose.")
    result = TicketLane(name, paths, source, issue, ignored_lines=read.ignored_lines)
    result.collisions = collisions(config, name, paths)
    return result


def collisions(config: Config, name: str, paths: Sequence[str]) -> List[Tuple[str, str, str]]:
    """(other lane, its pattern, our pattern) for every pair that could share a file.

    A shared zone is left out: it is the *remedy* for an overlap, checked before either
    lane's own `allow`, so counting it would report the fix as the problem. A retired
    lane is left out too (#70): its work is finished, and a warning that names overlaps
    with lanes from months ago is a warning people learn to skip — and this one is
    load-bearing.
    """
    zones = [p for lane in config.lanes.values() if lane.shared for p in lane.allow]
    found = []
    for other in sorted(config.lanes):
        if other == name or config.lanes[other].shared or config.lanes[other].retired:
            continue
        for theirs in config.lanes[other].allow:
            for ours in paths:
                if not patterns_intersect(theirs, ours):
                    continue
                # An overlap a shared zone already *covers* is that zone doing its job:
                # without this, marking the file shared would leave the warning printed
                # every time regardless. Covers, not merely touches — a zone holding
                # one file inside `src/domain/**` settles that file, not the directory,
                # and the review caught a first version that silenced the whole overlap.
                if any(covers(z, contested_pattern(theirs, ours)) for z in zones):
                    continue
                found.append((other, theirs, ours))
    return found


def covers(zone: str, pattern: str) -> bool:
    """Whether everything `pattern` could match is inside `zone`.

    Exact for the shapes that occur: an identical pattern, a literal path inside a
    zone glob, a directory glob under a wider directory glob. Anything else is not
    covered, which errs towards reporting an overlap — the safe side of the guess.
    """
    if zone == pattern:
        return True
    if not any(c in pattern for c in "*?["):
        return LaneEngine.match_glob(pattern, zone)
    if zone.endswith("/**") and pattern.startswith(zone[:-2]):
        return True
    return False


def ensure_lane(config: Config, root: Path, lane: TicketLane) -> Tuple[bool, List[str]]:
    """Writes the lane into the policy, and lets every scoped seat card into it.

    Returns (created, seats widened). Both are changes to the policy files, made by the
    person who ran the command — the same person `check` requires for a policy change.
    A seat card with an exhaustive lane scope would otherwise refuse the new lane, and
    the point of this command is that one ticket is enough.
    """
    created = False
    if not config.has_lane(lane.name):
        # The ticket and where the paths came from are written down with the lane
        # (#70), so a person reading the file later can answer "what is this for" and
        # "did anybody actually decide these paths" without this command's scrollback.
        config.lanes[lane.name] = LaneConfig(
            name=lane.name, allow=list(lane.paths), deny=[],
            ticket=str(lane.issue.ref), paths_from=lane.source.paths_from)
        save_config(config, root)
        created = True
    widened = []
    for seat, card in sorted(CapabilityRegistry.load(root).cards.items()):
        if card.max_allowed_lane_scope and lane.name not in card.max_allowed_lane_scope:
            card.max_allowed_lane_scope.append(lane.name)
            save_card(card, root)
            widened.append(seat)
    return created, widened


def policy_is_uncommitted(root: Path, runner=None) -> bool:
    """Whether the policy files differ from what git has recorded.

    Anything but a clean status counts — untracked on a first run, modified on a later
    one. A git that cannot answer is treated as clean: this drives a warning, and a
    warning nobody can act on is worse than none.
    """
    from .paths import policy_paths

    run = runner or (lambda argv: subprocess.run(
        argv, cwd=str(root), capture_output=True, text=True,
        encoding="utf-8", errors="replace"))
    try:
        res = run(["git", "status", "--porcelain", "--", *policy_paths()])
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0 and bool((res.stdout or "").strip())


def _clean(values: Sequence[str]) -> List[str]:
    out: List[str] = []
    for value in values:
        for part in str(value).split(","):
            norm = boundary.normalise(part)
            if norm and norm not in out:
                out.append(norm)
    return out


def describe(lane: TicketLane, created: bool, widened: Sequence[str]) -> str:
    lines = [f"🎫 Ticket #{lane.issue.ref}: {lane.issue.title}"]
    if lane.source is Source.EXISTING:
        lines.append(f"   Lane '{lane.name}' is already in the policy; using its boundary as it is.")
    else:
        lines.append(f"   Lane '{lane.name}', bounded by {lane.source.value}:")
    for p in lane.paths:
        lines.append(f"     {p}")
    for line in lane.ignored_lines:
        lines.append(f"   (not read as a path: {line!r})")
    if created:
        lines.append("   Written into the policy so the pull-request gate checks the same boundary.")
    if widened:
        lines.append(f"   Seat card{'s' if len(widened) > 1 else ''} {', '.join(widened)} "
                     f"now allow{'' if len(widened) > 1 else 's'} this lane.")
    return "\n".join(lines)


def contested_pattern(theirs: str, ours: str) -> str:
    """Of two overlapping patterns, the one that names the smaller zone.

    That is the zone to share: when `feat-02` claims `src/pages/**` and this ticket
    claims `src/pages/checkout/**`, the contested code is the checkout page, not every
    page. Fewer wildcards is narrower; on a tie the longer spelling is the more
    specific one. Two identical patterns — the common case, one file named on two
    tickets — are their own answer.
    """
    def width(pattern: str) -> Tuple[int, int]:
        return (pattern.count("*"), -len(pattern))
    return min((theirs, ours), key=width)


def shared_zone_paths(lane: TicketLane) -> List[str]:
    """The paths a shared zone would need to hold to settle every overlap reported."""
    out: List[str] = []
    for _, theirs, ours in lane.collisions:
        contested = contested_pattern(theirs, ours)
        if contested not in out:
            out.append(contested)
    return out


def collision_report(lane: TicketLane, root: Optional[Path] = None) -> str:
    """The overlap, what the gate will do about it, and the answer that already exists.

    Printed *before* the lane is written and long before a worktree exists (#80). The
    old wording said "settle it first" three lines after the lane had gone into the
    policy and just before the agent was started, so the advice was about a decision
    already taken the other way.

    Three things the old line did not say. Both lanes allow the file, so both agents'
    checks pass and the clash surfaces at merge — without that sentence the person is
    *more* confident after the warning, because everything afterwards is green. The
    remedy is `shared: true` (#25), built for exactly this file: a zone nobody is
    spawned into, checked before either lane's own `allow`, so a change there is
    escalated instead of quietly permitted twice. And nothing has been written yet.
    """
    if not lane.collisions:
        return ""
    zone = shared_zone_paths(lane)
    lines = [
        "⚠️  Another lane could touch the same files. Both lanes allow them, so both",
        "    agents' changes pass their own checks — and meet at merge. That is the",
        "    collision this tool exists to prevent, and the gate will not catch it:",
    ]
    for other, theirs, ours in lane.collisions:
        lines.append(f"      '{other}' claims {theirs}, this ticket claims {ours}")
    lines += [
        "",
        "    The designed answer is a shared zone: 'shared: true' on a lane nobody is",
        "    spawned into, checked before either lane's own list, so a change there is",
        f"    escalated rather than passed twice. In {paths.display_config_path(root)}:",
        "      - name: shared",
        "        shared: true",
        "        allow:",
    ]
    lines += [f"        - {p}" for p in zone]
    lines.append("")
    lines.append("    Nothing has been written yet.")
    return "\n".join(lines)


def collision_proceeding(lane: TicketLane, accepted: bool, interactive: bool) -> str:
    """The one line printed when a spawn goes ahead over an overlap."""
    if accepted:
        return ("    Proceeding: --accept-overlap says this overlap is deliberate.")
    if not interactive:
        return ("    Proceeding: there is no terminal to ask on. Pass --accept-overlap to "
                "say the overlap is deliberate, or add the shared zone above first.")
    return "    Proceeding as you asked."


def mark_shared(config: Config, root: Path, zone_paths: Sequence[str],
                name: str = "shared") -> str:
    """Writes the contested paths into a shared zone in the policy, and returns its name.

    An existing `shared: true` lane is extended rather than a second one made; a
    project with a lane already called `shared` that is not a zone gets `shared-zone`,
    because renaming somebody's lane is not this command's to do.
    """
    existing = next((l for l in config.lanes.values() if l.shared), None)
    if existing is None:
        while config.has_lane(name):
            name = f"{name}-zone" if not name.endswith("-zone") else f"{name}2"
        existing = LaneConfig(name=name, allow=[], deny=[], shared=True)
        config.lanes[name] = existing
    for p in zone_paths:
        if p not in existing.allow:
            existing.allow.append(p)
    save_config(config, root)
    return existing.name


def agent_prompt(lane: TicketLane) -> str:
    """A prompt to paste into whatever coding agent works in this worktree.

    The boundary is in `.lane`, but nothing makes an agent read it: the first real
    user watched one get the scope right and could not tell whether it would next
    time. A prompt the person pastes is deterministic in a way that hoping is not.
    """
    task = f"{lane.issue.title or ('issue #' + str(lane.issue.ref))} (#{lane.issue.ref})"
    return build_prompt(task, lane.paths)


def build_prompt(task: str, files: Sequence[str]) -> str:
    """The one wording of the instruction, used by `spawn --ticket` and by `work`."""
    listed = ", ".join(files)
    return (f"Implement {task}. You may only create or modify these files: {listed}. "
            f"If the task needs a file that is not in that list, stop and say so instead "
            f"of editing it — a change outside the list is rejected before it can merge.")


def commit_policy_advice(branch: str = "", protected: Sequence[str] = ("main", "master"),
                         root: Optional[Path] = None) -> str:
    """Where to commit the policy, said without naming a branch it should not go on.

    The old sentence said "Commit the policy here, on 'main'". "Here" meant the main
    checkout as opposed to the agent's worktree, and "main" was the repository's
    default branch whatever the person was on — so a tester on `my-test` was told to
    switch branches, and told to commit straight to a branch that the very file being
    committed lists under `protected_branches` (#69). The correct advice is: in this
    checkout, on the branch you are on, and land it as a pull request labelled
    `lane: policy`, like any other change.
    """
    home = paths.display_home(root).rstrip("/")
    commit = f"git add {home} .gitignore && git commit -m 'Add the lane policy'"
    if branch and branch not in protected:
        where = (f"Commit the policy on '{branch}' — in this checkout, not inside the "
                 f"agent's worktree — before you commit anything else, and open it as a "
                 f"pull request labelled 'lane: policy'.")
    else:
        where = (f"Commit the policy before you commit anything else — in this checkout, "
                 f"not inside the agent's worktree, and ideally on a branch of its own, "
                 f"opened as a pull request labelled 'lane: policy'.")
    return (f"{where} CI can only enforce a policy that is in the repository, and an "
            f"uncommitted one gets swept into your next 'git add -A' by accident, where "
            f"the gate denies it — a policy change is its own lane:\n      {commit}")


def next_steps(lane: TicketLane, gate_workflow_exists: bool, base: str = "main",
               branch: Optional[str] = None,
               protected: Sequence[str] = ("main", "master"),
               root: Optional[Path] = None) -> str:
    """`base` is kept for callers that still pass it; the advice no longer names it."""
    inv = invocation()
    lines = []
    if not gate_workflow_exists:
        lines.append("The gate is not installed yet. It is one file — the GitHub Action "
                     "that runs this check on every pull request:\n"
                     f"      {inv} install-gate")
    if lane.policy_uncommitted:
        lines.append(commit_policy_advice(branch if branch is not None else base,
                                          protected, root))
    lines.append(f"When the agent opens its pull request, label it 'lane: {lane.name}'. "
                 f"The gate fails the change if any file is outside the lane.")
    return "\n".join(f"  • {line}" for line in lines)


def _short(worktree: Path, root: Optional[Path] = None) -> str:
    """The worktree path as the person would type it — relative when it is inside the
    repository, which is the default. An absolute Windows path printed three times is
    most of what made this section look like a wall of text."""
    try:
        return str(worktree.relative_to(root or Path.cwd())).replace("\\", "/")
    except (ValueError, OSError):
        return str(worktree)


def install_step(where: str, step: Optional[DependencyStep]) -> List[str]:
    """The dependency step, or nothing for a project that has none (#73)."""
    if step is None:
        return []
    if step.command:
        return [
            f"Once per worktree, install the dependencies — a worktree is a fresh",
            f"checkout, so it has none ({step.evidence} says how):",
            "",
            f"       cd {where} && {step.command}",
        ]
    return [
        f"A fresh worktree has no dependencies installed, and this project has a",
        f"{step.evidence} but no lockfile — so which install command to run in",
        f"{where} is your call. Once per worktree, not once per task.",
    ]


def how_to_work(lane: TicketLane, worktree: Path, agent_id: str,
                root: Optional[Path] = None, editor_opened: bool = False,
                dependencies: Optional[DependencyStep] = None) -> str:
    """What to actually do next, which is where the first real user got stuck.

    Everything else `spawn` prints is bookkeeping — the policy, the label, the gate.
    None of it says "now do the work", and a person looking at a freshly opened
    editor has no idea that the tool has finished its part.

    `editor_opened` is whether a window was actually opened (#67): the first wording
    told everybody "the editor window that just opened is already there", and without
    `--open` no window had opened. Being told to look at a window that is not there is
    the kind of small wrongness that makes somebody doubt everything else the tool
    just said — in the block that exists to be the first thing they trust.
    """
    where = _short(worktree, root)
    inv = invocation()
    steps: List[List[str]] = []
    steps.append(install_step(where, dependencies))
    if editor_opened:
        steps.append([
            f"In {where} — the editor window that just opened is already",
            "there — start your coding agent: claude, cursor, whatever you use.",
        ])
    else:
        steps.append([
            f"Open {where} in your editor ('{inv} open {agent_id}' does it),",
            "then start your coding agent there: claude, cursor, whatever you use.",
        ])
    steps.append([
        "Give it the task and its boundary. This prompt carries both:",
        "",
        f"  {agent_prompt(lane)}",
    ])
    steps.append([
        "When it is done, from that same folder:",
        "",
        f"  {inv} check --lane {lane.name} --base main --working-tree",
        "",
        "Green means every changed file is inside the boundary; red names the one",
        f"that is not. The same boundary is in {where}/.lane.",
    ])
    lines = ["▶ Now do the work. Lanekeeper has prepared the desk; it does not write code."]
    n = 0
    for step in steps:
        if not step:
            continue
        n += 1
        lines.append("")
        lines.append(f"  {n}. {step[0]}")
        lines += [f"     {line}" if line else "" for line in step[1:]]
    # The check runs in a different window from the one this was printed in, and that
    # window's PATH is not ours to fix (#76). Said once, here, where the hand-over is.
    fallback = fallback_line(inv)
    if fallback:
        lines.append("")
        lines.append(f"     {fallback}")
    return "\n".join(lines)


def confirm_proposal(ref: str, paths: Sequence[str], answer: Optional[str]) -> bool:
    """Whether a proposed boundary was accepted. `answer` is what the person typed."""
    return bool(paths) and (answer or "").strip().lower() in ("y", "yes")
