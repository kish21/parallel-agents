"""The typed contracts crossing every boundary in step 1.

Nothing here does any work. These are the values `intake.gate` assembles and step 2
(#38) will be handed: a raw dict would let a later step read a field that was never
computed and get `None` where a judgement was required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class SpecSource(Enum):
    """What the issues were compared against, in order of preference."""

    PRODUCT_MD = "product-md"   # the playbook's own output — the intended path
    DOCS = "docs"               # a README or other document describing the product
    NONE = "none"               # nothing to compare against


class CoverageVerdict(Enum):
    COVERED = "covered"
    GAPS = "gaps"
    #: Not a soft "no". It is the honest answer when there is no description of the
    #: product to compare the tickets against, and it must never be dressed up as one
    #: of the other two.
    CANNOT_JUDGE = "cannot-judge"


class Verdict(Enum):
    """Whether the rest of `lanekeeper start` may run."""

    READY = "ready"
    #: The work is not written down, or does not cover the product. product-playbook
    #: writes work; lanekeeper divides it. This hands back to the playbook.
    NEEDS_PLAYBOOK = "needs-playbook"
    #: There is work, but it cannot be trusted to divide yet, or coverage could not be
    #: judged. The user is told what is unclear and decides.
    NEEDS_TIDYING = "needs-tidying"


@dataclass(frozen=True)
class Feature:
    """One thing the product is meant to do, as the product description states it."""

    name: str
    source_line: str = ""


@dataclass(frozen=True)
class ProductSpec:
    """The description of the product that coverage is judged against."""

    source: SpecSource = SpecSource.NONE
    path: Optional[str] = None
    features: Tuple[Feature, ...] = ()
    #: Which files were looked at and what was found, so a bad read is visible.
    considered: Tuple[str, ...] = ()

    @property
    def has_features(self) -> bool:
        return bool(self.features)


@dataclass(frozen=True)
class FeatureMatch:
    feature: Feature
    issue_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CoverageReport:
    verdict: CoverageVerdict
    source: SpecSource = SpecSource.NONE
    source_path: Optional[str] = None
    matches: Tuple[FeatureMatch, ...] = ()
    uncovered: Tuple[Feature, ...] = ()


class FlagKind(Enum):
    """Ways a ticket can exist and still not be usable for dividing work."""

    NO_FILE_HINT = "no-file-hint"
    NO_LABELS = "no-labels"
    POSSIBLE_DUPLICATE = "possible-duplicate"
    BROAD_TICKET = "broad-ticket"


@dataclass(frozen=True)
class QualityFlag:
    kind: FlagKind
    issue_refs: Tuple[str, ...]
    detail: str


@dataclass(frozen=True)
class IntakeResult:
    """Everything step 1 concluded. The whole of what step 2 is handed."""

    verdict: Verdict
    issue_count: int
    coverage: CoverageReport
    flags: Tuple[QualityFlag, ...] = ()
    tracker_name: str = ""
    tracker_available: bool = True
    tracker_note: str = ""
    label_counts: Tuple[Tuple[str, int], ...] = ()
    #: Which documents were opened looking for a description of the product. Reported
    #: even when none of them yielded one: "I found nothing" and "I looked in your
    #: README and it does not list what this product does" are different sentences, and
    #: only the second tells the user what to do about it.
    spec_considered: Tuple[str, ...] = ()
    #: Why the run stopped, in plain language, when the reason is not visible from the
    #: coverage report alone — a backlog too small to divide, or too many unclear
    #: tickets. A stop the user cannot see the reason for is indistinguishable from a
    #: broken tool.
    stop_reasons: Tuple[str, ...] = ()
    fingerprint: str = ""
    recorded_at: str = ""
    #: The user was told what could not be judged and said to carry on anyway. Bound to
    #: the fingerprint, so a change to the work asks again rather than staying accepted.
    accepted_as_is: bool = False
    #: Set when a previous run's record was reused instead of being recomputed.
    resumed: bool = field(default=False, compare=False)

    @property
    def passed(self) -> bool:
        return self.verdict is Verdict.READY
