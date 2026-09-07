"""The steps around the one command, done for the person instead of described to them.

`spawn --ticket` prepares the desk in one command. What followed it was five more,
each described in the output and each done by hand: install the gate, commit the
policy, push the agent's branch, open the pull request, label it. Every finding of
the second deep-test run was a variation on one theme — the tool knew the answer and
made the person work it out — and this module is that theme taken to its end:

- `next` reads the state of the repository and says the one thing to do now.
- `pr` runs the check, pushes the agent's branch, and opens the labelled pull request.
- `work` starts the coding agent inside the worktree with the prompt already given.
- the pre-push hook runs the check before every push from an agent's branch, so nobody
  has to remember to.

None of it widens what an agent may do. `pr` refuses to push a red change; the hook
refuses a red push; both are the same gate, run earlier.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from . import check as check_mod
from . import paths
from .config import Config, LaneConfig
from .invocation import invocation
from .ports import TERMINAL_STATUSES
from .state import AgentState
from .trackers.github_issues import CommandResult
from .worktree import GitError, WorktreeManager

CommandRunner = Callable[[Sequence[str]], CommandResult]


# --- next --------------------------------------------------------------------------


@dataclass
class Step:
    """One thing to do, with the command that does it when there is one."""

    what: str
    command: str = ""
    #: The agent this concerns, when it concerns one.
    agent: str = ""


@dataclass
class Situation:
    """What `next` found. Steps are in the order they should be done."""

    steps: List[Step] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def all_clear(self) -> bool:
        return not self.steps


def situation(root: Path, config: Optional[Config], agents: Sequence[AgentState],
              worktree_mgr: WorktreeManager,
              policy_uncommitted: Optional[bool] = None) -> Situation:
    """Everything that stands between this repository and its next merged pull request.

    Read, never changed. The order is the order it matters: a policy that is not
    committed makes the gate in CI meaningless, so it comes before anything about an
    agent; an agent with unpushed commits comes before one still working.
    """
    inv = invocation()
    out = Situation()
    if config is None:
        out.steps.append(Step("Hand a ticket to an agent. The policy is written for you.",
                              f"{inv} spawn --ticket <number>"))
        return out

    if policy_uncommitted:
        out.steps.append(Step(
            "Commit the policy, in this checkout, so CI can read the same boundary the "
            "agent was given.",
            f"git add {paths.display_home(root).rstrip('/')} .gitignore && "
            f"git commit -m 'Add the lane policy'"))
    gate = root / check_mod.WORKFLOW_PATH
    if not gate.exists():
        out.steps.append(Step("Install the pull-request gate, once per repository.",
                              f"{inv} install-gate"))
    elif _untracked_or_modified(worktree_mgr, gate.relative_to(root).as_posix()):
        out.steps.append(Step("Commit the gate workflow so it runs on pull requests.",
                              f"git add {gate.relative_to(root).as_posix()} && "
                              f"git commit -m 'Install the lane gate'"))

    base = worktree_mgr.merge_target()
    live = [a for a in agents if a.status not in TERMINAL_STATUSES]
    # (urgency, step): what is closest to a merged pull request comes first, whatever
    # order the agents were spawned in — a missing worktree, then unpushed commits,
    # then uncommitted work, then an agent that has not started, then one whose
    # branch is already up.
    ranked: List[tuple] = []
    for agent in live:
        wt = Path(agent.worktree_path)
        if not wt.exists():
            ranked.append((0, Step(f"{agent.id}'s worktree is missing.", f"{inv} doctor",
                                   agent=agent.id)))
            continue
        ahead = _commits_ahead(worktree_mgr, agent.branch, base)
        if ahead is None:
            out.notes.append(f"Could not compare {agent.branch} with {base}.")
            continue
        if ahead == 0:
            dirty = worktree_mgr.has_uncommitted_changes(wt)
            if dirty:
                ranked.append((2, Step(
                    f"{agent.id} has uncommitted work in its worktree. Check it, then commit.",
                    f"cd {_short(wt, root)} && {inv} check --lane {agent.lane} --base {base} "
                    f"--working-tree", agent=agent.id)))
            else:
                ranked.append((3, Step(
                    f"{agent.id} has not started: no commits yet on {agent.branch}. Start "
                    f"the agent with its prompt.",
                    f"{inv} work {agent.id} -- claude", agent=agent.id)))
            continue
        pushed = worktree_mgr.branch_is_pushed(agent.branch)
        if not pushed:
            ranked.append((1, Step(
                f"{agent.id} has {ahead} commit(s) not yet on the remote. Check, push and "
                f"open the pull request in one go.",
                f"{inv} pr {agent.id}", agent=agent.id)))
        else:
            ranked.append((4, Step(
                f"{agent.id}'s branch is pushed. If its pull request is open and green, "
                f"merge it; then clean up.",
                f"{inv} cleanup {agent.id}", agent=agent.id)))
    ranked.sort(key=lambda r: r[0])
    out.steps.extend(step for _, step in ranked)
    if not live and config.lanes and not out.steps:
        out.notes.append("No live agents. Hand out the next ticket with "
                         f"'{inv} spawn --ticket <number>'.")
    return out


def render_situation(s: Situation) -> str:
    if s.all_clear:
        lines = ["✅ Nothing waiting on you."]
    else:
        first, rest = s.steps[0], s.steps[1:]
        lines = ["▶ Next:", f"   {first.what}"]
        if first.command:
            lines.append(f"     {first.command}")
        if rest:
            lines.append("")
            lines.append("   Then:")
            for step in rest:
                lines.append(f"   • {step.what}")
                if step.command:
                    lines.append(f"       {step.command}")
    for note in s.notes:
        lines.append(f"   ℹ️  {note}")
    return "\n".join(lines)


def _untracked_or_modified(worktree_mgr: WorktreeManager, rel: str) -> bool:
    try:
        res = worktree_mgr._run_git(["status", "--porcelain", "--", rel], check=False)
    except (GitError, OSError):
        return False
    return res.returncode == 0 and bool((res.stdout or "").strip())


def _commits_ahead(worktree_mgr: WorktreeManager, branch: str, base: str) -> Optional[int]:
    try:
        res = worktree_mgr._run_git(["rev-list", "--count", f"{base}..{branch}"], check=False)
    except (GitError, OSError):
        return None
    if res.returncode != 0:
        return None
    try:
        return int((res.stdout or "0").strip())
    except ValueError:
        return None


def _short(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


# --- the prompt, for `work` --------------------------------------------------------


def prompt_for(agent: AgentState, lane: Optional[LaneConfig]) -> str:
    """The same prompt `spawn --ticket` prints, rebuilt from the agent's record.

    Rebuilt rather than stored: the boundary may have been widened by `allow` since
    the spawn, and the prompt handed to the agent should carry the boundary the gate
    will actually check.
    """
    from .ticket import build_prompt
    files = list(lane.allow) if lane is not None else ["(see .lane)"]
    task = agent.task or f"the task for agent {agent.id}"
    return build_prompt(task, files)


def command_with_prompt(command: Sequence[str], prompt: str) -> List[str]:
    """`{prompt}` substituted where it appears, else the prompt as the last argument.

    `claude "<prompt>"` and `cursor --prompt "<prompt>"` are both real shapes; the
    placeholder covers the second without a flag per editor.
    """
    argv = list(command)
    if any("{prompt}" in a for a in argv):
        return [a.replace("{prompt}", prompt) for a in argv]
    return argv + [prompt]


def run_in_worktree(argv: Sequence[str], worktree: Path) -> int:
    """Runs the agent's command in the worktree, attached to this terminal."""
    try:
        return subprocess.call(list(argv), cwd=str(worktree))
    except FileNotFoundError:
        return 127


# --- pr ------------------------------------------------------------------------------


@dataclass
class PullRequestOutcome:
    pushed: bool = False
    url: str = ""
    label: str = ""
    lines: List[str] = field(default_factory=list)
    #: What the person still has to do by hand, when `gh` could not do it.
    manual: List[str] = field(default_factory=list)


def open_pull_request(agent: AgentState, worktree_mgr: WorktreeManager, base: str,
                      gh: str = "gh", runner: Optional[CommandRunner] = None,
                      label_prefix: str = check_mod.DEFAULT_LABEL_PREFIX,
                      remote: str = "origin", title: str = "",
                      body: str = "") -> PullRequestOutcome:
    """Pushes the agent's branch and opens the pull request with its lane label.

    The label is the declaration CI reads, and forgetting it was the single most
    likely cause of a red gate on the first real project. Here it is applied by the
    same code that knows the lane, so it cannot be forgotten or mistyped. `gh` is
    optional: without it the branch is still pushed and the remaining steps are
    printed rather than done.
    """
    out = PullRequestOutcome(label=f"{label_prefix.strip()} {agent.lane}")
    wt = Path(agent.worktree_path)
    try:
        worktree_mgr._run_git(["push", "-u", remote, f"HEAD:{agent.branch}"], cwd=wt)
    except GitError as e:
        out.lines.append(f"❌ Push failed: {e}")
        return out
    out.pushed = True
    out.lines.append(f"⬆️  Pushed {agent.branch} to {remote}.")

    run = runner or _subprocess_runner(wt)

    def call(argv: Sequence[str]) -> Optional[CommandResult]:
        # Every `gh` call, not only the first: a timeout or a missing binary after the
        # push has already happened must become a printed step, never a traceback that
        # swallows the line saying the branch is up.
        try:
            return run(argv)
        except (OSError, subprocess.SubprocessError) as e:
            out.manual.append(f"Open the pull request for {agent.branch} and label it "
                              f"'{out.label}' — '{gh}' could not be run ({e}).")
            return None

    res = call([gh, "label", "create", out.label, "--color", "0e8a16",
                "--description", "Lanekeeper lane", "--force"])
    if res is None:
        return out
    if res.returncode != 0:
        out.manual.append(f"Create the label '{out.label}' by hand — '{gh} label create' "
                          f"failed: {(res.stderr or '').strip()[:160]}")
    res = call([gh, "pr", "create", "--head", agent.branch, "--base", base,
                "--label", out.label, "--title", title or agent.task or agent.branch,
                "--body", body or ""])
    if res is None:
        return out
    if res.returncode != 0:
        detail = (res.stderr or res.stdout or "").strip()
        if "already exists" in detail.lower():
            out.lines.append(f"ℹ️  A pull request for {agent.branch} already exists; make "
                             f"sure it carries the label '{out.label}'.")
            edit = call([gh, "pr", "edit", agent.branch, "--add-label", out.label])
            if edit is not None and edit.returncode == 0:
                out.lines.append(f"🏷️  Label '{out.label}' applied.")
            return out
        out.manual.append(f"Open the pull request for {agent.branch} and label it "
                          f"'{out.label}' — '{gh} pr create' failed: {detail[:200]}")
        return out
    out.url = (res.stdout or "").strip().splitlines()[-1] if (res.stdout or "").strip() else ""
    out.lines.append(f"🔀 Opened the pull request, labelled '{out.label}'"
                     + (f": {out.url}" if out.url else "."))
    return out


def render_pr(out: PullRequestOutcome) -> str:
    lines = list(out.lines)
    for m in out.manual:
        lines.append(f"   ⚠️  {m}")
    return "\n".join(lines)


def _subprocess_runner(cwd: Path) -> CommandRunner:
    def run(argv: Sequence[str]) -> CommandResult:
        res = subprocess.run(list(argv), cwd=str(cwd), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=120)
        return CommandResult(res.returncode, res.stdout or "", res.stderr or "")
    return run


# --- the pre-push hook ---------------------------------------------------------------

HOOK_MARK = "# lanekeeper pre-push hook"


def hook_text(branch_prefix: str, base: str, interpreter: str = "") -> str:
    """The pre-push hook: the check, on lanekeeper's branches only.

    Only those — a branch the person made by hand has no lane in its name, and
    `check` would refuse it, which is right for CI and wrong for a hook that would
    then block every push from the repository. The check reads the lane from the
    branch, so there is nothing to type and nothing to get wrong.

    Two things are decided at push time, not install time. The base is the remote's
    HEAD when the clone knows it, so a default branch renamed after the install is
    still the one compared against; the name baked in is the fallback. And the
    fallback interpreter is the one that ran the install, by absolute path: a bare
    `python` is not on the PATH of a push made from an editor's source-control panel,
    and a hook that cannot start is a push refused for a reason nobody asked for.
    """
    prefix = branch_prefix.rstrip("/") + "/"
    # Forward slashes even on Windows: this is an sh script, and `C:/…/python.exe`
    # is a path both sh and Windows read the same way, where a backslash inside
    # quotes is whatever the shell that runs the hook decides it is.
    python = shlex.quote(Path(interpreter or sys.executable).as_posix())
    return f"""#!/usr/bin/env sh
{HOOK_MARK} — written by `lanekeeper install-gate --hooks`; delete this file to remove it.
# Runs the lane check before a push from an agent's branch. Branches lanekeeper did
# not make are not its business and are pushed untouched.
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
case "$branch" in
  {prefix}*) ;;
  *) exit 0 ;;
esac
base="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null)"
[ -n "$base" ] || base="{base}"
if command -v lanekeeper >/dev/null 2>&1; then
  lanekeeper check --lane-from-branch --base "$base"
else
  {python} -m lanekeeper check --lane-from-branch --base "$base"
fi
"""


class HookNotInstalled(RuntimeError):
    """The hook could not be written safely, with the reason."""


def install_hook(root: Path, worktree_mgr: WorktreeManager, branch_prefix: str,
                 base: str, force: bool = False) -> Optional[Path]:
    """Writes the hook into the repository's common hooks directory.

    The common directory, so one install covers the main checkout and every agent
    worktree — git reads hooks from there for all of them. An existing hook that is
    not ours is never overwritten without `force`; a person's own pre-push is theirs.
    Returns None when it was left alone. Refuses a base of `HEAD`: that is
    `merge_target()` having found nothing to compare against, and a hook that diffs a
    branch against itself passes every push.
    """
    if not base or base == "HEAD":
        raise HookNotInstalled(
            "No base branch to compare against: this clone has no origin/HEAD and no "
            "main or master. Set one (git remote set-head origin -a), then run again.")
    res = worktree_mgr._run_git(["rev-parse", "--git-common-dir"], check=False)
    common = Path((res.stdout or "").strip() or ".git")
    if not common.is_absolute():
        common = (root / common).resolve()
    hooks = common / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    target = hooks / "pre-push"
    if target.exists() and not force:
        try:
            ours = HOOK_MARK in target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            ours = False
        if not ours:
            return None
    # LF on every platform: git runs the hook through sh, and a CRLF `esac` is a
    # syntax error that refuses every push on Windows.
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(hook_text(branch_prefix, base))
    try:
        target.chmod(target.stat().st_mode | 0o111)
    except OSError:
        pass
    return target
