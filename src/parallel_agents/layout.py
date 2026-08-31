"""Repository layout detection, so generated lanes match the project that exists.

The stock lanes assume `backend/`, `src/backend/`, `frontend/`, `web/`. Almost no real
project is laid out that way, so on a normal repository every lane matched nothing and a
user's first `validate` failed on entirely legitimate work — with an error that pointed at
the file rather than at the lane configuration that was actually wrong.

This module reads the repository's tracked files and derives lanes from what is really
there, then reports how much of the tree the result covers so a poor match is visible at
`init` time rather than at review time.
"""

from __future__ import annotations

import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import LaneConfig
from .lanes import LaneEngine

# Directory names that reliably indicate a role.
ROLE_BY_DIR_NAME = {
    "backend": "backend", "server": "backend", "api": "backend",
    "services": "backend", "service": "backend", "worker": "backend",
    "frontend": "frontend", "web": "frontend", "client": "frontend",
    "ui": "frontend", "www": "frontend", "site": "frontend",
    "database": "data", "migrations": "data", "models": "data",
    "db": "data", "schema": "data", "sql": "data",
    "infra": "platform", "infrastructure": "platform", "ops": "platform",
    "deploy": "platform", "deployment": "platform", "scripts": "platform",
    "terraform": "platform", "k8s": "platform", "kubernetes": "platform",
    ".github": "platform", "ci": "platform",
}

# Extension majority, used when the directory name says nothing useful.
ROLE_BY_EXTENSION = {
    "backend": {".py", ".go", ".rb", ".java", ".kt", ".rs", ".php", ".cs", ".ex", ".exs"},
    "frontend": {".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".html",
                 ".ts", ".js", ".mjs", ".cjs"},
    "data": {".sql", ".prisma"},
    "platform": {".tf", ".yaml", ".yml", ".dockerfile", ".sh"},
}

# Directories that are never a lane.
IGNORED_DIRS = {
    ".git", ".parallel-agents", "node_modules", "venv", ".venv", "__pycache__",
    "dist", "build", "target", ".idea", ".vscode", "vendor", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "coverage", ".next", ".nuxt",
}

# A container directory is not itself a lane; its children are.
CONTAINER_DIRS = {"src", "packages", "apps", "modules", "libs", "cmd", "internal"}


@dataclass
class DetectedLayout:
    lanes: Dict[str, LaneConfig] = field(default_factory=dict)
    coverage: float = 0.0
    total_files: int = 0
    covered_files: int = 0
    uncovered_examples: List[str] = field(default_factory=list)
    detected_from: str = "defaults"

    @property
    def is_usable(self) -> bool:
        """Whether the lanes actually describe this repository.

        Below roughly half, the configuration is more likely to obstruct work than to
        partition it, and the user needs to know that before spawning anything.
        """
        return self.coverage >= 0.5

    @property
    def substantive_lanes(self) -> List[str]:
        """Lanes that own a real directory, ignoring the root-files catch-all.

        A repository holding nothing but a README yields a single `platform` lane whose
        only pattern is the root glob. That is technically full coverage and tells us
        nothing, so it must not be mistaken for a detected structure.
        """
        return [name for name, lane in self.lanes.items() if any(p != "*" for p in lane.allow)]

    @property
    def is_meaningful(self) -> bool:
        """Whether to prefer these lanes over the generic starter set.

        Requires at least one lane covering a real directory. A repository with nothing
        but root-level files yields only the root catch-all, which describes no structure
        at all — there the generic starter lanes are the better starting point.

        One substantive lane is enough to adopt: a single-purpose project genuinely has
        one code area, and lanes that match it beat lanes that match nothing. Whether that
        repository is *separable enough to run agents in parallel* is a different question,
        reported separately as a warning.
        """
        return len(self.substantive_lanes) >= 1 and self.is_usable


def tracked_files(root: Path) -> List[str]:
    """Files git knows about — the honest picture of the project, minus build output."""
    try:
        res = subprocess.run(
            ["git", "ls-files", "-z"], cwd=str(root),
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return []
    return [f for f in res.stdout.split("\0") if f]


def _classify(dir_name: str, files: List[str]) -> Optional[str]:
    role = ROLE_BY_DIR_NAME.get(dir_name.lower())
    if role:
        return role
    counts: Counter = Counter()
    for f in files:
        ext = Path(f).suffix.lower()
        for candidate, extensions in ROLE_BY_EXTENSION.items():
            if ext in extensions:
                counts[candidate] += 1
    return counts.most_common(1)[0][0] if counts else None


def _lane_roots(paths: List[str]) -> Dict[str, List[str]]:
    """Groups files under the directory that should own them.

    A container such as `src/` or `packages/` is transparent: its children become the
    lane roots, so `src/api` and `src/web` are separate owners rather than one `src` lane.
    """
    groups: Dict[str, List[str]] = defaultdict(list)
    for path in paths:
        parts = path.split("/")
        if len(parts) == 1:
            continue  # a root-level file belongs to no directory lane
        head = parts[0]
        if head in IGNORED_DIRS:
            continue
        if head in CONTAINER_DIRS and len(parts) > 2:
            groups[f"{head}/{parts[1]}"].append(path)
        else:
            groups[head].append(path)
    return groups


def detect_layout(root: Path) -> DetectedLayout:
    """Derives lanes from the repository's real directory structure."""
    files = tracked_files(root)
    if not files:
        return DetectedLayout(detected_from="empty-repository")

    groups = _lane_roots(files)
    if not groups and not any("/" not in f for f in files):
        return DetectedLayout(total_files=len(files), detected_from="no-directories")

    # Assign each directory to a role, merging directories that share one. Every tracked
    # directory gets an owner — a small directory is still somebody's to edit, and leaving
    # it unclaimed is what produced "out-of-lane" errors on legitimate work.
    by_role: Dict[str, List[str]] = defaultdict(list)
    for directory, dir_files in sorted(groups.items()):
        role = _classify(Path(directory).name, dir_files) or directory.replace("/", "-")
        by_role[role].append(directory)

    lanes: Dict[str, LaneConfig] = {}
    for role, directories in by_role.items():
        lanes[role] = LaneConfig(name=role, allow=[f"{d}/**" for d in sorted(directories)], deny=[])

    # Root-level files (pyproject.toml, package.json, README) belong to no directory, so
    # nothing would own them. Give them to platform: repository-level configuration is
    # exactly that lane's remit. A bare '*' matches one path segment and therefore only
    # the repository root, never a nested file.
    if any("/" not in f for f in files):
        platform = lanes.setdefault("platform", LaneConfig(name="platform", allow=[], deny=[]))
        platform.allow.append("*")

    # One lane, one owner: every lane explicitly denies every other lane's paths, so an
    # overlap is impossible rather than merely discouraged.
    for name, lane in lanes.items():
        lane.deny = sorted(p for other, o in lanes.items() if other != name for p in o.allow)

    covered = [f for f in files
               if any(LaneEngine.match_glob(f, p) for lane in lanes.values() for p in lane.allow)]
    uncovered = [f for f in files if f not in set(covered)]

    return DetectedLayout(
        lanes=lanes,
        coverage=len(covered) / len(files) if files else 0.0,
        total_files=len(files),
        covered_files=len(covered),
        uncovered_examples=sorted(uncovered)[:5],
        detected_from="git-tracked-files",
    )


def measure_coverage(root: Path, lanes: Dict[str, LaneConfig]) -> Tuple[float, int, List[str]]:
    """How much of the repository a given lane set actually claims."""
    files = tracked_files(root)
    if not files:
        return 0.0, 0, []
    covered = [f for f in files
               if any(LaneEngine.match_glob(f, p) for lane in lanes.values() for p in lane.allow)]
    uncovered = sorted(f for f in files if f not in set(covered))
    return len(covered) / len(files), len(files), uncovered[:5]
