"""Does the written-down work cover the features the product is meant to have?

Three outcomes, and the third is the point of the module:

* `COVERED`     — every feature named in the product description has a ticket.
* `GAPS`        — these features appear to have nothing written against them.
* `CANNOT_JUDGE`— there is no description of the product to compare against, so the
                  question is not answered at all.

`CANNOT_JUDGE` is never softened into one of the other two. Reporting "looks complete"
because there was nothing to check against would be a confident-looking verdict on a
question that was never asked, and every later step is derived from this answer.
"""

from __future__ import annotations

from typing import List, Sequence

from .models import CoverageReport, CoverageVerdict, Feature, FeatureMatch, ProductSpec, SpecSource
from .spec import tokens


def judge(spec: ProductSpec, issues: Sequence, thresholds) -> CoverageReport:
    """Matches each feature to the tickets that appear to be about it."""
    if spec.source is SpecSource.NONE or not spec.has_features:
        return CoverageReport(
            verdict=CoverageVerdict.CANNOT_JUDGE,
            source=SpecSource.NONE,
            source_path=spec.path,
        )

    issue_tokens = [(issue, _issue_tokens(issue)) for issue in issues]

    matches: List[FeatureMatch] = []
    uncovered: List[Feature] = []
    for feature in spec.features:
        refs = tuple(
            issue.ref
            for issue, its in issue_tokens
            if _score(feature, its) >= thresholds.feature_match_score
        )
        matches.append(FeatureMatch(feature=feature, issue_refs=refs))
        if not refs:
            uncovered.append(feature)

    return CoverageReport(
        verdict=CoverageVerdict.GAPS if uncovered else CoverageVerdict.COVERED,
        source=spec.source,
        source_path=spec.path,
        matches=tuple(matches),
        uncovered=tuple(uncovered),
    )


def _issue_tokens(issue) -> set:
    """A ticket's words: its title, its labels, and its body.

    The body is included because a well-written ticket names its feature in the "files
    and code areas this touches" section rather than in the title.
    """
    words = set(tokens(issue.title))
    for label in issue.labels:
        words |= set(tokens(label))
    words |= set(tokens(issue.body))
    return words


def _score(feature: Feature, issue_words: set) -> float:
    """The share of the feature's own words that the ticket carries.

    Deliberately asymmetric: a long ticket should not be penalised for saying more than
    the feature's name, but a ticket that carries only one word of a five-word feature
    name is not about that feature.
    """
    feature_words = set(tokens(feature.name))
    if not feature_words:
        return 0.0
    return len(feature_words & issue_words) / len(feature_words)
