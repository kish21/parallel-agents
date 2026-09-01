"""The draft: what lanekeeper proposes, in a file the user can argue with.

Step 2 proposes and the user confirms, so what it writes first must carry no authority.
The draft lives under lanekeeper's own directory, is written in the same schema as the
real lane file, and is the place where the user picks: keep an entry, merge two, rename
one, delete one, paste in the paths a ticket forgot to state.

Confirming re-reads **what the user actually wrote** and re-runs every mechanical check
on it before the real file is written. Checking the proposal and then writing the edit
would make the check theatre.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import yaml

from .. import paths as lk_paths
from .models import (
    DivisionProposal,
    DraftProblem,
    PathSource,
    Placement,
    ProposedLane,
    ValidationReport,
)
from . import collision

#: Bumped with the lane-file schema in README §The lane file.
SCHEMA_VERSION = 1


def draft_path(root: Path, settings) -> Path:
    return lk_paths.divide_draft_path(root, settings.draft_path)


def lane_file_path(root: Path, settings) -> Path:
    return Path(root) / settings.lane_file


# -- writing ---------------------------------------------------------------------


def render(proposal: DivisionProposal, settings) -> str:
    """The draft as text.

    Written by hand rather than dumped, because the comments are half the point: a
    ticket that could not be placed sits here as a commented-out entry, so keeping it is
    an edit rather than a retype.
    """
    lines: List[str] = [
        "# What I propose to give each agent.",
        "#",
        "# Nothing here is decided. Edit this file — join two entries, split one, rename",
        "# them, delete what you do not want, add the files an entry is missing — and",
        "# then run:",
        "#",
        "#     lanekeeper divide --confirm",
        "#",
        "# I will re-check what you wrote and only then write the real file.",
        "",
        f"version: {SCHEMA_VERSION}",
        "",
        "defaults:",
        "  harness: claude-code",
        "",
        "lanes:",
    ]

    if not proposal.lanes:
        lines.append("  # I could not propose anything. See the notes below.")

    wider = dict(proposal.wider_paths)
    for lane in proposal.lanes:
        lines += _lane_block(lane, wider.get(lane.name, ()))

    if proposal.needs_paths:
        lines += [
            "",
            "# ---------------------------------------------------------------------",
            "# These pieces of work do not say which files they change, so there is",
            "# nothing to hold anybody to. Below is my guess at where each one belongs,",
            "# switched off. Check the files are right, then remove the '# ' in front of",
            "# the lines to use it — or delete the block if the guess is wrong.",
            "# ---------------------------------------------------------------------",
        ]
        for boundary in proposal.needs_paths:
            if boundary.belongs_with:
                # Its files are already an entry's. A second entry over the same files
                # would clash by construction, so the action offered is the one that
                # actually works: put the number in that entry's list.
                lines += [
                    "",
                    f"# {boundary.title}  (#{boundary.ref})",
                    f"#   Looks like part of '{boundary.belongs_with}'. If it is, add",
                    f"#   '{boundary.ref}' to that entry's tickets above.",
                ]
                continue
            lines += _commented_block(
                name=boundary.ref,
                title=boundary.title,
                paths=boundary.paths,
                tickets=(boundary.ref,),
                note="I suggested these files; nobody has confirmed them.",
            )

    if proposal.unplaced:
        lines += [
            "",
            "# ---------------------------------------------------------------------",
            "# I have nothing to say about these. They name no files, and no part of",
            "# this project matches what they are called. Add the files each one",
            "# changes, here or on the ticket itself.",
            "# ---------------------------------------------------------------------",
        ]
        for boundary in proposal.unplaced:
            lines += _commented_block(
                name=boundary.ref,
                title=boundary.title,
                paths=(),
                tickets=(boundary.ref,),
                note="No files stated anywhere.",
            )

    return "\n".join(lines).rstrip() + "\n"


def save(proposal: DivisionProposal, root: Path, settings,
         overwrite: bool = False) -> Tuple[Path, bool]:
    """Writes the proposal, unless a draft is already there.

    The draft is the file the user edits, and `start` runs this step every time it is
    run. Overwriting would throw away the answer they came back to give. Returns the
    path and whether it was written.
    """
    path = draft_path(root, settings)
    if path.is_file() and not overwrite:
        return path, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(proposal, settings), encoding="utf-8")
    return path, True


def _lane_block(lane: ProposedLane, wider: Sequence[str] = ()) -> List[str]:
    tickets = ", ".join(f"#{ref}" for ref in lane.tickets)
    lines = [
        "",
        f"  {_key(lane.name)}:",
        f"    description: {_scalar(_description(lane))}",
        "    owner: unsure",
    ]
    if tickets:
        lines.append(f"    tickets: [{', '.join(_scalar(r) for r in lane.tickets)}]")
    lines.append("    allow:")
    lines += [f"      - {_scalar(path)}" for path in lane.paths] or ["      []"]
    if wider:
        # The tickets named files; this is the part of the project those files sit in.
        # Switched off, because the first new file written would otherwise fall outside
        # a boundary made of exactly the files that existed when it was written.
        lines.append("      # The tickets named single files. If this work will add")
        lines.append("      # new ones, these cover the whole area instead:")
        lines += [f"      # - {path}" for path in wider]
    return lines


def _commented_block(name: str, title: str, paths: Sequence[str],
                     tickets: Sequence[str], note: str) -> List[str]:
    """A block the user switches on by deleting the `# `, so it has to be valid YAML
    once they do. A ticket title containing a colon or a `#` is ordinary, and unquoted
    it would make the file unreadable at exactly the moment they followed instructions."""
    body = [
        "",
        f"# {title}  (#{name}) — {note}",
        f"#   work-{name}:",
        f"#     description: {_scalar(title)}",
        "#     owner: unsure",
        f"#     tickets: [{', '.join(_scalar(t) for t in tickets)}]",
        "#     allow:",
    ]
    body += ([f"#       - {_scalar(path)}" for path in paths]
             # No blank item: uncommented, it loads as an empty entry that looks like
             # a boundary and is not one. A line saying what to write is not a line
             # pretending to be a path.
             or ["#       # add the files this changes, one per line"])
    return body


def _description(lane: ProposedLane) -> str:
    tickets = ", ".join(f"#{ref}" for ref in lane.tickets)
    where = {
        PathSource.TICKET: "from what the tickets say they change",
        PathSource.CODE: "read from the files in this project",
        PathSource.PROPOSED: "suggested, not confirmed",
    }[lane.source]
    if tickets:
        return f"{tickets} — {where}."
    return f"{where.capitalize()}."


def _key(name: str) -> str:
    return name if name and name.replace("-", "").replace("_", "").isalnum() else _scalar(name)


def _scalar(value: str) -> str:
    """A YAML scalar that survives `*`, `#`, `:` and everything else in a glob.

    Dumped rather than quoted by hand: a lane file whose paths are written out with a
    home-made quoting rule stops loading the first time somebody uses a character
    nobody thought of.
    """
    dumped = yaml.safe_dump(str(value), default_flow_style=True).splitlines()
    body = [line for line in dumped if line.strip() not in ("...", "---")]
    return " ".join(part.strip() for part in body).strip()


# -- reading back what the user wrote ---------------------------------------------


def load(root: Path, settings):
    """The user's edited draft: its entries, the whole document, and any read error.

    The document is kept because `deny`, `shared`, `unowned`, `owner` and `harness` are
    all part of the documented schema and all things a user may have written by hand.
    Reading only the parts step 2 proposes and writing the file back from those would
    silently delete the rest — including the two documented ways to answer an overlap.
    """
    path = draft_path(root, settings)
    if not path.is_file():
        return [], {}, DraftProblem(
            kind="unreadable", subject=str(path),
            detail=("There is no proposal to confirm yet. Run 'lanekeeper divide' "
                    "first and I will write one for you to look over."))
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return [], {}, DraftProblem(
            kind="unreadable", subject=str(path),
            detail=f"I could not read {path}: {exc}")

    raw_lanes = data.get("lanes") or {}
    if not isinstance(raw_lanes, dict):
        return [], {}, DraftProblem(
            kind="unreadable", subject=str(path),
            detail="The list of groups in that file is not in the shape I wrote it.")

    lanes: List[ProposedLane] = []
    for name, body in raw_lanes.items():
        body = body or {}
        allow = body.get("allow") or []
        deny = body.get("deny") or []
        tickets = body.get("tickets") or []
        lanes.append(ProposedLane(
            name=str(name),
            paths=_paths_of(allow),
            deny=_paths_of(deny),
            tickets=tuple(str(t) for t in tickets if t is not None),
            source=PathSource.TICKET,
            placement=Placement.GROUPED if len(tickets) > 1 else Placement.SINGLE_TICKET,
            why=str(body.get("description") or ""),
        ))
    return lanes, data, None


def shared_paths(document: dict) -> Tuple[str, ...]:
    """Every path covered by a shared zone the user declared."""
    zones = (document or {}).get("shared") or {}
    if not isinstance(zones, dict):
        return ()
    return tuple(str(p) for zone in zones.values()
                 for p in ((zone or {}).get("paths") or []) if str(p).strip())


def _paths_of(items) -> Tuple[str, ...]:
    """Written paths, with the empty ones dropped.

    A blank list entry loads as `None`, and `str(None)` is the perfectly plausible-
    looking path `"None"` — which would satisfy the check that an entry has a boundary
    while giving it one that matches nothing. An entry left half-filled has to read as
    empty, because that is what it is.
    """
    return tuple(str(item).strip() for item in items
                 if item is not None and str(item).strip())


def validate(lanes: Sequence[ProposedLane], files: Sequence[str], settings,
             document: dict = None) -> ValidationReport:
    """Every mechanical check, run on what the user wrote rather than on the proposal."""
    problems: List[DraftProblem] = []

    if not lanes:
        problems.append(DraftProblem(
            kind="no-lanes", subject="",
            detail=("That file does not describe any groups of work, so there is "
                    "nothing for me to write down.")))

    for lane in lanes:
        if not lane.paths:
            # No files means no boundary, and no boundary means nothing to hold the
            # agent to. Writing this would ship a promise that does not exist.
            problems.append(DraftProblem(
                kind="no-paths", subject=lane.name,
                detail=(f"'{lane.name}' does not say which files it covers, so I would "
                        "have no way to tell whether work on it stayed where it should.")))

    seen: Dict[str, str] = {}
    for lane in lanes:
        for ref in lane.tickets:
            if ref in seen and seen[ref] != lane.name:
                problems.append(DraftProblem(
                    kind="duplicate-ticket", subject=ref,
                    detail=(f"#{ref} is listed under both '{seen[ref]}' and "
                            f"'{lane.name}'. Two people would both think it was theirs.")))
            seen.setdefault(ref, lane.name)

    zones = shared_paths(document)
    overlaps = collision.report(lanes, files, settings, shared_paths=zones)
    return ValidationReport(lanes=tuple(lanes), problems=tuple(problems),
                            overlaps=tuple(overlaps), shared_paths=zones)


def write_lane_file(document: dict, root: Path, settings,
                    overwrite: bool = False) -> Tuple[Path, bool]:
    """The confirmed division, written from the user's own document.

    Written from what they wrote, not re-rendered from the entries step 2 understood:
    `deny`, `shared`, `unowned`, `owner` and `harness` are all part of the documented
    schema in README, §The lane file, and re-rendering would drop every one of them
    they had filled in — including the two documented ways to answer an overlap.

    The one key removed is `tickets`, which is the draft's own bookkeeping and not part
    of that schema. An existing file is never overwritten without being asked: it may
    have been written by hand, and this command did not write it.
    """
    path = lane_file_path(root, settings)
    if path.exists() and not overwrite:
        return path, False

    out = {key: value for key, value in (document or {}).items() if key != "lanes"}
    out.setdefault("version", SCHEMA_VERSION)
    lanes = {}
    for name, body in ((document or {}).get("lanes") or {}).items():
        lanes[name] = {k: v for k, v in (body or {}).items() if k != "tickets"}
    out["lanes"] = lanes

    header = "\n".join([
        "# Who owns what. Written by 'lanekeeper divide --confirm' from the proposal",
        "# you confirmed. Hand-editing this file is expected; it is the authority.",
        "",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + yaml.safe_dump(out, sort_keys=False,
                                            default_flow_style=False, allow_unicode=True),
                    encoding="utf-8")
    return path, True
