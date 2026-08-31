"""Git worktree and branch isolation management."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


class GitError(RuntimeError):
    """Raised when a Git command fails or violates safety rules."""


@dataclass
class WorktreeInfo:
    path: Path
    head: str
    branch: Optional[str] = None
    is_bare: bool = False
    is_detached: bool = False


class WorktreeManager:
    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or self._find_repo_root()

    @staticmethod
    def _find_repo_root() -> Path:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            return Path(res.stdout.strip())
        except subprocess.CalledProcessError as e:
            raise GitError("Current directory is not inside a valid Git repository.") from e

    def _run_git(
        self,
        args: List[str],
        cwd: Optional[Path] = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        target_cwd = cwd or self.root_dir
        try:
            return subprocess.run(
                ["git"] + args,
                cwd=target_cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=check,
            )
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip() or e.stdout.strip()
            raise GitError(f"Git command failed ('git {' '.join(args)}'): {err_msg}") from e

    def is_git_repo(self) -> bool:
        try:
            res = self._run_git(["rev-parse", "--is-inside-work-tree"], check=False)
            return res.returncode == 0 and res.stdout.strip() == "true"
        except Exception:
            return False

    def get_default_branch(self) -> str:
        try:
            res = self._run_git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], check=False)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip().replace("origin/", "")
        except Exception:
            pass

        # Fallback to local main / master
        for candidate in ["main", "master"]:
            res = self._run_git(["show-ref", "--verify", f"refs/heads/{candidate}"], check=False)
            if res.returncode == 0:
                return candidate
        return "main"

    @staticmethod
    def slugify(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[-\s]+", "-", text)
        return text[:40] or "task"

    def make_branch_name(self, agent_id: str, task: str, prefix: str = "parallel/") -> str:
        task_slug = self.slugify(task)
        clean_prefix = prefix.rstrip("/") + "/"
        return f"{clean_prefix}{agent_id}/{task_slug}"

    def branch_exists(self, branch_name: str) -> bool:
        res = self._run_git(["show-ref", "--verify", f"refs/heads/{branch_name}"], check=False)
        return res.returncode == 0

    def list_worktrees(self) -> List[WorktreeInfo]:
        res = self._run_git(["worktree", "list", "--porcelain"])
        worktrees: List[WorktreeInfo] = []
        current_wt: dict = {}

        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                if "worktree" in current_wt:
                    worktrees.append(
                        WorktreeInfo(
                            path=Path(current_wt["worktree"]),
                            head=current_wt.get("HEAD", ""),
                            branch=current_wt.get("branch", "").replace("refs/heads/", "") or None,
                            is_bare="bare" in current_wt,
                            is_detached="detached" in current_wt,
                        )
                    )
                current_wt = {}
                continue

            parts = line.split(" ", 1)
            key = parts[0]
            val = parts[1] if len(parts) > 1 else ""
            current_wt[key] = val

        if "worktree" in current_wt:
            worktrees.append(
                WorktreeInfo(
                    path=Path(current_wt["worktree"]),
                    head=current_wt.get("HEAD", ""),
                    branch=current_wt.get("branch", "").replace("refs/heads/", "") or None,
                    is_bare="bare" in current_wt,
                    is_detached="detached" in current_wt,
                )
            )

        return worktrees

    def create_worktree(
        self,
        target_path: Path,
        branch_name: str,
        base_ref: Optional[str] = None,
    ) -> Path:
        resolved_path = (self.root_dir / target_path).resolve()
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

        base = base_ref or self.get_default_branch()

        if self.branch_exists(branch_name):
            # Check out existing branch
            self._run_git(["worktree", "add", str(resolved_path), branch_name])
        else:
            # Create new branch off base
            self._run_git(["worktree", "add", "-b", branch_name, str(resolved_path), base])

        return resolved_path

    def has_uncommitted_changes(self, worktree_path: Path) -> bool:
        if not worktree_path.exists():
            return False
        res = self._run_git(["status", "--porcelain"], cwd=worktree_path, check=False)
        return bool(res.stdout.strip())

    def get_changed_files(
        self,
        worktree_path: Path,
        base_branch: Optional[str] = None,
    ) -> List[str]:
        base = base_branch or self.get_default_branch()
        if not worktree_path.exists():
            return []

        # 1. Committed diff against base branch
        diff_res = self._run_git(
            ["diff", "--name-only", f"{base}...HEAD"],
            cwd=worktree_path,
            check=False,
        )
        committed_files = [f.strip() for f in diff_res.stdout.splitlines() if f.strip()]

        # 2. Uncommitted & untracked working tree changes (use -uall to list all individual files)
        status_res = self._run_git(
            ["status", "--porcelain", "-uall"],
            cwd=worktree_path,
            check=False,
        )
        uncommitted_files = []
        for line in status_res.stdout.splitlines():
            line = line.strip()
            if len(line) > 3:
                filepath = line[3:].strip()
                if " -> " in filepath:
                    filepath = filepath.split(" -> ")[1].strip()
                uncommitted_files.append(filepath)

        all_files = list(dict.fromkeys(committed_files + uncommitted_files))
        return all_files

    def remove_worktree(
        self,
        worktree_path: Path,
        force: bool = False,
    ) -> None:
        resolved_path = (self.root_dir / worktree_path).resolve()
        if not resolved_path.exists():
            # Prune stale registration
            self.prune()
            return

        if self.has_uncommitted_changes(resolved_path) and not force:
            raise GitError(
                f"Worktree at {resolved_path} has uncommitted changes. Use force=True to discard."
            )

        cmd = ["worktree", "remove", str(resolved_path)]
        if force:
            cmd.append("--force")
        self._run_git(cmd)
        self.prune()

    def prune(self) -> None:
        self._run_git(["worktree", "prune"], check=False)
