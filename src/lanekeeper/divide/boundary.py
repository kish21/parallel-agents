"""What a ticket says about the files it touches.

The ticket form asks for Allowed File Paths and makes it the required field, so a
properly filed ticket carries its own boundary and nothing has to be inferred. This
module reads that field and nothing else.

**Only that section.** `intake.quality` scans a whole ticket body for anything
path-shaped, which is right for its question ("is there a clue here at all?") and wrong
for this one: a stack trace pasted into an Evidence field would otherwise become a
boundary the merge gate enforces. "The filer stated where this work belongs" and "the
body happens to contain a path" are different claims, and only the first one may be
handed to an agent.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

from .models import PathSource, TicketBoundary

#: A markdown heading, in either of the shapes GitHub renders a form field as: an ATX
#: heading (`### Allowed File Paths`) or a bolded label on its own line.
_HEADING = re.compile(r"^\s{0,3}(?:(#{1,6})\s*(.+?)\s*#*|\*\*(.+?)\*\*:?)\s*$")

#: What GitHub writes into a section the filer left empty.
_EMPTY_MARKERS = {"_no response_", "no response", "n/a", "none", "-", "tbd"}

#: Decoration around a path in a list: a bullet, a checkbox, backticks, a trailing
#: comma. Stripped rather than rejected — a filer who writes a tidy list is not making
#: a mistake.
#:
#: A bullet only counts as one when whitespace follows it. `*` and `+` are also the
#: first character of perfectly good patterns — `**/checkout/**`, `*.py`,
#: `+page.svelte` — and stripping one turns a boundary into a different, wrong boundary
#: that the merge gate would then enforce.
_DECORATION = re.compile(r"^[-*+•]\s+|^\[[ xX]\]\s*|[`'\",;]+")

#: A line that is prose, not a path. Paths do not contain spaces often enough to be
#: worth guessing about, and a sentence in the box is a comment on the boundary rather
#: than part of it.
_MAX_WORDS = 1


def read(issue, settings) -> TicketBoundary:
    """One ticket's stated boundary, exactly as the filer wrote it."""
    body = issue.body or ""
    paths, ignored = _paths(_section(body, settings.path_headings))
    lane = _lane_name(_section(body, settings.lane_headings))
    return TicketBoundary(
        ref=str(issue.ref),
        title=issue.title or "",
        paths=tuple(paths),
        declared_lane=lane,
        source=PathSource.TICKET,
        url=getattr(issue, "url", "") or "",
        ignored_lines=tuple(ignored),
    )


def read_all(issues: Sequence, settings) -> List[TicketBoundary]:
    return [read(issue, settings) for issue in issues]


def normalise(raw: str) -> Optional[str]:
    """One written path, in the form the lane engine matches against.

    Windows separators, a leading `./` or `/`, and surrounding decoration are all ways
    of writing the same path, and a boundary that depends on which one the filer chose
    is not a boundary.
    """
    text = _DECORATION.sub("", (raw or "").strip()).strip()
    text = text.replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    text = text.lstrip("/")
    if not text or text.lower() in _EMPTY_MARKERS:
        return None
    if len(text.split()) > _MAX_WORDS:
        return None
    if text.endswith("/"):
        # A directory is everything under it. Saying so here means the rest of the
        # system only ever sees globs, and the filer never has to know that.
        text = text + "**"
    return text


# -- reading one section out of an issue body ------------------------------------


def _section(body: str, headings: Sequence[str]) -> List[str]:
    """The lines under the first heading matching one of `headings`.

    A section ends at the next heading of any level, which is how GitHub renders the
    next field of the form. Anything before the first heading belongs to no field.
    """
    wanted = tuple(h.strip().lower() for h in headings if h.strip())
    if not wanted:
        return []

    collecting = False
    collected: List[str] = []
    for line in body.splitlines():
        title = _heading_title(line)
        if title is not None:
            if collecting:
                break
            collecting = any(title.startswith(name) for name in wanted)
            continue
        if collecting:
            collected.append(line)
    return collected


def _heading_title(line: str):
    """The text of a heading, or None when the line is not one.

    The bolded-label form has to be told apart from a path: `**/checkout/**` is a
    perfectly ordinary pattern and reads as `**…**` to a regex. Treating it as a heading
    ended the section it was written in, and the boundary came back empty — the ticket
    stated where the work belonged and lanekeeper said it had not.
    """
    match = _HEADING.match(line)
    if not match:
        return None
    if match.group(1):                       # an ATX heading: unambiguous
        return (match.group(2) or "").strip().lower()
    label = (match.group(3) or "").strip()
    if not label or "/" in label or "*" in label or len(label.split()) > 8:
        return None                          # a path in bold is still a path
    return label.lower()


def _paths(lines: Sequence[str]):
    """Every path in a section, de-duplicated, and every line that was not one.

    Fenced code blocks are unwrapped rather than skipped: a filer who pastes their
    paths inside a fence has still stated them.

    The second list exists because a sentence in the box is usually a comment on the
    boundary — but not always, and a line dropped in silence is a boundary narrower
    than the one the filer wrote, with nobody told. They are handed back to be shown.
    """
    seen = set()
    out: List[str] = []
    ignored: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("```") or stripped.startswith("~~~"):
            continue
        path = normalise(stripped)
        if path is None:
            ignored.append(stripped)
            continue
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out, ignored


def _lane_name(lines: Sequence[str]) -> str:
    """The feature name the filer gave, or nothing.

    Nothing is the expected answer and never a defect: the form says to leave it blank
    when unsure, because the backlog read as a whole is a better guess than one ticket
    can make.
    """
    for line in lines:
        text = _DECORATION.sub("", line.strip()).strip()
        if not text or text.lower() in _EMPTY_MARKERS:
            continue
        return text
    return ""
