"""Taking lanekeeper back out of a repository.

`init` and `spawn --ticket` write into a project somebody already cares about: a
directory of state, a managed block in the project's `.gitignore`, a workflow, a
branch and a worktree per agent. Until this module existed, undoing that was five
manual steps the user had to reconstruct from what they remembered running — which
made *trying* the tool expensive, on exactly the repository where it has to be tried.
Issue #26.

The plan is built before anything is removed and printed in full, because the one
thing worse than leaving residue behind is deleting work nobody has merged. That is
also why an unmerged branch is never deleted here, not even with `--force`: `--force`
answers the question "are you sure", it does not decide that somebody's commits do
not matter.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import paths
from .check import WORKFLOW_PATH
from .ports import TERMINAL_STATUSES
from .worktree import GitError, WorktreeManager

#: Workflows lanekeeper writes are named `lanekeeper-*.yml`; the gate is one of them.
WORKFLOW_GLOB = "lanekeeper-*.yml"


@dataclass
class UninitPlan:
    """What `uninit` would remove, and what it deliberately would not."""

    root: Path
    home: Optional[Path] = None
    worktrees: List[Path] = field(default_factory=list)
    branches: List[str] = field(default_factory=list)
    workflows: List[Path] = field(default_factory=list)
    gitignore_block: bool = False
    live_agents: List[str] = field(default_factory=list)
    tracked: List[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.home or self.worktrees or self.branches
                    or self.workflows or self.gitignore_block)


def _tracked_paths(worktree_mgr: WorktreeManager, candidates: List[str]) -> List[str]:
    """Which of these paths git is tracking.

    Removing a tracked file leaves a deletion in `git status`, which is not residue —
    it is a change the person has to commit. Saying so beforehand is the difference
    between a tidy repository and an alarming one.
    """
    if not candidates:
        return []
    try:
        res = worktree_mgr._run_git(["ls-files", "--"] + candidates, check=False)
    except (GitError, OSError):
        return []
    if res.returncode != 0:
        return []
    return sorted({line.strip() for line in res.stdout.splitlines() if line.strip()})


def build_plan(root: Path, worktree_mgr: WorktreeManager,
               agents: Optional[List] = None,
               branch_prefix: str = "parallel/",
               gitignore_marker: str = "") -> UninitPlan:
    """Everything `uninit` can see, gathered before a single thing is removed.

    `agents` is the recorded state when it could be read at all; a repository whose
    state file is missing or damaged still has a home directory and branches on disk,
    and refusing to clean those up because the ledger is unreadable would strand the
    person in exactly the state they are trying to escape.
    """
    plan = UninitPlan(root=root)

    home = paths.home(root)
    if home.exists():
        plan.home = home

    for agent in agents or []:
        if agent.status not in TERMINAL_STATUSES:
            plan.live_agents.append(f"{agent.id} ({agent.name})")
        wt = Path(agent.worktree_path)
        if not wt.is_absolute():
            wt = root / wt
        if wt.exists():
            plan.worktrees.append(wt)

    # A worktree registered with git but not in the ledger is still ours to offer to
    # remove: it is under the directory we created, and a failed cleanup leaves exactly
    # that. Anything outside the directory belongs to the person, and is left alone.
    wt_dir = (root / paths.worktrees_dir()).resolve()
    try:
        for info in worktree_mgr.list_worktrees():
            resolved = info.path.resolve()
            if resolved == root.resolve() or resolved in [w.resolve() for w in plan.worktrees]:
                continue
            if wt_dir in resolved.parents:
                plan.worktrees.append(info.path)
    except (GitError, OSError):
        pass

    try:
        plan.branches = worktree_mgr.list_branches(branch_prefix)
    except (GitError, OSError):
        plan.branches = []

    workflows_dir = root / WORKFLOW_PATH.parent
    if workflows_dir.is_dir():
        plan.workflows = sorted(workflows_dir.glob(WORKFLOW_GLOB))

    gitignore = root / ".gitignore"
    if gitignore_marker and gitignore.exists():
        try:
            plan.gitignore_block = gitignore_marker in gitignore.read_text(encoding="utf-8")
        except OSError:
            plan.gitignore_block = False

    candidates = [p.relative_to(root).as_posix() for p in plan.workflows]
    if plan.home is not None:
        candidates.append(paths.home_dirname(root))
    plan.tracked = _tracked_paths(worktree_mgr, candidates)

    return plan


def strip_gitignore_block(text: str, begin: str, end: str) -> str:
    """The `.gitignore` with lanekeeper's managed block taken out.

    Only between the markers `init` wrote. Anything the person added around it —
    including their own rules that happen to mention the directory — is theirs.
    """
    lines = text.splitlines(keepends=True)
    out: List[str] = []
    inside = False
    for line in lines:
        stripped = line.strip()
        if not inside and stripped == begin:
            inside = True
            # Drop one blank line immediately before the block, which is the one
            # `ensure_gitignore` put there.
            while out and out[-1].strip() == "":
                out.pop()
            continue
        if inside:
            if stripped == end:
                inside = False
            continue
        out.append(line)
    result = "".join(out)
    if result and not result.endswith("\n"):
        result += "\n"
    return result


def render(plan: UninitPlan) -> str:
    """The plan, in the order it will be carried out."""
    if plan.is_empty:
        return "Nothing to remove — this repository has no lanekeeper files in it."

    lines = ["This will remove:"]
    for wt in plan.worktrees:
        lines.append(f"  - the worktree {_display(plan.root, wt)}")
    if plan.branches:
        lines.append(f"  - {len(plan.branches)} agent branch(es), "
                     f"but only the ones git agrees are fully merged:")
        for b in plan.branches:
            lines.append(f"      {b}")
    if plan.home is not None:
        lines.append(f"  - {paths.display_home(plan.root)} (configuration, seat cards, state, logs)")
    for wf in plan.workflows:
        lines.append(f"  - {_display(plan.root, wf)}")
    if plan.gitignore_block:
        lines.append("  - lanekeeper's managed block in .gitignore")

    if plan.tracked:
        lines.append("")
        lines.append("Some of those files are committed, so removing them leaves a deletion")
        lines.append("in 'git status' for you to commit:")
        for t in plan.tracked[:10]:
            lines.append(f"      {t}")
        if len(plan.tracked) > 10:
            lines.append(f"      ... and {len(plan.tracked) - 10} more")
    return "\n".join(lines)


def _display(root: Path, target: Path) -> str:
    try:
        return target.relative_to(root).as_posix()
    except ValueError:
        return str(target)


def apply(plan: UninitPlan, worktree_mgr: WorktreeManager,
          begin: str = "", end: str = "") -> List[str]:
    """Carries out the plan. Returns the lines describing what actually happened.

    Reported rather than assumed: git refuses to delete an unmerged branch, and that
    refusal is the whole safety property here, so it has to reach the person as a
    sentence and not as a silent difference between the plan and the result.
    """
    done: List[str] = []

    for wt in plan.worktrees:
        try:
            worktree_mgr.remove_worktree(wt, force=True)
            done.append(f"Removed the worktree {_display(plan.root, wt)}.")
        except (GitError, OSError) as exc:
            if wt.exists():
                shutil.rmtree(wt, ignore_errors=True)
            if wt.exists():
                done.append(f"Could not remove {_display(plan.root, wt)}: {exc}")
            else:
                done.append(f"Removed the worktree {_display(plan.root, wt)}.")
    if plan.worktrees:
        try:
            worktree_mgr.prune()
        except (GitError, OSError):
            pass

    kept: List[str] = []
    deleted: List[str] = []
    for branch in plan.branches:
        if worktree_mgr.delete_branch(branch):
            deleted.append(branch)
        else:
            kept.append(branch)
    if deleted:
        done.append(f"Deleted {len(deleted)} merged branch(es): {', '.join(deleted)}.")
    if kept:
        done.append(f"Kept {len(kept)} branch(es) git would not delete — they hold commits "
                    f"nobody has merged, or one of them is checked out: {', '.join(kept)}.")
        done.append("   Delete those yourself with 'git branch -D <name>' when you are sure.")

    if plan.home is not None and plan.home.exists():
        shutil.rmtree(plan.home, ignore_errors=True)
        if plan.home.exists():
            done.append(f"Could not remove {paths.display_home(plan.root)}.")
        else:
            done.append(f"Removed {paths.display_home(plan.root)}.")

    for wf in plan.workflows:
        try:
            wf.unlink()
            done.append(f"Removed {_display(plan.root, wf)}.")
        except OSError as exc:
            done.append(f"Could not remove {_display(plan.root, wf)}: {exc}")

    if plan.gitignore_block and begin and end:
        gitignore = plan.root / ".gitignore"
        try:
            text = gitignore.read_text(encoding="utf-8")
            stripped = strip_gitignore_block(text, begin, end)
            if stripped.strip():
                gitignore.write_text(stripped, encoding="utf-8")
            else:
                # The file held nothing but our block, so `init` created it. Leaving an
                # empty .gitignore behind is residue too.
                gitignore.unlink()
            done.append("Removed lanekeeper's block from .gitignore.")
        except OSError as exc:
            done.append(f"Could not edit .gitignore: {exc}")

    return done
