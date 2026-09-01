"""What step 1 decided, written down so the next run continues instead of restarting.

`lanekeeper start` is one guided command a user may run several times — fix the tickets,
run it again. Re-asking a question that has already been answered is how a guided
command turns into a form, so the answer is recorded with a fingerprint of what it was
based on: unchanged input and a passing verdict means step 1 is skipped, changed input
means it runs again.

Only a passing result is recorded. A run that stopped at the gate wrote nothing, which
is what lets `start` promise it changes nothing on a repository it cannot help yet.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from .. import paths
from .models import (
    CoverageReport,
    CoverageVerdict,
    Feature,
    FeatureMatch,
    FlagKind,
    IntakeResult,
    ProductSpec,
    QualityFlag,
    SpecSource,
    Verdict,
)

#: Bumped when the recorded shape changes, so an old record is re-run rather than
#: half-read.
RECORD_VERSION = 1


def fingerprint(tracker_name: str, issues: Sequence, spec: ProductSpec,
                thresholds=None) -> str:
    """A stable hash of everything step 1's answer depends on.

    Everything it depends on, and nothing else. The ticket bodies are in here because
    both the coverage match and the file-hint check read them — leaving them out meant a
    backlog could be gutted and the next run would still say "nothing has changed since".
    The thresholds are in here for the same reason: they are what the answer was judged
    by, so editing one has to re-ask the question rather than resume the old answer.

    The product description contributes its path and the feature names read out of it,
    so editing prose around a feature list does not invalidate an answer that never
    depended on the prose.
    """
    digest = hashlib.sha256()
    digest.update(f"v{RECORD_VERSION}\n{tracker_name}\n".encode("utf-8"))
    for issue in sorted(issues, key=lambda i: str(i.ref)):
        labels = ",".join(sorted(issue.labels))
        digest.update(
            f"{issue.ref}\x1f{issue.title}\x1f{labels}\x1f{issue.body}\x1e".encode("utf-8"))
    digest.update(f"\n{spec.source.value}\x1f{spec.path or ''}\x1e".encode("utf-8"))
    for feature in spec.features:
        digest.update(f"{feature.name}\x1e".encode("utf-8"))
    if thresholds is not None:
        for name in sorted(vars(thresholds)):
            digest.update(f"{name}={getattr(thresholds, name)}\x1e".encode("utf-8"))
    return digest.hexdigest()


def save(result: IntakeResult, root: Path) -> Path:
    path = paths.intake_record_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"record_version": RECORD_VERSION, **_result_to_dict(result)}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load(root: Path) -> Optional[IntakeResult]:
    """The previous result, or None when there is none or it cannot be read.

    A record that cannot be read is discarded rather than raised: it is a cache of a
    cheap computation, and failing the whole command because of it would be worse than
    doing the work again.
    """
    path = paths.intake_record_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or data.get("record_version") != RECORD_VERSION:
        return None
    try:
        return _result_from_dict(data)
    except (KeyError, ValueError, TypeError):
        return None


def clear(root: Path) -> None:
    path = paths.intake_record_path(root)
    if path.is_file():
        path.unlink()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# -- serialisation ---------------------------------------------------------------


def _result_to_dict(result: IntakeResult) -> dict:
    return {
        "verdict": result.verdict.value,
        "issue_count": result.issue_count,
        "tracker_name": result.tracker_name,
        "tracker_available": result.tracker_available,
        "tracker_note": result.tracker_note,
        "label_counts": [list(pair) for pair in result.label_counts],
        "stop_reasons": list(result.stop_reasons),
        "spec_considered": list(result.spec_considered),
        "fingerprint": result.fingerprint,
        "recorded_at": result.recorded_at,
        "accepted_as_is": result.accepted_as_is,
        "coverage": {
            "verdict": result.coverage.verdict.value,
            "source": result.coverage.source.value,
            "source_path": result.coverage.source_path,
            "matches": [
                {
                    "feature": match.feature.name,
                    "source_line": match.feature.source_line,
                    "issue_refs": list(match.issue_refs),
                }
                for match in result.coverage.matches
            ],
            "uncovered": [f.name for f in result.coverage.uncovered],
        },
        "flags": [
            {"kind": f.kind.value, "issue_refs": list(f.issue_refs), "detail": f.detail}
            for f in result.flags
        ],
    }


def _result_from_dict(data: dict) -> IntakeResult:
    cov = data.get("coverage") or {}
    matches = tuple(
        FeatureMatch(
            feature=Feature(name=m["feature"], source_line=m.get("source_line", "")),
            issue_refs=tuple(m.get("issue_refs", [])),
        )
        for m in cov.get("matches", [])
    )
    coverage = CoverageReport(
        verdict=CoverageVerdict(cov["verdict"]),
        source=SpecSource(cov.get("source", SpecSource.NONE.value)),
        source_path=cov.get("source_path"),
        matches=matches,
        uncovered=tuple(Feature(name=n) for n in cov.get("uncovered", [])),
    )
    flags = tuple(
        QualityFlag(
            kind=FlagKind(f["kind"]),
            issue_refs=tuple(f.get("issue_refs", [])),
            detail=f.get("detail", ""),
        )
        for f in data.get("flags", [])
    )
    return IntakeResult(
        verdict=Verdict(data["verdict"]),
        issue_count=int(data.get("issue_count", 0)),
        coverage=coverage,
        flags=flags,
        tracker_name=data.get("tracker_name", ""),
        tracker_available=bool(data.get("tracker_available", True)),
        tracker_note=data.get("tracker_note", ""),
        label_counts=tuple((str(k), int(v)) for k, v in data.get("label_counts", [])),
        stop_reasons=tuple(str(r) for r in data.get("stop_reasons", [])),
        spec_considered=tuple(str(c) for c in data.get("spec_considered", [])),
        fingerprint=data.get("fingerprint", ""),
        recorded_at=data.get("recorded_at", ""),
        accepted_as_is=bool(data.get("accepted_as_is", False)),
    )
