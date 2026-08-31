"""Lane configuration and mechanical path matching engine."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import List, Optional
from .config import LaneConfig
from . import paths


@dataclass
class LaneViolation:
    filepath: str
    reason: str  # "denied" or "not_allowed"
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

        if norm_pattern == norm_path:
            return True

        # A trailing '/**' also matches the directory itself, not only its contents.
        if norm_pattern.endswith("/**") and norm_path == norm_pattern[:-3]:
            return True

        return bool(cls._compile(norm_pattern).match(norm_path))

    @classmethod
    def check_file(cls, filepath: str | Path, lane: LaneConfig) -> Optional[LaneViolation]:
        path_str = cls.normalize_path(filepath)

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

        # Built-in internal files to ignore
        ignored_prefixes = paths.ignored_prefixes()
        ignored_exact = (".env", ".lane", ".gitignore")

        for f in files:
            norm_f = cls.normalize_path(f)
            if any(norm_f.startswith(p) for p in ignored_prefixes) or norm_f in ignored_exact:
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
