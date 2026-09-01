"""Everything step 2 says to the user, in one place.

Same two reasons as step 1's presenter. A person running `lanekeeper start` has a
project and wants several agents on it; they should not need to know what a lane, a
worktree or a glob is to answer the one question this step asks. And a wording rule that
lives in a style guide is not enforced, whereas one asserted over a module of strings is.

This module also never suggests moving a file or renaming a folder. The division is
carved out of the project as it stands — that is what makes it usable on the messy
repositories that need it most.
"""

from __future__ import annotations

import textwrap
from typing import List, Sequence

from .models import DivisionProposal, PathSource, Placement, ValidationReport

#: Step 1's list, unchanged: these are lanekeeper's own words and the user has had no
#: reason to meet them.
BANNED_WORDS = ("lane", "lanes", "worktree", "worktrees", "seat", "seats",
                "glob", "globs", "branch", "merge base")


#: A list of titles longer than this stops being a report and becomes a wall. The rest
#: are counted rather than printed; every one of them is still in the draft file.
UNPLACED_SHOWN = 8


def render(proposal: DivisionProposal, draft_file: str,
           draft_written: bool = True) -> str:
    """The proposal, and the one question it asks."""
    lines: List[str] = [_headline(proposal), ""]
    lines += _group_lines(proposal)

    if proposal.needs_paths:
        lines += [""] + _needs_paths_lines(proposal)
    if proposal.unplaced:
        lines += [""] + _unplaced_lines(proposal)
    if proposal.ignored_lines:
        lines += [""] + _ignored_lines(proposal)
    if proposal.overlaps:
        lines += [""] + _overlap_lines(proposal)
    # Only worth saying when something was actually claimed. On a proposal with no
    # groups at all, "some files belong to nobody" is every file, and true of nothing.
    if proposal.unclaimed_examples and proposal.lanes:
        lines += [""] + _unclaimed_lines(proposal)

    lines += [""] + _next_lines(proposal, draft_file, draft_written)
    return "\n".join(lines).rstrip() + "\n"


def render_confirmation(report: ValidationReport, written: str = "",
                        policy: str = "") -> str:
    """What confirming said: either what was written, or what stopped it."""
    if report.ok:
        lines = [
            f"✅ Written down: {_groups(len(report.lanes))}, each with its own "
            "set of files.",
            "",
            f"   The record is {written}. It is yours to edit from here.",
        ]
        if policy:
            lines += [
                f"   The same groups are now the 'lanes' in {policy}, which is what",
                "   'spawn', 'validate' and 'check' hold every agent to.",
            ]
        lines.append("")
        for lane in report.lanes:
            lines.append(f"     • {lane.name} — {_files(len(lane.paths))}")
        return "\n".join(lines).rstrip() + "\n"

    lines = ["🛑 I have not written anything, because of this:", ""]
    for problem in report.problems:
        lines += _wrapped(problem.detail)
    for overlap in report.overlaps:
        lines += _wrapped(_overlap_sentence(overlap))
    lines += [
        "",
        "   Fix those in the same file and run the same command again. Nothing has",
        "   changed in your project in the meantime.",
    ]
    return "\n".join(lines).rstrip() + "\n"


# -- the parts of a proposal ------------------------------------------------------


def _headline(proposal: DivisionProposal) -> str:
    if not proposal.lanes:
        return "📋 I could not see a way to split this up on my own."
    if not proposal.placed_refs:
        # The groups came from the project's own files, and none of the written-down
        # work is inside one of them. Saying "here is how I would share out 18 pieces
        # of work" would describe something that has not happened.
        return (f"📋 None of {_count(proposal.ticket_count)} says which files it "
                f"changes, so here is how this project looks to me instead — "
                f"{len(proposal.lanes)} parts.")
    grouped = sum(1 for lane in proposal.lanes if lane.placement is Placement.GROUPED)
    if grouped:
        return (f"📋 Here is how I would share out {_count(proposal.ticket_count)} — "
                f"{len(proposal.lanes)} groups, one for each agent.")
    # Nothing grouped. That is an ordinary answer, and saying so plainly is better than
    # dressing up a list of single items as a discovery.
    return (f"📋 Nothing in this list groups together, so here is each piece on its "
            f"own — {_count(proposal.ticket_count)}.")


def _group_lines(proposal: DivisionProposal) -> List[str]:
    if not proposal.lanes:
        # The commonest reason, and the one with something to do about it: the tickets
        # were written before anybody asked them which files they touch. Saying that is
        # worth more than repeating the whole list back.
        return _wrapped(
            "None of these say which files they change, and I could not see a split "
            "in the project itself either, so I have not proposed anything. What "
            "would fix it: each ticket has a place to list the files it touches — "
            "filling that in on even a few of them is enough for me to start.")

    lines: List[str] = []
    for lane in proposal.lanes:
        tickets = ", ".join(f"#{ref}" for ref in lane.tickets)
        heading = f"   {lane.name}"
        if tickets:
            heading += f"  ({tickets})"
        lines.append(heading)
        lines += [f"       {line}" for line in textwrap.wrap(lane.why, width=68)]
        lines.append(f"       Files it would cover: {_examples(lane.paths)}")
        lines.append(f"       Where that came from: {_source(lane.source)}")
        lines.append("")
    return lines


def _needs_paths_lines(proposal: DivisionProposal) -> List[str]:
    lines = _wrapped(
        "These do not say which files they change. I cannot hold anybody to a piece "
        "of work whose edges nobody has written down, so I have not given them out. "
        "My guess at where each belongs is in the file below, switched off until you "
        "say it is right:")
    for boundary in proposal.needs_paths:
        lines.append(f"       #{boundary.ref}  {_short(boundary.title)}")
        if boundary.belongs_with:
            lines.append(f"          Looks like part of '{boundary.belongs_with}' — "
                         "add its number there.")
        else:
            lines.append(f"          I would guess: {_examples(boundary.paths)}")
    return lines


def _unplaced_lines(proposal: DivisionProposal) -> List[str]:
    lines = _wrapped(
        "I have nothing at all to say about these — they name no files, and nothing "
        "in the project matches what they are called:")
    for boundary in proposal.unplaced[:UNPLACED_SHOWN]:
        lines.append(f"       #{boundary.ref}  {_short(boundary.title)}")
    remaining = len(proposal.unplaced) - UNPLACED_SHOWN
    if remaining > 0:
        lines.append(f"       (and {remaining} more, all of them in the file below)")
    lines += _wrapped(
        "Adding the files each one changes, on the ticket itself, is what would let "
        "me place it.")
    return lines


def _ignored_lines(proposal: DivisionProposal) -> List[str]:
    """Lines in a ticket's file list that did not read as a file.

    Usually a note the filer added, and then this is a formality. Sometimes it is a
    file they meant to include, and then saying nothing would hand somebody a smaller
    boundary than the one they wrote without either of us noticing.
    """
    lines = _wrapped(
        "Some lines in these did not look like a file to me, so they are not part of "
        "what I would hold anybody to. If one of them was meant to be, it is worth "
        "putting on its own line:")
    for ref, ignored in proposal.ignored_lines[:5]:
        for text in ignored[:2]:
            lines.append(f"       #{ref}: {_short(text, 58)}")
    return lines


def _overlap_lines(proposal: DivisionProposal) -> List[str]:
    lines = _wrapped(
        "Two of these would be working on the same files. That is the one thing here "
        "you cannot see by reading the list, so it is worth settling before anybody "
        "starts:")
    for overlap in proposal.overlaps:
        lines += _wrapped(_overlap_sentence(overlap))
    return lines


def _overlap_sentence(overlap) -> str:
    if overlap.kind == "files":
        shown = ", ".join(overlap.example_files[:3])
        return (f"{overlap.left} and {overlap.right} both cover {shown}"
                f"{' and others' if len(overlap.example_files) > 3 else ''}.")
    return (f"{overlap.left} and {overlap.right} do not share any file that exists "
            "today, but they are written widely enough that the next file added could "
            "belong to either.")


def _unclaimed_lines(proposal: DivisionProposal) -> List[str]:
    return _wrapped(
        "Some files belong to nobody in this split, for example "
        f"{', '.join(proposal.unclaimed_examples[:3])}. That is normal and not a "
        "problem to fix now; it only matters when somebody needs to change one.")


def _next_lines(proposal: DivisionProposal, draft_file: str,
                draft_written: bool = True) -> List[str]:
    # A second run must not throw away the answer the user came back to give, so when
    # their file is already there it is left alone and the message says so.
    if draft_written:
        wrote = [f"   I have written all of the above to {draft_file}."]
    else:
        wrote = [
            f"   You already have a copy of this at {draft_file}, with whatever you",
            "   changed in it, so I have left it exactly as it is. To start again from",
            "   my own suggestion instead, add --redraft.",
        ]
    return [
        "   Nothing is decided, and I have changed nothing in your project.",
        *wrote,
        "",
        "   Have a look and change whatever is wrong — join two of them, split one,",
        "   rename them, delete the ones you do not want given out, or add the files",
        "   a piece of work is missing. Then run:",
        "",
        "     lanekeeper divide --confirm",
    ]


# -- small helpers ----------------------------------------------------------------


def _source(source: PathSource) -> str:
    return {
        PathSource.TICKET: "the files the tickets themselves name.",
        PathSource.CODE: "the files that are already in this project.",
        PathSource.PROPOSED: "my own suggestion — nobody has confirmed it.",
    }[source]


def _examples(paths: Sequence[str], limit: int = 3) -> str:
    if not paths:
        return "none stated"
    shown = ", ".join(paths[:limit])
    return shown if len(paths) <= limit else f"{shown} (and {len(paths) - limit} more)"


def _wrapped(detail: str) -> List[str]:
    wrapped = textwrap.wrap(detail, width=72)
    return [f"     • {wrapped[0]}"] + [f"       {line}" for line in wrapped[1:]]


def _short(title: str, width: int = 62) -> str:
    text = (title or "").strip()
    return text if len(text) <= width else text[:width - 1].rstrip() + "…"


def _count(n: int) -> str:
    return "1 piece of work" if n == 1 else f"{n} pieces of work"


def _files(n: int) -> str:
    return "1 set of files" if n == 1 else f"{n} sets of files"


def _groups(n: int) -> str:
    return "1 group of work" if n == 1 else f"{n} groups of work"
