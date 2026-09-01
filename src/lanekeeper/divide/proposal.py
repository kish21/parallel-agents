"""Step 2 assembled: from the tickets step 1 read to a division and its collisions.

It decides; it does not print, and it does not read the tracker. The tickets arrive on
the `IntakeResult` because step 1 already listed them, and asking a live backlog twice
in one command is how two halves of one answer come to disagree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..layout import tracked_files
from .models import CodeSlice, DivisionProposal, ProposedLane
from . import boundary, codebase, collision, grouping


def propose(root: Path, settings, intake_result, files: Sequence[str] = None
            ) -> DivisionProposal:
    """The whole of step 2's answer for one run.

    `files` is injectable so the tests can describe a repository without building one,
    and so this module never has to care that reading them means running git.
    """
    listed = list(files) if files is not None else tracked_files(root)
    boundaries = boundary.read_all(intake_result.issues, settings)
    slices, code_note = codebase.slices(root, settings, files=listed)

    draft = grouping.proposal(boundaries, slices, settings, code_note=code_note)

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
