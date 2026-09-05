"""The lanes, written out as the file GitHub already enforces.

`CODEOWNERS` and the lane file hold the same information — which paths belong to
whom — so emitting one from the other is close to free, and it makes the lanes
readable by people and tools that have never heard of lanekeeper. Once "require
review from Code Owners" is on, GitHub routes every pull request by the same
boundaries the gate checks. Issue #42.

The two are **not** substitutes, and the generated header says so. `CODEOWNERS`
answers *who must approve this file* — a routing decision made after the work is
done, actionable only by a person. The gate answers *should this branch have touched
this file at all* — a boundary decided before the work starts, and a failing check is
feedback the agent itself can read.

Three things about `CODEOWNERS` decide the shape of everything below:

1. **The last matching pattern wins**, which is the opposite of most glob systems and
   the opposite of this tool's own engine, where `deny` beats `allow` and a shared zone
   beats both. So the emission order is inverted on purpose: ordinary lanes first,
   then the shared zones, then the policy files last of all.
2. **There is no way to say "not this path".** A lane's `deny` list has no
   representation, so it is reported rather than approximated.
3. **Over 3 MB the feature silently stops working**, taking the routing with it and
   saying nothing. That is worth refusing to cause.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from . import paths
from .config import Config, LaneConfig

#: Where GitHub looks. `.github/` is the conventional one of the three locations.
DEFAULT_PATH = ".github/CODEOWNERS"

BEGIN = "# --- lanekeeper (managed) — do not edit between these markers ---"
END = "# --- end lanekeeper ---"

#: GitHub stops loading a CODEOWNERS file above this size, without saying so.
MAX_BYTES = 3 * 1024 * 1024

#: Characters `CODEOWNERS` does not support, with the reason to print for each.
UNSUPPORTED = {
    "?": "'?' is not supported in CODEOWNERS patterns",
    "[": "character ranges ('[...]') are not supported in CODEOWNERS patterns",
    "]": "character ranges ('[...]') are not supported in CODEOWNERS patterns",
}


class MalformedBlock(ValueError):
    """Raised when the markers in an existing file are not a block.

    Never repaired silently. The text between a stray marker and the real block is
    somebody's routing, and quietly deleting it — or writing a second block below a
    broken one — is worse than stopping and saying which line is wrong.
    """


class UntranslatablePattern(ValueError):
    """Raised for a lane pattern CODEOWNERS cannot express.

    Carries the pattern and the reason separately so the caller can put the pattern in
    the file as a comment and the reason in front of the person running the command.
    """

    def __init__(self, pattern: str, reason: str):
        super().__init__(f"{pattern}: {reason}")
        self.pattern = pattern
        self.reason = reason


def translate(pattern: str) -> str:
    """A lane glob as a CODEOWNERS pattern.

    Anchored with a leading `/` wherever it can be, which is the whole of the
    translation: lane patterns are matched against a path from the repository root,
    while an unanchored CODEOWNERS pattern matches at *every* level. `src/*.ts` in a
    lane means the two files in `src/`; written unanchored into CODEOWNERS it would
    also claim `vendor/other/src/x.ts` and route somebody else's review to this lane.
    """
    norm = pattern.replace("\\", "/").strip()
    if not norm:
        raise UntranslatablePattern(pattern, "empty pattern")
    if norm.startswith("!"):
        raise UntranslatablePattern(
            pattern, "negation ('!') is not supported in CODEOWNERS patterns")
    for char, reason in UNSUPPORTED.items():
        if char in norm:
            raise UntranslatablePattern(pattern, reason)
    if any(c.isspace() for c in norm):
        # CODEOWNERS splits each line on whitespace: the first field is the pattern and
        # the rest are owners. `My Docs/**  @a` is read as the pattern `/My` owned by
        # `Docs/**` and `@a`, which is a rule about a path that does not exist and an
        # owner who is not a person. There is no escape for it.
        raise UntranslatablePattern(
            pattern, "a space in the path cannot be written in CODEOWNERS, which "
                     "splits every line on whitespace")
    if norm.startswith("/") or norm.startswith("**/"):
        # Already anchored, or deliberately unanchored — `**/` means "at any level" in
        # both systems, so re-anchoring it would change what the lane said.
        return norm
    return "/" + norm


@dataclass
class Rule:
    """One lane's worth of ownership, ready to write."""

    lane: str
    owners: Tuple[str, ...]
    patterns: Tuple[str, ...] = ()
    #: Patterns that could not be translated, with the reason for each.
    skipped: Tuple[Tuple[str, str], ...] = ()
    #: A `deny` list has no representation in CODEOWNERS; carried so it can be said.
    unexpressible_deny: Tuple[str, ...] = ()
    note: str = ""


@dataclass
class Plan:
    """Everything the command would write, and everything it has to say about it."""

    rules: List[Rule] = field(default_factory=list)
    #: True when no owner could be found for the policy files, so nothing routes them
    #: and an ordinary lane's pattern may end up owning the lane file itself.
    policy_unowned: bool = False
    #: Lanes nobody owns. They get no rule at all: an owner-less line is a syntax
    #: error in CODEOWNERS, and inventing an owner would route reviews to somebody who
    #: never agreed to them.
    unowned_lanes: List[str] = field(default_factory=list)

    @property
    def has_rules(self) -> bool:
        return any(r.patterns for r in self.rules)

    @property
    def skipped_count(self) -> int:
        return sum(len(r.skipped) for r in self.rules)


def _owners_for(lane: LaneConfig, default: Sequence[str]) -> Tuple[str, ...]:
    return tuple(lane.owner) if lane.owner else tuple(default)


def _rule_for(lane: LaneConfig, owners: Sequence[str], note: str = "") -> Rule:
    good: List[str] = []
    skipped: List[Tuple[str, str]] = []
    for pattern in lane.allow:
        try:
            good.append(translate(pattern))
        except UntranslatablePattern as exc:
            skipped.append((exc.pattern, exc.reason))
    return Rule(
        lane=lane.name,
        owners=tuple(owners),
        patterns=tuple(good),
        skipped=tuple(skipped),
        unexpressible_deny=tuple(lane.deny),
        note=note,
    )


def build_plan(config: Config, default_owner: Sequence[str] = (),
               policy_owner: Sequence[str] = ()) -> Plan:
    """The rules, in the order CODEOWNERS has to read them.

    Ordinary lanes, then shared zones, then the policy files — later wins there, so
    this is the tool's own precedence written backwards. Get it the other way round and
    a feature lane whose `allow` happens to cover the shared store silently takes the
    shared zone's ownership, which is the exact failure the zone exists to prevent.
    """
    plan = Plan()
    ordinary = [l for l in config.lanes.values() if not l.shared]
    shared = [l for l in config.lanes.values() if l.shared]

    for lane in ordinary + shared:
        owners = _owners_for(lane, default_owner)
        if not owners:
            plan.unowned_lanes.append(lane.name)
            continue
        note = ("shared code — no single owner; this routes the decision to the "
                "steward") if lane.shared else ""
        plan.rules.append(_rule_for(lane, owners, note))

    owners_for_policy = tuple(policy_owner) or tuple(default_owner)
    if owners_for_policy:
        # The policy last, so it beats every lane above it. It is the one thing no lane
        # may change, and a review of a change to it is a review of the boundaries
        # themselves. Without this rule an ordinary lane's pattern — `**/*.yaml` is
        # enough — becomes the code owner of the file that defines every lane, which is
        # the one capture this file must not enable.
        policy = LaneConfig(
            name="policy",
            allow=[p + "**" if p.endswith("/") else p for p in paths.policy_paths()]
            + [config.codeowners.path],
        )
        plan.rules.append(
            _rule_for(policy, owners_for_policy,
                      "the lane policy itself, and this file. A change here changes "
                      "who may touch what."))
    else:
        plan.policy_unowned = True
    return plan


def render_block(plan: Plan, source: str) -> str:
    """The managed block, markers included."""
    lines = [
        BEGIN,
        f"# Generated by 'lanekeeper codeowners' from {source} — do not edit by hand.",
        "# CODEOWNERS answers who must approve a file. The lane gate answers whether a",
        "# branch should have touched it at all. Both, not either.",
        "# The LAST matching pattern wins here, so the order below is deliberate:",
        "# feature lanes first, shared zones next, the policy last.",
    ]
    for rule in plan.rules:
        lines.append("")
        header = f"# lane: {rule.lane}"
        if rule.note:
            header += f" — {rule.note}"
        lines.append(header)
        owners = " ".join(rule.owners)
        width = max((len(p) for p in rule.patterns), default=0)
        for pattern in rule.patterns:
            lines.append(f"{pattern.ljust(width)}  {owners}")
        for pattern, reason in rule.skipped:
            lines.append(f"#   not written: {pattern} — {reason}")
        if rule.unexpressible_deny:
            lines.append(f"#   this lane denies {', '.join(rule.unexpressible_deny)}; "
                         f"CODEOWNERS cannot express a carve-out, so the paths above "
                         f"include them")
    lines.append(END)
    return "\n".join(lines) + "\n"


def merge(existing: str, block: str) -> str:
    """The file with the managed block replaced, or added if it was not there.

    Everything outside the markers is somebody's hand-written routing and survives
    untouched — the same contract as the managed `.gitignore` block.
    """
    has_begin, has_end = BEGIN in existing, END in existing
    if has_begin or has_end:
        if not (has_begin and has_end):
            raise MalformedBlock(
                f"the file has {'a start' if has_begin else 'an end'} marker "
                f"({BEGIN if has_begin else END}) without the other one")
        head, rest = existing.split(BEGIN, 1)
        if END not in rest:
            # END came *before* BEGIN. Splitting on it anyway would swallow everything
            # between them, which is exactly the text that is not ours.
            raise MalformedBlock(
                "the end marker comes before the start marker, so what lies between "
                "them cannot be identified as ours")
        _, tail = rest.split(END, 1)
        return head + block.rstrip("\n") + tail
    if not existing.strip():
        return block
    prefix = "" if existing.endswith("\n") else "\n"
    return existing + prefix + "\n" + block


def rules_after_block(text: str) -> List[str]:
    """Hand-written rules that come *after* the managed block.

    Last match wins, so a rule below the block overrides the lanes for any path it
    matches — including, if it is broad enough, the policy files. That is a legitimate
    thing to want and an easy thing to do by accident, so it is said out loud rather
    than left to be discovered when a review routes to the wrong person.
    """
    if END not in text:
        return []
    tail = text.split(END, 1)[1]
    return [line.strip() for line in tail.splitlines()
            if line.strip() and not line.strip().startswith("#")]


def target_path(config: Config, root: Path) -> Path:
    return root / config.codeowners.path


def desired_text(config: Config, root: Path, default_owner: Sequence[str] = (),
                 source: str = "", policy_owner: Sequence[str] = ()) -> Tuple[str, Plan]:
    """The whole file as it should be, plus the plan that produced it."""
    plan = build_plan(config, default_owner, policy_owner)
    block = render_block(plan, source or paths.display_config_path(root))
    target = target_path(config, root)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    return merge(existing, block), plan


def too_big(text: str) -> Optional[int]:
    """The size in bytes when it is over GitHub's limit, else None."""
    size = len(text.encode("utf-8"))
    return size if size > MAX_BYTES else None


def crowded(text: str) -> Optional[int]:
    """The size when it is within 10% of the limit — worth saying before it breaks."""
    size = len(text.encode("utf-8"))
    return size if MAX_BYTES * 0.9 <= size <= MAX_BYTES else None


def write(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
