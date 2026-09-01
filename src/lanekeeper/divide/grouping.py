"""Group the tickets where they group. Where they do not, hand each one out on its own.

The rule that shapes this module: **a backlog that does not group is not a failure.** A
lane may be a single ticket, bounded by that ticket's own Allowed File Paths, and that
is a complete lane with a real boundary and a real gate. So nothing here ever refuses,
and nothing here guesses: a ticket that shares a feature name with others joins them, a
ticket that shares one with nobody becomes its own entry, and a ticket that states no
paths at all is set aside to be asked about rather than quietly handed over.

Every decision is a comparison of strings drawn from paths. No model is called, which is
what makes two runs on the same backlog produce the same division.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

from .models import CodeSlice, DivisionProposal, PathSource, Placement, ProposedLane, TicketBoundary
from . import codebase, names as naming


def group(boundaries: Sequence[TicketBoundary], code_slices: Sequence[CodeSlice],
          settings) -> Tuple[List[ProposedLane], List[TicketBoundary], List[TicketBoundary]]:
    """Returns the lanes, the tickets with nothing to enforce, and the unplaceable.

    The three together are always the whole backlog, each ticket in exactly one of them.
    That is the promise the caller turns into a printed report, and it is checked by the
    tests as a set identity rather than case by case.
    """
    with_paths = [b for b in boundaries if b.has_boundary]
    without_paths = [b for b in boundaries if not b.has_boundary]

    lanes = _lanes_from_tickets(with_paths, settings)
    if not lanes and code_slices:
        # No ticket stated a boundary. The repository still has a structure, and a
        # proposal drawn from it is worth more than an empty page — proposed, and
        # labelled as read from the code so nobody mistakes it for what a filer wrote.
        #
        # Built before the pathless tickets are handled, not after: those tickets are
        # matched against the entries that exist, and on this path these are all of
        # them. Handling them first offered a second entry over an entry's own files,
        # which is a clash by construction.
        lanes = _lanes_from_code(code_slices)

    needs_paths, unplaced = _handle_pathless(without_paths, lanes, code_slices, settings)
    return lanes, needs_paths, unplaced


# -- grouping tickets that stated their paths ------------------------------------


def _lanes_from_tickets(boundaries: Sequence[TicketBoundary], settings) -> List[ProposedLane]:
    if not boundaries:
        return []

    candidates = {b.ref: _candidate_names(b, settings) for b in boundaries}
    counts: Dict[str, int] = defaultdict(int)
    declared: Dict[str, int] = defaultdict(int)
    for boundary in boundaries:
        for name in candidates[boundary.ref]:
            counts[name] += 1
        if boundary.declared_lane:
            declared[naming.slug(boundary.declared_lane)] += 1

    minimum = settings.thresholds.min_group_tickets
    # A name the filer wrote down groups on its own: they know the product and this
    # module does not. An inferred name has to be shared before it means anything.
    groupable = {name for name, n in counts.items() if n >= minimum} | set(declared)

    assigned: Dict[str, List[TicketBoundary]] = defaultdict(list)
    solo: List[TicketBoundary] = []
    for boundary in boundaries:
        chosen = _chosen_name(boundary, candidates[boundary.ref], groupable, counts)
        if chosen:
            assigned[chosen].append(boundary)
        else:
            solo.append(boundary)

    lanes = [_lane(name, tickets, settings) for name, tickets in sorted(assigned.items())]
    # Sorted, not left in the order the tracker happened to list them. A division that
    # comes out differently on a second run is not a division anybody can review, and
    # the order tickets arrive in is an accident of the tracker either way.
    lanes += sorted((_solo_lane(boundary, settings) for boundary in solo),
                    key=lambda lane: (lane.name, lane.tickets))
    return _deduplicate_names(lanes)


def _candidate_names(boundary: TicketBoundary, settings) -> List[str]:
    names: List[str] = []
    for path in boundary.paths:
        for name in naming.candidates(path, settings):
            if name not in names:
                names.append(name)
    return names


def _chosen_name(boundary: TicketBoundary, candidates: Sequence[str],
                 groupable, counts) -> str:
    """The one entry this ticket belongs to.

    Exactly one, always: a ticket in two groups is a ticket two agents may both take.
    The filer's own answer wins; otherwise the most specific shared name, meaning the
    one covering the fewest tickets, with ties broken alphabetically so that the same
    backlog divides the same way every time.
    """
    if boundary.declared_lane:
        return naming.slug(boundary.declared_lane)
    shared = [name for name in candidates if name in groupable]
    if not shared:
        return ""
    return sorted(shared, key=lambda name: (counts.get(name, 0), name))[0]


def _lane(name: str, tickets: Sequence[TicketBoundary], settings) -> ProposedLane:
    paths = _merge_paths(tickets)
    grouped = len(tickets) > 1
    return ProposedLane(
        name=name,
        paths=paths,
        tickets=tuple(t.ref for t in tickets),
        source=PathSource.TICKET,
        placement=Placement.GROUPED if grouped else Placement.SINGLE_TICKET,
        why=(f"{len(tickets)} pieces of work name the same part of the project "
             f"({name}) in the files they touch."
             if grouped else
             "Nothing else in the list points at the same part of the project."),
    )


def _solo_lane(boundary: TicketBoundary, settings) -> ProposedLane:
    """One ticket, its own paths, no apology.

    Named after whatever its paths are about, and after the ticket itself when they are
    about nothing nameable — a lane called after its single ticket is perfectly clear.
    """
    candidates = _candidate_names(boundary, settings)
    name = candidates[0] if candidates else naming.slug(boundary.title) or f"work-{boundary.ref}"
    return ProposedLane(
        name=name,
        paths=tuple(boundary.paths),
        tickets=(boundary.ref,),
        source=PathSource.TICKET,
        placement=Placement.SINGLE_TICKET,
        why=("Nothing else in the list points at the same part of the project, so "
             "this can go to somebody by itself."),
    )


def _merge_paths(tickets: Sequence[TicketBoundary]) -> Tuple[str, ...]:
    seen: List[str] = []
    for ticket in tickets:
        for path in ticket.paths:
            if path not in seen:
                seen.append(path)
    return tuple(sorted(seen))


def _deduplicate_names(lanes: Sequence[ProposedLane]) -> List[ProposedLane]:
    """Two entries with one name would silently become one lane in the file."""
    used = set()
    out: List[ProposedLane] = []
    for lane in lanes:
        name = lane.name or "work"
        if name in used:
            suffix = lane.tickets[0] if lane.tickets else str(len(out) + 1)
            name = f"{name}-{suffix}"
        used.add(name)
        out.append(lane if name == lane.name else ProposedLane(
            name=name, paths=lane.paths, tickets=lane.tickets, source=lane.source,
            placement=lane.placement, why=lane.why))
    return out


# -- tickets that stated no paths -------------------------------------------------


def _handle_pathless(boundaries: Sequence[TicketBoundary],
                     lanes: Sequence[ProposedLane],
                     code_slices: Sequence[CodeSlice],
                     settings) -> Tuple[List[TicketBoundary], List[TicketBoundary]]:
    """Nothing to enforce, so nothing is handed over.

    A ticket with no paths has no boundary, and a lane with no boundary has no gate:
    handing it to an agent would ship a safety guarantee that quietly does not exist. So
    each one is either turned into a question — here are the paths I would suggest, are
    they right? — or listed as one lanekeeper has nothing to say about. Never a lane.
    """
    needs_paths: List[TicketBoundary] = []
    unplaced: List[TicketBoundary] = []
    known = {lane.name: lane.paths for lane in lanes}

    for boundary in boundaries:
        suggestion, belongs_with = _suggested_paths(boundary, known, code_slices,
                                                    settings)
        if suggestion:
            needs_paths.append(TicketBoundary(
                ref=boundary.ref, title=boundary.title, paths=suggestion,
                declared_lane=boundary.declared_lane, source=PathSource.PROPOSED,
                url=boundary.url, belongs_with=belongs_with))
        else:
            unplaced.append(boundary)
    return needs_paths, unplaced


def _suggested_paths(boundary: TicketBoundary, known: Dict[str, Tuple[str, ...]],
                     code_slices: Sequence[CodeSlice], settings):
    """Paths worth *asking about*, never paths to act on.

    Drawn only from names that already exist — an entry the tickets produced, or a part
    of the repository that is really there. Nothing is invented from the words in a
    title.

    When the match is an entry that already exists, the second return value names it.
    The right answer there is to add the ticket to that entry, not to make a second one
    over the same files: doing that would be a clash by construction, and confirming it
    would be refused.
    """
    wanted = []
    if boundary.declared_lane:
        wanted.append(naming.slug(boundary.declared_lane))
    wanted += naming.from_text(boundary.title, settings)

    for name in wanted:
        if name in known and known[name]:
            return tuple(known[name]), name
        from_code = codebase.paths_for(name, code_slices)
        if from_code:
            return from_code, ""
    return (), ""


# -- the fallback: a repository whose tickets say nothing -------------------------


def _lanes_from_code(code_slices: Sequence[CodeSlice]) -> List[ProposedLane]:
    return [
        ProposedLane(
            name=slice_.name,
            paths=slice_.paths,
            tickets=(),
            source=PathSource.CODE,
            placement=Placement.GROUPED,
            why=("None of the tickets say which files they change, so this comes from "
                 f"the project itself: {', '.join(slice_.evidence[:3])} all appear to "
                 f"be about {slice_.name}."),
        )
        for slice_ in code_slices
    ]


def proposal(boundaries: Sequence[TicketBoundary], code_slices: Sequence[CodeSlice],
             settings, code_note: str = "") -> DivisionProposal:
    """The whole division, with every ticket accounted for exactly once."""
    lanes, needs_paths, unplaced = group(boundaries, code_slices, settings)
    return DivisionProposal(
        lanes=tuple(lanes),
        unplaced=tuple(unplaced),
        needs_paths=tuple(needs_paths),
        code_slices=tuple(code_slices),
        ticket_count=len(boundaries),
        code_note=code_note,
    )
