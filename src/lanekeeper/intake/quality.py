"""Are the tickets usable for dividing work between people?

Getting the work organised is lanekeeper's job, not a precondition it demands — so this
module does not refuse to proceed. It names what is unclear and what would fix it. Step
2 groups tickets into modules, and it can only do that if a ticket says something about
what it touches, so these are the things that make step 2 guess.

This module reports. It never edits anybody's tickets: rewriting a live backlog is an
outward-facing action that belongs behind its own confirmation, not inside a report.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List, Sequence, Tuple

from .models import FlagKind, QualityFlag

#: A path mentioned in the ticket (`backend/app/api.py`, `frontend/src/**`) or a bare
#: filename carrying a code extension (`CheckoutPage.tsx`). The extension list is what
#: stops "e.g." and "Node.js" counting as a statement about which code is touched.
_PATH_HINT = re.compile(r"[A-Za-z0-9_.\-*]+/[A-Za-z0-9_.\-*/]+"
                        r"|[A-Za-z0-9_\-]+\.[A-Za-z0-9]{1,10}\b")
#: A link is about the world outside this repository, never about a file inside it.
_URL = re.compile(r"\bhttps?://\S+|\bwww\.\S+")
#: Extensions that name code, configuration or documentation in a repository.
CODE_EXTENSIONS = {
    "py", "pyi", "js", "jsx", "mjs", "cjs", "ts", "tsx", "vue", "svelte", "go", "rs",
    "rb", "java", "kt", "kts", "cs", "php", "ex", "exs", "swift", "c", "h", "cpp",
    "hpp", "css", "scss", "less", "html", "sql", "prisma", "graphql", "proto", "sh",
    "bash", "ps1", "tf", "yaml", "yml", "toml", "ini", "cfg", "json", "env", "lock",
    "dockerfile", "makefile", "md", "rst", "txt", "csv",
}


def inspect(issues: Sequence, thresholds) -> Tuple[QualityFlag, ...]:
    """Everything about this backlog that would make step 2 guess."""
    flags: List[QualityFlag] = []

    no_hint = tuple(i.ref for i in issues if not _file_hints(i))
    if no_hint:
        flags.append(QualityFlag(
            kind=FlagKind.NO_FILE_HINT,
            issue_refs=no_hint,
            detail=("These do not say which part of the project they change, so I "
                    "cannot tell which group of work they belong to."),
        ))

    # Labels are deliberately not flagged. Nothing downstream groups by label — the
    # division reads file paths and the board's Lane field — so "these have no labels"
    # was a complaint about a clue nobody used, and on every real backlog it fired.

    for left, right, score in _duplicate_pairs(
            issues, thresholds.duplicate_title_score, thresholds.duplicate_report_limit):
        flags.append(QualityFlag(
            kind=FlagKind.POSSIBLE_DUPLICATE,
            issue_refs=(left.ref, right.ref),
            detail=(f"These two are worded almost identically ({score:.0%} the same), "
                    "so one of them may already be covered by the other."),
        ))

    broad = tuple(i.ref for i in issues
                  if len(_areas(i)) > thresholds.broad_ticket_areas)
    if broad:
        flags.append(QualityFlag(
            kind=FlagKind.BROAD_TICKET,
            issue_refs=broad,
            detail=(f"These each touch more than {thresholds.broad_ticket_areas} "
                    "different parts of the project, which usually means one ticket "
                    "is really several pieces of work."),
        ))

    return tuple(flags)


def flagged_refs(flags: Sequence[QualityFlag]) -> set:
    """Every ticket named by at least one flag, counted once."""
    refs: set = set()
    for flag in flags:
        refs.update(flag.issue_refs)
    return refs


def _file_hints(issue) -> List[str]:
    """The files and directories a ticket says it touches.

    Links are stripped first. A ticket whose only slash is inside a URL says nothing
    about which code it changes, and counting it would suppress the very flag that
    exists to catch that.
    """
    text = _URL.sub(" ", f"{issue.title}\n{issue.body}")
    hints = []
    for match in _PATH_HINT.findall(text):
        if "/" not in match and not _has_code_extension(match):
            continue
        hints.append(match)
    return hints


#: Product names that are spelled like a file and are not one. A closed, well-known set
#: — `Node.js` in a ticket body says what stack it is about, never which file it edits,
#: and counting it would suppress the flag that exists to catch exactly that ticket.
_PROSE_NAMES = {"node", "next", "nuxt", "vue", "react", "express", "socket", "d3"}


def _has_code_extension(candidate: str) -> bool:
    stem, _, extension = candidate.rpartition(".")
    if stem.lower() in _PROSE_NAMES:
        return False
    return extension.lower() in CODE_EXTENSIONS


def _areas(issue) -> set:
    """The distinct top-level parts of the project a ticket names."""
    areas = set()
    for hint in _file_hints(issue):
        head = hint.split("/")[0]
        if head and "." not in head:
            areas.add(head.lower())
    return areas


def _duplicate_pairs(issues: Sequence, threshold: float, limit: int):
    """Pairs of tickets whose titles are near-identical, worst first.

    Comparing every ticket with every other is quadratic, and on a large backlog of
    similarly-worded tickets both the character-level comparison and the resulting list
    of pairs grow past anything a person could read. Two guards: a cheap length check
    rejects most pairs before the expensive comparison runs, and only the closest
    `limit` pairs are reported — a report of a hundred thousand near-duplicates is not
    a report.
    """
    pairs = []
    normalised = [(i, _normalise(i.title)) for i in issues if _normalise(i.title)]
    for idx, (left, left_title) in enumerate(normalised):
        for right, right_title in normalised[idx + 1:]:
            # Two strings whose lengths differ by more than the threshold allows can
            # never reach it: the ratio is bounded by 2*min/(len+len).
            shorter, longer = sorted((len(left_title), len(right_title)))
            if 2 * shorter / (shorter + longer) < threshold:
                continue
            score = SequenceMatcher(None, left_title, right_title).ratio()
            if score >= threshold:
                pairs.append((left, right, score))
    pairs.sort(key=lambda p: p[2], reverse=True)
    return pairs[:limit] if limit > 0 else pairs


def _normalise(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (title or "").lower()))
