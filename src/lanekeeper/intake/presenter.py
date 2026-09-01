"""Everything step 1 says to the user, in one place.

Two reasons it is one module. First, a person running `lanekeeper start` has a project
and wants several agents working on it; they should not have to know what a lane, a
worktree or a seat is to get through the first question. Second, a rule about wording
that lives only in a style guide is not enforced — with every string here, a test can
assert the rule instead, which is what `BANNED_WORDS` and `test_intake_language.py` do.

This module also never suggests moving a file or reorganising a folder. How the work
divides is settled later, over the project as it actually stands.
"""

from __future__ import annotations

import textwrap
from typing import List

from .models import CoverageVerdict, FlagKind, IntakeResult, SpecSource, Verdict

#: Vocabulary this step must not need. These are lanekeeper's own concepts, and step 1
#: happens before the user has any reason to have met them.
BANNED_WORDS = ("lane", "lanes", "worktree", "worktrees", "seat", "seats",
                "glob", "globs", "branch", "merge base")

PLAYBOOK_STEPS = ("/vision", "/scope", "/plan")


def render(result: IntakeResult, has_issue_template: bool = False,
           dividing_next: bool = True) -> str:
    """The whole of step 1's output for one run.

    `has_issue_template` is passed in rather than looked up: this module reads nothing
    from disk, so every string it produces is reproducible from its arguments alone.
    """
    if result.resumed:
        return _resumed(result)
    if not result.tracker_available:
        return _unreadable(result)
    if result.issue_count == 0:
        return _nothing_written_down(result)

    lines: List[str] = [_headline(result), ""]
    lines += _coverage_lines(result)
    if result.stop_reasons:
        lines.append("")
        lines += [f"   {reason}" for reason in result.stop_reasons]
    flag_lines = _flag_lines(result)
    if flag_lines:
        lines += [""] + flag_lines
    lines += [""] + _next_lines(result, has_issue_template, dividing_next)
    return "\n".join(lines).rstrip() + "\n"


# -- the whole-output cases ------------------------------------------------------


def _resumed(result: IntakeResult) -> str:
    """What a resumed run says — which must be what the recorded run actually found.

    A record that passed only because the user said to take it as read did not conclude
    that the work covers the product, and repeating it back as though it had would be
    exactly the dressed-up verdict this step exists to refuse.
    """
    if result.accepted_as_is or result.coverage.verdict is CoverageVerdict.CANNOT_JUDGE:
        finding = "and you have already told me it is the whole job"
    else:
        finding = "and it still covers what this project set out to do"
    return (
        "✅ Step 1 was already done and nothing has changed since — "
        f"{_count(result.issue_count)}, {finding}.\n"
        "   Carrying on from where the last run stopped.\n"
    )


def _unreadable(result: IntakeResult) -> str:
    return (
        "🛑 I could not read this project's list of work.\n\n"
        f"   {result.tracker_note}\n\n"
        "   Until I can read it, I cannot tell what there is to share out, so I have\n"
        "   stopped here and changed nothing.\n"
    )


def _nothing_written_down(result: IntakeResult) -> str:
    """No work to share out — either none was written, or this project has no tracker.

    Both land here on purpose. A repository that has never been pushed anywhere has no
    list of work for the same reason a brand-new one does: nobody has written it yet.
    The note says which of the two it was, and the advice is the same either way.
    """
    steps = "  then  ".join(PLAYBOOK_STEPS)
    opening = (
        f"🛑 {result.tracker_note}\n\n" if result.tracker_note else
        "🛑 There is no written-down work in this project yet, so there is nothing\n"
        "   to share out between agents.\n\n"
    )
    return (
        opening
        + "   That is the normal starting point, and it is not my job to invent what\n"
        "   your product should do. Its companion tool, product-playbook, is built\n"
        "   for exactly this: it works out what you are building, what the first\n"
        "   version includes, and turns that into a list of tickets.\n\n"
        f"   Run:  {steps}\n\n"
        "   When that has produced your list of work, run 'lanekeeper start' again\n"
        "   and I will carry on from here.\n\n"
        "   I have changed nothing in this project.\n"
    )


# -- the parts of a normal report ------------------------------------------------


def _headline(result: IntakeResult) -> str:
    if result.accepted_as_is:
        return (f"✅ Taking {_count(result.issue_count)} as the whole job, "
                "because you said so.")
    if result.verdict is Verdict.READY:
        return f"✅ The work is written down: {_count(result.issue_count)}."
    return f"📋 I found {_count(result.issue_count)} written down."


def _coverage_lines(result: IntakeResult) -> List[str]:
    cov = result.coverage
    if cov.verdict is CoverageVerdict.CANNOT_JUDGE:
        lines = [
            f"   I count {_count(result.issue_count)} and I cannot tell whether that is",
            "   all of them, because I have nothing to compare them against that says",
            "   what this product is meant to do. I am not going to guess.",
        ]
        lines += _where_i_looked(result)
        if result.label_counts:
            shown = ", ".join(f"{name} ({n})" for name, n in result.label_counts[:6])
            lines.append(f"   How they are labelled: {shown}")
        else:
            lines.append("   None of them carry a label.")
        return lines

    where = _describe_source(cov.source, cov.source_path)
    if cov.verdict is CoverageVerdict.COVERED:
        return [
            f"   I compared them against {where}, and every thing that document says",
            "   this product does has something written against it.",
        ]

    lines = [
        f"   I compared them against {where}. These appear to have nothing written",
        "   against them:",
        "",
    ]
    lines += [f"     • {feature.name}" for feature in cov.uncovered]
    return lines


def _where_i_looked(result: IntakeResult) -> List[str]:
    """Which documents were opened and found wanting.

    "I have nothing to compare against" and "I read your README and it does not list
    what this product does" are different sentences, and only the second one tells the
    user what would fix it. Saying the first while having done the second is the kind of
    quietly-wrong report this whole step exists to avoid.
    """
    if not result.spec_considered:
        return []
    read = ", ".join(result.spec_considered)
    return [
        f"   I read {read}, and could not find a list in there of what this",
        "   product does — a section headed Scope, Plan or Features is what I look for.",
    ]


def _describe_source(source: SpecSource, path) -> str:
    if source is SpecSource.PRODUCT_MD:
        return f"the plan in {path}"
    return f"the description of this product in {path}"


def _flag_lines(result: IntakeResult) -> List[str]:
    """The tickets that would make grouping a guess, one sentence per problem.

    Near-duplicates arrive as one flag per pair, because that is the honest shape of the
    finding — but printing the same sentence once per pair turns a dozen similar tickets
    into a wall of identical text. They are collapsed into one entry listing the pairs.
    """
    if not result.flags:
        return []

    lines = ["   Some of the tickets will be hard for me to sort into groups:"]
    pairs = [f for f in result.flags if f.kind is FlagKind.POSSIBLE_DUPLICATE]
    for flag in result.flags:
        if flag.kind is FlagKind.POSSIBLE_DUPLICATE:
            continue
        lines += _wrapped(flag.detail)
        lines.append(f"       {_refs(flag.issue_refs)}")
    if pairs:
        lines += _wrapped("Some are worded almost identically, so one of each pair may "
                          "already be covered by the other.")
        listed = ", ".join(f"#{f.issue_refs[0]} and #{f.issue_refs[1]}" for f in pairs)
        lines += [f"       {line}" for line in textwrap.wrap(listed, width=70)]
    lines.append("")
    lines.append("   I have not changed any of them — they are yours to edit.")
    return lines


def _wrapped(detail: str) -> List[str]:
    """One bullet, wrapped so it stays readable in a terminal."""
    wrapped = textwrap.wrap(detail, width=72)
    return [f"     • {wrapped[0]}"] + [f"       {line}" for line in wrapped[1:]]


def _refs(refs, limit: int = 8) -> str:
    shown = ", ".join(f"#{ref}" for ref in refs[:limit])
    return shown if len(refs) <= limit else f"{shown} (and {len(refs) - limit} more)"


def _next_lines(result: IntakeResult, has_issue_template: bool = False,
                dividing_next: bool = True) -> List[str]:
    if result.verdict is Verdict.READY:
        # This same report is printed by the check run on its own, which stops here.
        # Saying "next I will…" when nothing follows is a small lie about what the
        # command just did.
        if dividing_next:
            return [
                "   Next: I will work out how this splits into groups, so each agent",
                "   gets one of them.",
            ]
        return [
            "   Working out how this splits into groups is the next step, and",
            "   'lanekeeper divide' is the command that does it.",
        ]

    if result.coverage.verdict is CoverageVerdict.GAPS:
        steps = "  then  ".join(PLAYBOOK_STEPS)
        return [
            "   Work that is not written down cannot be shared out. product-playbook",
            "   is the tool that turns a gap like this into tickets:",
            "",
            f"     {steps}",
            "",
            "   Then run 'lanekeeper start' again and I will pick up from here.",
            "   I have changed nothing in this project.",
        ]

    lines = [
        "   You know this project and I do not, so this is your call. If work is",
        "   missing, product-playbook (" + ", ".join(PLAYBOOK_STEPS) + ") is what",
        "   writes it down. If what is here is the whole job, tell me so and I will",
        "   take it as read:",
        "",
        "     lanekeeper start --take-as-is",
    ]
    if has_issue_template and _template_hint(result):
        lines.append("   This project already has a ticket template — filling in the same")
        lines.append("   fields on the tickets above is what would make them clear to me.")
    lines.append("   I have changed nothing in this project.")
    return lines


def _template_hint(result: IntakeResult) -> bool:
    return any(f.kind in (FlagKind.NO_FILE_HINT, FlagKind.NO_LABELS) for f in result.flags)


def _count(n: int) -> str:
    return "1 piece of work" if n == 1 else f"{n} pieces of work"
