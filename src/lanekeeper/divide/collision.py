"""Do any two entries touch the same files?

This is the one thing in step 2 the user cannot see by eye and lanekeeper can answer
exactly. It is a set intersection over globs: no model, no judgement, the same answer
every time.

It answers only that question. Whether an overlap is a *dependency* that wants the two
entries fused, or a *collision* that wants a shared zone with a steward, is #39's, and
guessing at it here would put a judgement inside a check whose whole value is that it
makes none.
"""

from __future__ import annotations

import fnmatch
from functools import lru_cache
from typing import Dict, List, Sequence, Tuple

from ..lanes import LaneEngine
from .models import Overlap, ProposedLane


def report(lanes: Sequence[ProposedLane], files: Sequence[str], settings,
           shared_paths: Sequence[str] = ()) -> List[Overlap]:
    """Every pair of entries claiming the same files, worst first.

    Two kinds, kept apart because they are worth different amounts. A pair proved by
    files that exist is a fact about this repository. A pair that only overlaps in the
    shape of its patterns is a fact about what would happen when somebody adds a file —
    real, but weaker, and reported as such rather than rounded up.
    """
    limit = settings.thresholds.overlap_report_limit
    # A file inside a shared zone belongs to the zone, however specifically an entry
    # claims it. Two entries reaching into one is that zone working as documented, so
    # counting it as a collision would report the fix as the problem.
    listed = [f for f in files if not _claims(shared_paths, f)]
    matched: Dict[str, set] = {
        lane.name: {f for f in listed if _owns(lane, f)} for lane in lanes
    }

    found: List[Overlap] = []
    for index, left in enumerate(lanes):
        for right in lanes[index + 1:]:
            shared = sorted(matched[left.name] & matched[right.name])
            pairs = _overlapping_patterns(left.paths, right.paths)
            if not shared and pairs:
                # A carve-out or a shared zone can answer an overlap that no existing
                # file proves. Only the pairs it actually covers are dropped: blanking
                # every structural finding because a zone exists somewhere would let
                # one answered overlap hide all the unanswered ones.
                answered = tuple(left.deny) + tuple(right.deny) + tuple(shared_paths)
                pairs = tuple(pair for pair in pairs
                              if not _answered_by(pair, answered))
            if shared:
                found.append(Overlap(
                    left=left.name, right=right.name,
                    patterns=pairs, example_files=tuple(shared[:5]), kind="files"))
            elif pairs:
                found.append(Overlap(
                    left=left.name, right=right.name,
                    patterns=pairs, example_files=(), kind="patterns-only"))

    found.sort(key=lambda o: (o.kind != "files", -len(o.example_files), o.left, o.right))
    return found[:limit] if limit > 0 else found


def unclaimed(lanes: Sequence[ProposedLane], files: Sequence[str],
              limit: int) -> Tuple[str, ...]:
    """Files no entry claims — said out loud rather than left to be discovered later."""
    loose = [f for f in files if not any(_owns(lane, f) for lane in lanes)]
    return tuple(loose[:limit]) if limit > 0 else tuple(loose)


def _owns(lane: ProposedLane, path: str) -> bool:
    """Whether an entry claims a path, after its own carve-outs.

    `deny` beats `allow` within an entry — README, §The lane file, rule 3 — and it is
    how a user answers a reported overlap without moving a file.
    """
    return _claims(lane.paths, path) and not _claims(lane.deny, path)


def _claims(patterns: Sequence[str], path: str) -> bool:
    return any(LaneEngine.match_glob(path, pattern) for pattern in patterns)


def _answered_by(pair, answered: Sequence[str]) -> bool:
    """Whether a carve-out or a shared zone covers where two patterns meet.

    Approximate, and deliberately so: a pattern intersecting both sides covers the
    region they share in every case worth reporting, and the exact answer would need a
    language globs do not have. It only ever suppresses the weaker structural finding —
    an overlap proved by a file that exists is never dropped.
    """
    left, right = pair
    return any(patterns_intersect(cover, left) and patterns_intersect(cover, right)
               for cover in answered)


def _overlapping_patterns(left: Sequence[str], right: Sequence[str]):
    return tuple(
        (a, b) for a in left for b in right if patterns_intersect(a, b)
    )


def patterns_intersect(left: str, right: str) -> bool:
    """Whether any path at all could match both patterns.

    Needed because a collision over files that do not exist yet is still a collision:
    two entries both claiming `backend/app/domains/checkout/**` collide the moment
    anybody writes the first file there, and finding that out then rather than now is
    the failure this whole step exists to prevent.

    Compared segment by segment, with `**` standing for any run of segments.
    """
    return _walk(_segments(left), _segments(right))


def _segments(pattern: str) -> List[str]:
    cleaned = (pattern or "").replace("\\", "/").strip("/")
    return [s for s in cleaned.split("/") if s != ""]


def _walk(left: List[str], right: List[str]) -> bool:
    if not left and not right:
        return True
    if not left:
        return all(part == "**" for part in right)
    if not right:
        return all(part == "**" for part in left)

    head_left, head_right = left[0], right[0]
    if head_left == "**" or head_right == "**":
        wild, other = (left, right) if head_left == "**" else (right, left)
        # `**` consumes nothing, or one segment and stays.
        return _walk(wild[1:], other) or _walk(wild, other[1:])
    if not _segment_may_match(head_left, head_right):
        return False
    return _walk(left[1:], right[1:])


def _segment_may_match(left: str, right: str) -> bool:
    """Whether some string could satisfy both segment patterns.

    Walked character by character over both patterns at once, so two wildcard segments
    are actually compared rather than assumed to collide. `carrier_*.py` and
    `email_*.py` cannot both match one name — their literal prefixes disagree — and an
    earlier version said they did, which made the project's own worked example
    impossible to confirm. A character class is treated as `?`: it may match one
    character, and over-reporting a collision is the safe side of that guess.
    """
    return _common_string_exists(_class_to_question(left), _class_to_question(right))


def _class_to_question(segment: str) -> str:
    out, i = [], 0
    while i < len(segment):
        if segment[i] == "[":
            close = segment.find("]", i + 1)
            if close != -1:
                out.append("?")
                i = close + 1
                continue
        out.append(segment[i])
        i += 1
    return "".join(out)


@lru_cache(maxsize=4096)
def _common_string_exists(p: str, q: str) -> bool:
    """Whether the two `*`/`?`/literal patterns share at least one matching string."""
    if not p and not q:
        return True
    if not p:
        return all(ch == "*" for ch in q)
    if not q:
        return all(ch == "*" for ch in p)
    if p[0] == "*":
        # The star produces nothing, or absorbs whatever q produces next.
        return _common_string_exists(p[1:], q) or _common_string_exists(p, q[1:])
    if q[0] == "*":
        return _common_string_exists(p, q[1:]) or _common_string_exists(p[1:], q)
    if p[0] == "?" or q[0] == "?" or p[0] == q[0]:
        return _common_string_exists(p[1:], q[1:])
    return False
