"""The gate: may the rest of `lanekeeper start` run?

Everything downstream — modules, lanes, seats, worktrees, the merge gate — is derived
from the written-down work. If that work is missing or thin, dividing it produces a
confident-looking split of nothing, so this runs first and can stop the command.

It decides; it does not print, and it does not shell out. It is handed a tracker and a
configuration and returns a value. That is what makes every case below testable without
a network, a GitHub account, or a repository that happens to be in the right state.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import List, Optional, Sequence

from ..trackers.base import IssueTracker, TrackerError, TrackerNotConnectedError
from . import coverage as coverage_module
from . import quality, record
from .models import (
    CoverageReport,
    CoverageVerdict,
    IntakeResult,
    ProductSpec,
    SpecSource,
    Verdict,
)
from .spec import resolve_spec


def run_intake(
    root: Path,
    settings,
    tracker: IssueTracker,
    use_record: bool = True,
    accept_as_is: bool = False,
) -> IntakeResult:
    """Runs step 1, reusing a previous passing result when nothing has changed.

    `accept_as_is` is the user answering the one question this step cannot answer for
    them: whether a backlog it could not judge is nevertheless the whole job. It turns
    a stop-and-ask into a pass, and never overrides a coverage gap or an unreadable
    tracker, because neither of those is the user's opinion to give.
    """
    availability = tracker.is_available()
    if not availability.available:
        # Unreadable is not the same as empty. Saying "you have written nothing down"
        # to someone whose backlog simply could not be reached would send them to
        # rewrite work they already have.
        return IntakeResult(
            verdict=Verdict.NEEDS_TIDYING,
            issue_count=0,
            coverage=CoverageReport(verdict=CoverageVerdict.CANNOT_JUDGE),
            tracker_name=tracker.name,
            tracker_available=False,
            tracker_note=availability.reason,
        )

    try:
        issues = list(tracker.list_issues())
    except TrackerNotConnectedError as exc:
        # Not connected is not a failure. A repository that has never been pushed is the
        # ordinary first day of a project: there is no list of work because nobody has
        # written one yet, and the answer is the playbook, not an error.
        return IntakeResult(
            verdict=Verdict.NEEDS_PLAYBOOK,
            issue_count=0,
            coverage=CoverageReport(verdict=CoverageVerdict.CANNOT_JUDGE),
            tracker_name=tracker.name,
            tracker_note=str(exc),
        )
    except TrackerError as exc:
        return IntakeResult(
            verdict=Verdict.NEEDS_TIDYING,
            issue_count=0,
            coverage=CoverageReport(verdict=CoverageVerdict.CANNOT_JUDGE),
            tracker_name=tracker.name,
            tracker_available=False,
            tracker_note=str(exc),
        )

    spec = resolve_spec(root, settings)
    stamp = record.fingerprint(tracker.name, issues, spec, settings.thresholds)

    if use_record:
        previous = record.load(root)
        if previous is not None and previous.passed and previous.fingerprint == stamp:
            # The tickets come from this run, not from the record. A resumed result
            # is a resumed *judgement*; the work itself is whatever the tracker says
            # today, and step 2 divides that.
            return IntakeResult(**{**previous.__dict__, "resumed": True,
                                   "issues": tuple(issues)})

    result = _judge(issues, spec, settings.thresholds, tracker.name, stamp)
    if accept_as_is and result.verdict is Verdict.NEEDS_TIDYING:
        result = IntakeResult(**{**result.__dict__,
                                 "verdict": Verdict.READY,
                                 "accepted_as_is": True})
    if result.passed:
        record.save(result, root)
    # Attached after recording, never before: the record is a judgement about the work,
    # not a copy of it.
    return IntakeResult(**{**result.__dict__, "issues": tuple(issues)})


def _judge(issues: Sequence, spec: ProductSpec, thresholds, tracker_name: str,
           stamp: str) -> IntakeResult:
    if not issues:
        # The one case with a single right answer: there is nothing to divide, and
        # lanekeeper does not invent the work. product-playbook writes it.
        return IntakeResult(
            verdict=Verdict.NEEDS_PLAYBOOK,
            issue_count=0,
            coverage=CoverageReport(verdict=CoverageVerdict.CANNOT_JUDGE,
                                    source=spec.source, source_path=spec.path),
            tracker_name=tracker_name,
            fingerprint=stamp,
            recorded_at=record.now(),
        )

    report = coverage_module.judge(spec, issues, thresholds)
    flags = quality.inspect(issues, thresholds)
    verdict, reasons = _verdict_for(report, flags, len(issues), thresholds)

    return IntakeResult(
        spec_considered=spec.considered,
        verdict=verdict,
        issue_count=len(issues),
        coverage=report,
        flags=flags,
        tracker_name=tracker_name,
        label_counts=_label_counts(issues),
        stop_reasons=reasons,
        fingerprint=stamp,
        recorded_at=record.now(),
    )


def _verdict_for(report: CoverageReport, flags, issue_count: int, thresholds):
    """Coverage decides first; ticket quality can only hold things up, never pass them.

    A gap in coverage is the playbook's to fill, because the missing thing is work that
    was never written down. Unusable tickets are the user's to sort out, and only stop
    the run when they affect enough of the backlog that grouping would be guesswork.

    Returns the verdict and, when the reason for stopping is not already visible in the
    coverage report, a plain-language sentence saying what it was.
    """
    if report.verdict is CoverageVerdict.GAPS:
        return Verdict.NEEDS_PLAYBOOK, ()
    if report.verdict is CoverageVerdict.CANNOT_JUDGE:
        return Verdict.NEEDS_TIDYING, ()

    reasons: List[str] = []
    if issue_count < thresholds.thin_issue_count:
        reasons.append(
            f"There are only {issue_count} of them, which is fewer than this project "
            f"expects to see ({thresholds.thin_issue_count}) before sharing work out. "
            "That usually means most of the job is not written down yet.")
    flagged = len(quality.flagged_refs(flags))
    if issue_count and flagged / issue_count >= thresholds.tidy_flag_ratio:
        reasons.append(
            f"{flagged} of the {issue_count} are unclear to me, which is too many to "
            "sort into groups without guessing.")
    if reasons:
        return Verdict.NEEDS_TIDYING, tuple(reasons)
    return Verdict.READY, ()


def _label_counts(issues: Sequence):
    counts: Counter = Counter()
    for issue in issues:
        for label in issue.labels:
            counts[label] += 1
    return tuple(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
