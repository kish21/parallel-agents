"""Step 2 assembled: from the tickets step 1 read to a division and its collisions.

It decides; it does not print, and it does not read the tracker. The tickets arrive on
the `IntakeResult` because step 1 already listed them, and asking a live backlog twice
in one command is how two halves of one answer come to disagree.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ..layout import tracked_files
from .advisor import Advisor, AdvisorError
from .models import CodeSlice, DivisionProposal, PathSource, ProposedLane, TicketBoundary
from . import boundary, codebase, collision, grouping


def propose(root: Path, settings, intake_result, files: Sequence[str] = None,
            advisor: Optional[Advisor] = None,
            board_lanes: Optional[Dict[str, str]] = None,
            notes: Optional[List[str]] = None) -> DivisionProposal:
    """The whole of step 2's answer for one run.

    `files` is injectable so the tests can describe a repository without building one,
    and so this module never has to care that reading them means running git.

    `board_lanes` maps a ticket number to the Lane set on the board. It outranks the
    form's free-text field: a lane somebody chose from a list, on the board everyone
    looks at, is a decision; the form field is a hint the form itself says to leave
    blank when unsure.

    `advisor` is asked about one thing only: a ticket that names no files and that
    nothing in the code matches. Its answer is a suggestion, marked as such, that the
    draft shows switched off. `notes` collects anything the advisor could not do, for
    the caller to print — this module does not print.
    """
    listed = list(files) if files is not None else tracked_files(root)
    boundaries = boundary.read_all(intake_result.issues, settings)
    if board_lanes:
        boundaries = [
            replace(b, declared_lane=board_lanes[b.ref]) if board_lanes.get(b.ref) else b
            for b in boundaries
        ]
    slices, code_note = codebase.slices(root, settings, files=listed)

    draft = grouping.proposal(boundaries, slices, settings, code_note=code_note)
    if advisor is not None and draft.unplaced:
        draft = _ask_advisor(draft, advisor, intake_result.issues, listed, notes)

    overlaps = collision.report(draft.lanes, listed, settings)
    wider = _wider_paths(draft.lanes, slices)
    unclaimed = collision.unclaimed(draft.lanes, listed,
                                    settings.thresholds.unclaimed_examples)
    ignored = tuple((b.ref, b.ignored_lines) for b in boundaries if b.ignored_lines)
    return DivisionProposal(
        lanes=draft.lanes,
        ignored_lines=ignored,
        unplaced=draft.unplaced,
        needs_paths=draft.needs_paths,
        overlaps=tuple(overlaps),
        code_slices=draft.code_slices,
        unclaimed_examples=unclaimed,
        wider_paths=wider,
        ticket_count=draft.ticket_count,
        code_note=draft.code_note,
    )


def _ask_advisor(draft: DivisionProposal, advisor: Advisor, issues, files: Sequence[str],
                 notes: Optional[List[str]]) -> DivisionProposal:
    """Moves an unplaced ticket to "needs paths" when the advisor has a suggestion.

    Only tickets nothing else could place are sent, and only paths that name something
    in the project come back (the advisor filters its own answer). A suggestion is
    stored with `PathSource.PROPOSED`, which the draft renders commented out with a
    note saying nobody has confirmed it.
    """
    bodies = {str(i.ref): i for i in issues}
    still_unplaced: List[TicketBoundary] = []
    suggested: List[TicketBoundary] = list(draft.needs_paths)
    for index, b in enumerate(draft.unplaced):
        issue = bodies.get(b.ref)
        try:
            paths = advisor.propose_paths(b.ref, b.title, issue.body if issue else "", files)
        except AdvisorError as exc:
            # Said once, and the rest stay unplaced rather than being asked again.
            if notes is not None:
                notes.append(str(exc))
            still_unplaced.extend(draft.unplaced[index:])
            break
        if paths:
            suggested.append(replace(b, paths=tuple(paths), source=PathSource.PROPOSED))
        else:
            still_unplaced.append(b)
    return replace(draft, needs_paths=tuple(suggested), unplaced=tuple(still_unplaced))


def _wider_paths(lanes: Sequence[ProposedLane], slices: Sequence[CodeSlice]):
    """For an entry whose files were listed one by one, the part of the project they
    sit in.

    A ticket naming three files is stating what it changes, not what the work may grow
    into — and the first new file an agent writes would sit outside a boundary made of
    exactly those three. So the wider claim is offered, switched off, for the user to
    accept or ignore.

    Never applied here. Widening a boundary on somebody's behalf hands an agent more
    than any ticket asked for, which is the opposite of what a boundary is for.
    """
    by_name = {slice_.name: slice_ for slice_ in slices}
    offers = []
    for lane in lanes:
        slice_ = by_name.get(lane.name)
        if slice_ is None or any("*" in path for path in lane.paths):
            continue
        # The comparison is "is this wider claim already being made", not "do the
        # entry's files sit inside it" — every one of them does, which is exactly why
        # the wider claim is worth offering.
        missing = tuple(path for path in slice_.paths if path not in lane.paths)
        if missing:
            offers.append((lane.name, missing))
    return tuple(offers)
