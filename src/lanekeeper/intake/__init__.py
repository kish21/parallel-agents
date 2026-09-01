"""Step 1 of `lanekeeper start`: is the work written down, and does it cover
the features?

See docs/start-step1-intake.md. The package decides and returns a value; printing it
is `presenter`'s job and running it is the CLI's.
"""

from __future__ import annotations

from .gate import run_intake
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

__all__ = [
    "CoverageReport",
    "CoverageVerdict",
    "Feature",
    "FeatureMatch",
    "FlagKind",
    "IntakeResult",
    "ProductSpec",
    "QualityFlag",
    "SpecSource",
    "Verdict",
    "run_intake",
]
