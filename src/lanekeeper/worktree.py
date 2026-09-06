"""Git worktree and branch isolation management."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


class GitError(RuntimeError):
    """Raised when a Git command fails or violates safety rules."""


@dataclass
class RemoteLookup:
    """The answer to "what does the remote know about this branch name"."""

    remote: str
    #: False when there is no such remote, or it could not be reached (see `error`).
    available: bool
    error: str = ""
    #: Branch name → commit sha, for every remote branch matching the pattern asked.
    branches: dict = field(default_factory=dict)

    def sha(self, branch_name: str) -> Optional[str]:
        return self.branches.get(branch_name)


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
        timeout: Optional[float] = None,
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
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise GitError(
                f"Git command timed out after {timeout:.0f}s ('git {' '.join(args)}')") from e
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

    def current_branch(self, cwd: Optional[Path] = None) -> str:
        """The branch checked out at `cwd`, or "" when detached or unanswerable.

        Read so that advice about committing can name the branch the person is
        actually on. A message that always said `main` told somebody on `my-test` to
        switch branches — and to commit to a branch the same file lists as protected.
        """
        try:
            res = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, check=False)
        except (GitError, OSError):
            return ""
        name = (res.stdout or "").strip() if res.returncode == 0 else ""
        return "" if name in ("", "HEAD") else name

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

    def branch_is_merged(self, branch_name: str, base: str) -> bool:
        """Whether every commit on the branch is already on `base`.

        Asked directly — `git merge-base --is-ancestor` — rather than inferred from
        `git branch -d`'s exit code (#65). `-d`'s documented rule is "fully merged in
        its upstream branch, or in HEAD if no upstream was set". A branch pushed with
        `-u` therefore had an upstream identical to itself and git agreed to delete it;
        lanekeeper then reported "fully merged", which is not what had been established.
        Nothing had checked the branch against the base at all. The test suite never
        saw it because no test ever pushed to a remote.
        """
        res = self._run_git(["merge-base", "--is-ancestor", branch_name, base], check=False)
        return res.returncode == 0

    def branch_upstream(self, branch_name: str) -> Optional[str]:
        """The branch's upstream (`origin/x`), or None when it has none."""
        res = self._run_git(
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{branch_name}@{{upstream}}"],
            check=False)
        name = (res.stdout or "").strip()
        return name if res.returncode == 0 and name else None

    def branch_is_pushed(self, branch_name: str) -> Optional[bool]:
        """Whether every commit on the branch is on its upstream; None without one."""
        upstream = self.branch_upstream(branch_name)
        if upstream is None:
            return None
        return self.branch_is_merged(branch_name, upstream)

    def describe_kept_branch(self, branch_name: str, base: str) -> str:
        """Why a branch was kept, with the fact that decides its risk: where its
        commits are. "Pushed to origin" and "not pushed anywhere" carry very different
        risk and used to be indistinguishable."""
        pushed = self.branch_is_pushed(branch_name)
        if pushed:
            return (f"Kept branch {branch_name}: not merged into {base}. Its commits are "
                    f"pushed to {self.branch_upstream(branch_name)}.")
        if pushed is False:
            return (f"Kept branch {branch_name}: not merged into {base}, and not every "
                    f"commit on it is on {self.branch_upstream(branch_name)}. Push it, or "
                    f"delete it yourself with 'git branch -D' when you are sure.")
        return (f"Kept branch {branch_name}: not merged into {base}, and not pushed "
                f"anywhere. Delete it yourself with 'git branch -D' when you are sure.")

    def delete_branch(self, branch_name: str, force: bool = False,
                      base: Optional[str] = None) -> bool:
        """Deletes a local branch when it is merged into `base` (the default branch
        unless given), or unconditionally with `force`. Returns False when it was kept —
        unmerged, or checked out in a worktree — so the caller says so."""
        if not self.branch_exists(branch_name):
            return False
        if not force and not self.branch_is_merged(branch_name, base or self.get_default_branch()):
            return False
        # `-D`, because `-d` would consult the upstream and say yes to a pushed branch;
        # the question that matters was answered above.
        res = self._run_git(["branch", "-D", branch_name], check=False)
        return res.returncode == 0

    def has_remote(self, remote: str = "origin") -> bool:
        res = self._run_git(["remote", "get-url", remote], check=False)
        return res.returncode == 0

    def remote_branches(self, pattern: str, remote: str = "origin",
                        timeout: float = 15.0) -> "RemoteLookup":
        """What the remote holds under `refs/heads/<pattern>` (#78).

        `git ls-remote` needs no GitHub API, no token and no `gh`. It does need the
        network, so it gets a timeout and a failure is a *note*, never an error: this
        is a convenience check, and the gate does not depend on it.
        """
        if not self.has_remote(remote):
            return RemoteLookup(remote=remote, available=False, error="")
        try:
            res = self._run_git(["ls-remote", "--heads", remote, f"refs/heads/{pattern}"],
                                check=False, timeout=timeout)
        except GitError as e:
            return RemoteLookup(remote=remote, available=False, error=str(e))
        if res.returncode != 0:
            return RemoteLookup(remote=remote, available=False,
                                error=(res.stderr or "").strip().splitlines()[-1:][0]
                                if (res.stderr or "").strip() else f"exit {res.returncode}")
        found = {}
        for line in (res.stdout or "").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].startswith("refs/heads/"):
                found[parts[1][len("refs/heads/"):]] = parts[0]
        return RemoteLookup(remote=remote, available=True, branches=found)

    def fetch_branch(self, branch_name: str, remote: str = "origin") -> None:
        """Brings a remote branch down as a local branch of the same name, tracking it."""
        self._run_git(["fetch", remote, f"{branch_name}:{branch_name}"])
        self._run_git(["branch", f"--set-upstream-to={remote}/{branch_name}", branch_name],
                      check=False)
