"""The typed contracts crossing every boundary in step 2.

Nothing here does any work. The shapes carry the two promises step 2 has to keep and
that a dictionary would let a later step quietly break: every ticket is in exactly one
place, and a boundary always says where it came from.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class PathSource(Enum):
    """Where a boundary came from. Printed, never inferred.

    The difference matters to the person reading the proposal: a boundary the filer
    wrote is a statement, a boundary read out of the folder tree is a reading, and a
    boundary lanekeeper suggested is a question.
    """

    TICKET = "ticket"       # the filer stated it on the ticket
    CODE = "code"           # read from the files that are actually there
    PROPOSED = "proposed"   # suggested by lanekeeper, not yet confirmed by anyone


class Placement(Enum):
    GROUPED = "grouped"              # several tickets that belong together
    #: One ticket, bounded by its own paths. A complete lane, not a degraded one — a
    #: backlog that does not group is the ordinary case, not a failure to handle.
    SINGLE_TICKET = "single-ticket"
    UNPLACED = "unplaced"            # named out loud, never quietly dropped


@dataclass(frozen=True)
class TicketBoundary:
    """One ticket, and what it says about the files it touches."""

    ref: str
    title: str
    paths: Tuple[str, ...] = ()
    #: The optional free-text feature name from the form. Blank is ordinary input, not
    #: a defect: the form tells the filer to leave it blank when unsure.
    declared_lane: str = ""
    source: PathSource = PathSource.TICKET
    url: str = ""
    #: Lines in the ticket's file list that were not read as paths. Reported rather
    #: than dropped: a boundary quietly narrower than the one the filer wrote is the
    #: same defect as one quietly wider, and both end at the merge gate.
    ignored_lines: Tuple[str, ...] = ()
    #: The entry this ticket appears to belong to, when its suggested files are that
    #: entry's own. Set so the suggestion can say "add it there" instead of offering a
    #: second entry over the same files — which, if accepted, is a guaranteed clash and
    #: a refusal to write anything at all.
    belongs_with: str = ""

    @property
    def has_boundary(self) -> bool:
        return bool(self.paths)


@dataclass(frozen=True)
class CodeSlice:
    """A feature the repository itself appears to have, read from its files."""

    name: str
    paths: Tuple[str, ...] = ()
    file_count: int = 0
    #: The directories that produced the name, so a wrong reading is visible rather
    #: than being presented as a fact about the project.
    evidence: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ProposedLane:
    name: str
    paths: Tuple[str, ...]
    #: Carve-outs inside this entry's own claim. Never proposed — read back from what
    #: the user wrote, because `deny` is one of the two documented ways to answer a
    #: reported overlap, and a fix that is silently dropped is a fix that gets reported
    #: as a problem again.
    deny: Tuple[str, ...] = ()
    tickets: Tuple[str, ...] = ()
    source: PathSource = PathSource.TICKET
    placement: Placement = Placement.GROUPED
    #: One plain sentence saying why these belong together. A grouping the user cannot
    #: argue with is a grouping they cannot correct.
    why: str = ""


@dataclass(frozen=True)
class Overlap:
    """Two entries that touch the same files.

    Only the mechanical half: whether they overlap, and what proves it. Whether the
    overlap is a dependency or a collision, and whether the answer is to fuse the two
    or to declare a shared zone, is #39's question and is not asked here.
    """

    left: str
    right: str
    patterns: Tuple[Tuple[str, str], ...] = ()
    #: Real tracked files matching both sides. Evidence beats an assertion.
    example_files: Tuple[str, ...] = ()
    #: "files" when existing files prove it; "patterns-only" when the two claims
    #: overlap but nothing in the repository sits in the overlap yet. The second is
    #: weaker and says so rather than being rounded up to the first.
    kind: str = "files"


@dataclass(frozen=True)
class DivisionProposal:
    """What step 2 proposes, and everything it could not decide.

    `unplaced` and `needs_paths` are fields rather than log lines so that "every ticket
    lands somewhere, and nothing is handed over without a boundary" is a property of the
    value, checkable by a test, instead of a code path someone must remember to run.
    """

    lanes: Tuple[ProposedLane, ...] = ()
    unplaced: Tuple[TicketBoundary, ...] = ()
    needs_paths: Tuple[TicketBoundary, ...] = ()
    overlaps: Tuple[Overlap, ...] = ()
    code_slices: Tuple[CodeSlice, ...] = ()
    #: Lines from a ticket's file list that were not read as paths, per ticket. Shown,
    #: because a boundary quietly narrower than the one the filer wrote is as wrong as
    #: one quietly wider.
    ignored_lines: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()
    unclaimed_examples: Tuple[str, ...] = ()
    #: For an entry whose files are all named one by one: the wider part of the project
    #: those files sit in, as read from the code. Offered, never applied — widening a
    #: boundary on somebody's behalf hands out more than the tickets asked for.
    wider_paths: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()
    ticket_count: int = 0
    #: Where the repository's own structure was read from, or why it was not.
    code_note: str = ""

    @property
    def placed_refs(self) -> Tuple[str, ...]:
        return tuple(ref for lane in self.lanes for ref in lane.tickets)


@dataclass(frozen=True)
class DraftProblem:
    """Something about a confirmed division that stops it being written.

    Each one is a fact about what the user wrote, not an opinion about it.
    """

    kind: str            # "no-paths" | "no-lanes" | "unreadable" | "duplicate-ticket"
    subject: str         # the lane or ticket it is about
    detail: str


@dataclass(frozen=True)
class ValidationReport:
    lanes: Tuple[ProposedLane, ...] = ()
    #: Paths a shared zone covers. A file inside one belongs to the zone rather than to
    #: any entry, so two entries reaching into it is the zone doing its job, not a
    #: collision. README, §The lane file, rule 1.
    shared_paths: Tuple[str, ...] = ()
    problems: Tuple[DraftProblem, ...] = ()
    overlaps: Tuple[Overlap, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.problems and not self.overlaps
