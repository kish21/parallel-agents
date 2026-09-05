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
    def main_worktree_root() -> Optional[Path]:
        """The repository's main checkout, seen from anywhere inside it.

        A linked worktree shares the main checkout's git directory, so
        `--git-common-dir` resolves to `<main checkout>/.git` from inside either.
        Returns None when that shape does not hold — a bare repository, a separate
        git directory — because the caller then has nothing better to read.
        """
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--git-common-dir"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", check=True,
            )
        except (subprocess.CalledProcessError, OSError):
            return None
        common = Path(res.stdout.strip())
        if not common.is_absolute():
            common = (Path.cwd() / common).resolve()
        return common.parent if common.name == ".git" else None

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
            # Git writes progress ("Preparing worktree...") to stderr alongside the real
            # error, so keep every line: truncating to one hid the actual cause.
            streams = [s.strip() for s in (e.stderr, e.stdout) if s and s.strip()]
            err_msg = " | ".join(" | ".join(s.splitlines()) for s in streams) or f"exit {e.returncode}"
            raise GitError(
                f"Git command failed ('git {' '.join(args)}', exit {e.returncode}): {err_msg}"
            ) from e

    def is_git_repo(self) -> bool:
        try:
            res = self._run_git(["rev-parse", "--is-inside-work-tree"], check=False)
            return res.returncode == 0 and res.stdout.strip() == "true"
        except Exception:
            return False

    def repo_toplevel(self) -> Optional[Path]:
        """The root of the repository this directory sits in, or None if there is none.

        `--repo` points at a directory somebody typed. Lanekeeper writes its home beside
        the repository root, so a subdirectory has to be named as one rather than
        quietly initialising a second, half-working setup one level down.
        """
        try:
            res = self._run_git(["rev-parse", "--show-toplevel"], check=False)
        except GitError:
            return None
        if res.returncode != 0 or not res.stdout.strip():
            return None
        return Path(res.stdout.strip())

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
        # Trim the cut back to a word boundary: a slug ending in a separator reads as
        # a mistake on every branch listing.
        return text[:40].strip("-") or "task"

    def make_branch_name(self, agent_id: str, task: str, prefix: str = "parallel/") -> str:
        task_slug = self.slugify(task)
        clean_prefix = prefix.rstrip("/") + "/"
        return f"{clean_prefix}{agent_id}/{task_slug}"

    def list_branches(self, prefix: str = "") -> List[str]:
        """Local branch names, optionally only those starting with `prefix`.

        `for-each-ref` rather than `branch --list`: it prints one plain name per line
        with no decoration, so the branch that happens to be checked out does not
        arrive with an asterisk on the front.
        """
        res = self._run_git(
            ["for-each-ref", "--format=%(refname:short)", "refs/heads/"], check=False)
        if res.returncode != 0:
            return []
        names = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return [n for n in names if n.startswith(prefix)] if prefix else names

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
        """Whether the worktree holds work that would be lost.

        Lanekeeper writes `.lane` and `.env` into every worktree it creates, so a
        worktree where nobody has done anything is still "dirty" to git. Counting
        those made `cleanup` demand `--force` on an agent that never ran, which
        teaches people to pass `--force` always — exactly the habit the question
        exists to prevent.
        """
        from .lanes import LaneEngine  # local: lanes imports config, config imports nothing here

        if not worktree_path.exists():
            return False
        res = self._run_git(["status", "--porcelain"], cwd=worktree_path, check=False)
        for line in (res.stdout or "").splitlines():
            path = line[3:].strip().strip('"')
            # A rename reads "old -> new"; either side is somebody's work.
            path = path.split(" -> ")[-1] if " -> " in path else path
            if path and not LaneEngine.is_bookkeeping(LaneEngine.normalize_path(path)):
                return True
        return False

    def get_changed_files(
        self,
        worktree_path: Path,
        base_branch: Optional[str] = None,
    ) -> List[str]:
        base = base_branch or self.get_default_branch()
        if not worktree_path.exists():
            return []

        # 1. Committed diff against base branch
        committed_files = self.diff_files(base, "HEAD", cwd=worktree_path)

        # 2. Uncommitted & untracked working-tree changes. The failure of this call is
        #    also a failure of the check: an empty list is what a clean tree returns, and
        #    a validator that cannot tell the two apart passes whatever it could not see.
        status_res = self._run_git(
            ["status", "--porcelain", "-z", "-uall"],
            cwd=worktree_path,
        )
        uncommitted_files = self._parse_porcelain_z(status_res.stdout)

        return list(dict.fromkeys(committed_files + uncommitted_files))

    def diff_files(self, base: str, head: str = "HEAD",
                   cwd: Optional[Path] = None) -> List[str]:
        """Every path that differs between the merge base of `base` and `head`.

        Raises ``GitError`` when git cannot compute it — an unknown base branch, a
        shallow clone with no merge base. This used to swallow the error and return no
        files, and "no files" is exactly what a clean branch looks like: an agent whose
        base branch was misnamed had every committed change waved through as "All 0
        changed files are within allowed lane paths."

        ``--no-renames`` because a rename is a deletion and a creation, and the deletion
        is a change to the file that was deleted. With detection on, git reports only the
        destination, so moving a file out of another lane — or out of `secrets/` — into
        this one looked like an ordinary in-lane addition. ``-z`` so paths containing
        spaces, quotes or non-ASCII characters survive intact.
        """
        res = self._run_git(
            ["diff", "--name-only", "-z", "--no-renames", f"{base}...{head}"],
            cwd=cwd,
        )
        return [f for f in res.stdout.split("\0") if f]

    @staticmethod
    def _parse_porcelain_z(raw: str) -> List[str]:
        """Parses `git status --porcelain -z` output into paths.

        Each entry is exactly ``XY<space>PATH``: two status columns then a single space.
        The columns are position-significant and X is a space for a change that is not
        staged, so an unstaged modification reads ``" M path"``.

        A rename or copy is followed by its source path as a second NUL-terminated
        field. Both are reported: the destination was written, and the source was
        deleted, which is a change to a file that may belong to somebody else's lane.

        A previous version stripped the line before slicing ``line[3:]``, which removed
        that leading space and took the first character of the path with it. Every
        *modified* file was therefore reported one character short — ``secrets/prod.pem``
        became ``ecrets/prod.pem`` — and no lane or gate pattern matched it. Newly created
        files are reported as ``"?? path"``, which has no leading space and parsed
        correctly, so the defect only affected edits to files that already existed.
        """
        entries = raw.split("\0")
        paths: List[str] = []
        i = 0
        while i < len(entries):
            entry = entries[i]
            i += 1
            if len(entry) < 4:
                continue
            status, path = entry[:2], entry[3:]
            if path:
                paths.append(path)
            if ("R" in status or "C" in status) and i < len(entries):
                source = entries[i]
                i += 1
                if source:
                    paths.append(source)
        return paths

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

        # Past our own guard, the removal is always forced at the git level: the `.lane`
        # and `.env` we wrote are untracked, and git refuses a plain `worktree remove`
        # over them. Whether any of the person's work is at stake was decided above, by
        # `has_uncommitted_changes`, which ignores exactly those two files.
        self._run_git(["worktree", "remove", "--force", str(resolved_path)])
        self.prune()

    def prune(self) -> None:
        self._run_git(["worktree", "prune"], check=False)

    def delete_branch(self, branch_name: str, force: bool = False) -> bool:
        """Deletes a local branch. Returns False when git refuses — an unmerged branch
        without `force` — so the caller can say the work was kept, not lost."""
        if not self.branch_exists(branch_name):
            return False
        flag = "-D" if force else "-d"
        res = self._run_git(["branch", flag, branch_name], check=False)
        return res.returncode == 0
