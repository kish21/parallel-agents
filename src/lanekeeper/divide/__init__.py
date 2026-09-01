"""Step 2 of `lanekeeper start`: divide the work.

Group the tickets where they group; where they do not, show them and ask which ones to
hand out on their own. Never blocks, never guesses, never calls a model.

See docs/start-step2-divide.md. The package decides and returns a value; printing it is
`presenter`'s job and running it is the CLI's.
"""

from __future__ import annotations

from .models import (
    CodeSlice,
    DivisionProposal,
    DraftProblem,
    Overlap,
    PathSource,
    Placement,
    ProposedLane,
    TicketBoundary,
    ValidationReport,
)
from .proposal import propose

__all__ = [
    "CodeSlice",
    "DivisionProposal",
    "DraftProblem",
    "Overlap",
    "PathSource",
    "Placement",
    "ProposedLane",
    "TicketBoundary",
    "ValidationReport",
    "propose",
]
