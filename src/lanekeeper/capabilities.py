"""Capability cards: making a seat's declared limits mechanically enforceable.

A lane answers *where* a seat may work. A capability card answers *what kind of work* it
is competent to do there. Both fail closed: an undeclared seat, or a capability a card
does not mention, stops the operation rather than permitting it.

The card schema is the one specified in 03-orchestration.md, unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from . import paths



class CapabilityState(str, Enum):
    """The three states from 03-orchestration.md §1.

    Two states would collapse the distinction that matters: a harness that *can* do
    something with a written procedure carries a very different risk from one that cannot
    do it at all.
    """

    NATIVE = "native"
    AUTHOR_REQUIRED = "author-required"
    UNAVAILABLE = "unavailable"

    @classmethod
    def parse(cls, raw: str) -> "CapabilityState":
        try:
            return cls(str(raw).strip().lower())
        except ValueError:
            valid = ", ".join(s.value for s in cls)
            raise CapabilityCardError(
                f"Invalid capability state '{raw}'. Must be one of: {valid}."
            ) from None


class CapabilityCardError(ValueError):
    """Raised when a capability card is malformed."""


class UnknownSeatError(KeyError):
    """Raised when a seat has no declared capability card.

    Seat lookup fails closed. A seat with no card cannot be evaluated against any gate,
    so it must not be allowed to work on gated paths.
    """

    def __init__(self, seat: str, known_seats: List[str]):
        self.seat = seat
        self.known_seats = sorted(known_seats)
        known = ", ".join(self.known_seats) if self.known_seats else "(none declared)"
        super().__init__(f"Unknown seat '{seat}'. Declared seats: {known}.")

    def __str__(self) -> str:
        return self.args[0]


@dataclass
class CapabilityCard:
    seat: str
    vendor_harness: str = ""
    capabilities: Dict[str, str] = field(default_factory=dict)
    max_allowed_lane_scope: List[str] = field(default_factory=list)
    forbidden_paths: List[str] = field(default_factory=list)

    def state_for(self, capability: str) -> CapabilityState:
        """The seat's rating for a capability.

        A capability the card does not mention is treated as UNAVAILABLE. Absence is not
        permission: a card that forgot to rate `security_review` must not thereby be
        allowed to perform it.
        """
        raw = self.capabilities.get(capability)
        if raw is None:
            return CapabilityState.UNAVAILABLE
        return CapabilityState.parse(raw)

    def declares(self, capability: str) -> bool:
        return capability in self.capabilities

    def allows_lane(self, lane: str) -> bool:
        """An empty scope means no lane restriction; a non-empty one is exhaustive."""
        return not self.max_allowed_lane_scope or lane in self.max_allowed_lane_scope

    def to_dict(self) -> Dict[str, object]:
        return {
            "seat": self.seat,
            "vendor_harness": self.vendor_harness,
            "capabilities": dict(self.capabilities),
            "max_allowed_lane_scope": list(self.max_allowed_lane_scope),
            "forbidden_paths": list(self.forbidden_paths),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object], source: Optional[Path] = None) -> "CapabilityCard":
        where = f" in {source}" if source else ""
        if not isinstance(data, dict):
            raise CapabilityCardError(f"Capability card{where} must be a JSON object.")

        seat = data.get("seat")
        if not seat or not isinstance(seat, str):
            raise CapabilityCardError(f"Capability card{where} is missing a 'seat' name.")

        caps_raw = data.get("capabilities", {})
        if not isinstance(caps_raw, dict):
            raise CapabilityCardError(f"'capabilities'{where} must be an object.")
        # Validate every state up front so a typo surfaces at load time, not at the
        # moment a gate is evaluated.
        capabilities = {}
        for name, state in caps_raw.items():
            CapabilityState.parse(state)
            capabilities[str(name)] = str(state).strip().lower()

        return cls(
            seat=seat,
            vendor_harness=str(data.get("vendor_harness", "") or ""),
            capabilities=capabilities,
            max_allowed_lane_scope=[str(x) for x in data.get("max_allowed_lane_scope", []) or []],
            forbidden_paths=[str(x) for x in data.get("forbidden_paths", []) or []],
        )


class CapabilityRegistry:
    """All capability cards declared in a repository."""

    def __init__(self, cards: Dict[str, CapabilityCard]):
        self.cards = cards

    def __len__(self) -> int:
        return len(self.cards)

    @property
    def is_empty(self) -> bool:
        return not self.cards

    def seats(self) -> List[str]:
        return sorted(self.cards)

    def has_seat(self, seat: str) -> bool:
        return seat in self.cards

    def get(self, seat: str) -> CapabilityCard:
        """Returns the seat's card, or raises. There is no permissive default."""
        card = self.cards.get(seat)
        if card is None:
            raise UnknownSeatError(seat, list(self.cards))
        return card

    @classmethod
    def load(cls, root_dir: Optional[Path] = None) -> "CapabilityRegistry":
        root = root_dir or Path.cwd()
        cards_dir = paths.capabilities_dir(root)
        cards: Dict[str, CapabilityCard] = {}
        if not cards_dir.is_dir():
            return cls(cards)

        for path in sorted(cards_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise CapabilityCardError(f"Capability card {path} is not valid JSON: {e}") from e
            card = CapabilityCard.from_dict(data, source=path)
            cards[card.seat] = card
        return cls(cards)


def save_card(card: CapabilityCard, root_dir: Optional[Path] = None) -> Path:
    root = root_dir or Path.cwd()
    cards_dir = paths.capabilities_dir(root)
    cards_dir.mkdir(parents=True, exist_ok=True)
    path = cards_dir / f"{card.seat}.json"
    path.write_text(json.dumps(card.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def default_cards(lanes: List[str]) -> List[CapabilityCard]:
    """Starter cards for the four standard seats.

    Senior seats are rated native throughout. Junior seats are deliberately *not*: they
    are author-required for deep review and migrations, and unavailable for security
    review. That is the point of the model — the ratings encode a real difference, so the
    gates have something to bite on out of the box.
    """
    senior = {
        "file_level_code_generation": "native",
        "unit_test_generation": "native",
        "local_test_execution": "native",
        "deep_code_review": "native",
        "security_review": "native",
        "database_migrations": "native",
    }
    junior = {
        "file_level_code_generation": "native",
        "unit_test_generation": "native",
        "local_test_execution": "native",
        "deep_code_review": "author-required",
        "security_review": "unavailable",
        "database_migrations": "author-required",
    }
    return [
        CapabilityCard(seat="SR1", vendor_harness="", capabilities=dict(senior),
                       max_allowed_lane_scope=list(lanes), forbidden_paths=[]),
        CapabilityCard(seat="SR2", vendor_harness="", capabilities=dict(senior),
                       max_allowed_lane_scope=list(lanes), forbidden_paths=[]),
        CapabilityCard(seat="JR1", vendor_harness="", capabilities=dict(junior),
                       max_allowed_lane_scope=list(lanes), forbidden_paths=[]),
        CapabilityCard(seat="JR2", vendor_harness="", capabilities=dict(junior),
                       max_allowed_lane_scope=list(lanes), forbidden_paths=[]),
    ]
