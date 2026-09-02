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
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .capabilities import CapabilityRegistry, save_card
from .config import Config, LaneConfig, save_config
from .divide import boundary, names
from .divide.collision import patterns_intersect
from .trackers.base import TrackedIssue


class Source(Enum):
    TICKET = "the ticket's own file list"
    FLAG = "--allow"
    PROPOSED = "the advisor's proposal"
    EXISTING = "the lane already in the policy"


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
    """(other lane, its pattern, our pattern) for every pair that could share a file."""
    found = []
    for other in sorted(config.lanes):
        if other == name:
            continue
        for theirs in config.lanes[other].allow:
            for ours in paths:
                if patterns_intersect(theirs, ours):
                    found.append((other, theirs, ours))
    return found


def ensure_lane(config: Config, root: Path, lane: TicketLane) -> Tuple[bool, List[str]]:
    """Writes the lane into the policy, and lets every scoped seat card into it.

    Returns (created, seats widened). Both are changes to the policy files, made by the
    person who ran the command — the same person `check` requires for a policy change.
    A seat card with an exhaustive lane scope would otherwise refuse the new lane, and
    the point of this command is that one ticket is enough.
    """
    created = False
    if not config.has_lane(lane.name):
        config.lanes[lane.name] = LaneConfig(name=lane.name, allow=list(lane.paths), deny=[])
        save_config(config, root)
        created = True
    widened = []
    for seat, card in sorted(CapabilityRegistry.load(root).cards.items()):
        if card.max_allowed_lane_scope and lane.name not in card.max_allowed_lane_scope:
            card.max_allowed_lane_scope.append(lane.name)
            save_card(card, root)
            widened.append(seat)
    return created, widened


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
    if lane.collisions:
        lines.append("")
        lines.append("   ⚠️  Another lane could touch the same files. Two agents on one file "
                     "is the collision this tool exists to prevent, so settle it first:")
        for other, theirs, ours in lane.collisions:
            lines.append(f"     '{other}' claims {theirs}, this ticket claims {ours}")
    return "\n".join(lines)


def next_steps(lane: TicketLane, gate_workflow_exists: bool) -> str:
    lines = [f"When the agent opens its pull request, label it 'lane: {lane.name}'. "
             f"The gate fails the change if any file is outside the lane."]
    if not gate_workflow_exists:
        lines.append("The gate is not installed yet: run 'lanekeeper check --write-workflow' "
                     "once and commit the workflow.")
    return "\n".join(f"  • {line}" for line in lines)


def confirm_proposal(ref: str, paths: Sequence[str], answer: Optional[str]) -> bool:
    """Whether a proposed boundary was accepted. `answer` is what the person typed."""
    return bool(paths) and (answer or "").strip().lower() in ("y", "yes")
