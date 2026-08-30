"""Lane configuration and mechanical path matching engine."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import List, Optional
from .config import LaneConfig


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
        return path_str.lstrip("/")

    @staticmethod
    def match_glob(path_str: str, pattern: str) -> bool:
        """Matches posix path string against a glob pattern with ** support."""
        norm_pattern = pattern.replace("\\", "/").lstrip("/")
        norm_path = path_str

        # Exact match
        if norm_pattern == norm_path:
            return True

        # Directory wildcard (e.g. 'src/backend/**')
        if norm_pattern.endswith("/**"):
            prefix = norm_pattern[:-3]
            return norm_path == prefix or norm_path.startswith(prefix + "/")

        # Prefix wildcard (e.g. '**/test_*.py')
        if norm_pattern.startswith("**/"):
            suffix = norm_pattern[3:]
            filename = PurePosixPath(norm_path).name
            if fnmatch.fnmatch(filename, suffix) or fnmatch.fnmatch(norm_path, suffix):
                return True

        # Standard fnmatch
        return fnmatch.fnmatch(norm_path, norm_pattern)

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
        ignored_prefixes = (".parallel-agents/", ".git/")
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
