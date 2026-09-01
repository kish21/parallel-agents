"""Lane configuration and mechanical path matching engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from .config import LaneConfig
from . import paths


@dataclass
class LaneViolation:
    filepath: str
    reason: str  # "denied", "not_allowed" or "policy"
    matched_pattern: Optional[str] = None


@dataclass
class LaneValidationResult:
    lane_name: str
    is_valid: bool
    allowed_files: List[str] = field(default_factory=list)
    violations: List[LaneViolation] = field(default_factory=list)


class LaneEngine:
    """Evaluates changed files against lane allow/deny glob policies."""

    @staticmethod
    def normalize_path(filepath: str | Path) -> str:
        """Converts file path to posix-style relative string (e.g. 'src/backend/app.py')."""
        if isinstance(filepath, Path):
            path_str = filepath.as_posix()
        else:
            path_str = str(filepath).replace("\\", "/")
        return path_str.strip("/")

    @staticmethod
    @lru_cache(maxsize=512)
    def _compile(pattern: str) -> "re.Pattern[str]":
        """Translates a path glob into an anchored regex.

        Segment-aware, which the previous implementation was not:

        * ``**``  matches zero or more whole path segments
        * ``*``   matches within one segment (never crosses ``/``)
        * ``?``   matches a single character within one segment

        The earlier version short-circuited on any pattern ending in ``/**`` and returned
        a prefix comparison, so a pattern that both began with ``**/`` and ended with
        ``/**`` — e.g. ``**/secrets/**`` — could never match anything. A lane denying that
        path silently denied nothing.
        """
        parts = pattern.split("/")
        out = ["^"]
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            if part == "**":
                # Trailing ** absorbs the remainder; an interior ** spans whole segments.
                out.append(".*" if last else "(?:[^/]+/)*")
                continue
            segment = ""
            for ch in part:
                if ch == "*":
                    segment += "[^/]*"
                elif ch == "?":
                    segment += "[^/]"
                else:
                    segment += re.escape(ch)
            out.append(segment)
            if not last:
                out.append("/")
        out.append("$")
        return re.compile("".join(out))

    @classmethod
    def match_glob(cls, path_str: str, pattern: str) -> bool:
        """Matches a posix path string against a glob pattern with full ** support."""
        norm_pattern = pattern.replace("\\", "/").lstrip("/")
        norm_path = path_str.replace("\\", "/").strip("/")

        # A pattern written as a directory — `secrets/` — means everything under it.
        # Previously it matched nothing at all in a lane, while the capability gates
        # expanded the same spelling to `secrets/**`, so a deny written the natural way
        # was a silent no-op in one half of the tool and enforced in the other.
        if norm_pattern.endswith("/"):
            norm_pattern = norm_pattern + "**"

        if norm_pattern == norm_path:
            return True

        # A trailing '/**' also matches the directory itself, not only its contents.
        if norm_pattern.endswith("/**") and norm_path == norm_pattern[:-3]:
            return True

        return bool(cls._compile(norm_pattern).match(norm_path))

    #: Files lanekeeper itself writes into every worktree. They are ignored by git and
    #: carry no work, so they never count against a lane.
    RUNTIME_FILES = (".env", ".lane")

    @classmethod
    def is_bookkeeping(cls, filepath: str | Path) -> bool:
        """Whether a path is runtime state rather than work, and so outside any lane."""
        norm = cls.normalize_path(filepath)
        return norm in cls.RUNTIME_FILES or any(
            norm.startswith(p) for p in paths.ignored_prefixes())

    @classmethod
    def is_policy(cls, filepath: str | Path) -> bool:
        """Whether a path defines the lanes themselves. No lane may touch it."""
        norm = cls.normalize_path(filepath)
        for p in paths.policy_paths():
            if norm == p or (p.endswith("/") and norm.startswith(p)):
                return True
        return False

    @classmethod
    def check_file(cls, filepath: str | Path, lane: LaneConfig) -> Optional[LaneViolation]:
        path_str = cls.normalize_path(filepath)

        # 0. The policy is not subject to the policy: it is denied to every lane, before
        #    an `allow` as wide as `**` gets a say.
        if cls.is_policy(path_str):
            return LaneViolation(filepath=path_str, reason="policy", matched_pattern=None)

        # 1. Check explicit Deny patterns first
        for deny_pat in lane.deny:
            if cls.match_glob(path_str, deny_pat):
                return LaneViolation(
                    filepath=path_str,
                    reason="denied",
                    matched_pattern=deny_pat,
                )

        # 2. Check Allow patterns (if specified)
        if lane.allow:
            matched_allow = False
            for allow_pat in lane.allow:
                if cls.match_glob(path_str, allow_pat):
                    matched_allow = True
                    break
            if not matched_allow:
                return LaneViolation(
                    filepath=path_str,
                    reason="not_allowed",
                    matched_pattern=None,
                )

        return None

    @classmethod
    def validate_files(cls, files: List[str | Path], lane: LaneConfig) -> LaneValidationResult:
        allowed: List[str] = []
        violations: List[LaneViolation] = []

        for f in files:
            norm_f = cls.normalize_path(f)
            if cls.is_bookkeeping(norm_f):
                continue

            violation = cls.check_file(norm_f, lane)
            if violation:
                violations.append(violation)
            else:
                allowed.append(norm_f)

        return LaneValidationResult(
            lane_name=lane.name,
            is_valid=len(violations) == 0,
            allowed_files=allowed,
            violations=violations,
        )
