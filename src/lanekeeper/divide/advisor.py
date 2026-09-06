"""An advisor for step 2: a model that is asked, never obeyed.

Dividing the work is a mechanical answer and stays one. The one question a set
intersection cannot answer is what a ticket that names no files probably touches, and
that is the only question this module asks. The answer is a *suggestion*: it lands in
the draft switched off, marked as proposed, and the user turns it on by hand. It never
reaches the gate.

The only implemented advisor is Claude Code itself, through its own `claude` command in
headless mode. That runs on whatever login the user already has — a Pro or Max
subscription, an API key, a cloud provider — and lanekeeper holds none of it. No token
is read, stored or forwarded; the command is the boundary.

Two mechanical checks stand between the model and the draft. A suggested path is kept
only if it names a file that exists or a pattern that matches one, so the model cannot
invent a directory. And a ticket that already states its files is never sent: the
filer's statement outranks any guess.

The first check has one honest exception (#71). Every path a *new* feature creates is,
by definition, not in the tree yet, so a filter that keeps only existing files answers
the bug-fix ticket well and cannot answer the greenfield one at all — which inverts
the useful case, since a bug ticket usually names its file already. So a suggestion
that matches nothing is kept only as the nearest directory that *does* exist, widened
to a glob: `src/components/settings/ThemeToggle.tsx` is unverifiable,
`src/components/settings/**` is checkable. A directory glob is a materially wider
grant than a named file, so the proposal says which lines were widened, and a
suggestion with no existing ancestor short of the project root is dropped with its
reason said. Every glob written still matches something real.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from ..lanes import LaneEngine
from ..trackers.github_issues import CommandResult

CommandRunner = Callable[[Sequence[str]], CommandResult]

#: Configuration values that select an advisor.
NONE = "none"
CLAUDE_CODE = "claude-code"
KNOWN = (NONE, CLAUDE_CODE)

#: How many tracked files the model is shown. Enough to see the shape of the project;
#: not the whole tree of a monorepo.
FILE_SAMPLE = 400

#: How many paths one suggestion may carry. A ticket that "touches" forty files is not
#: a boundary, it is the project.
MAX_PATHS = 12


class AdvisorError(RuntimeError):
    """The advisor could not be asked. Reported once; the division continues without it."""


@dataclass(frozen=True)
class Proposal:
    """What the advisor's answer became once anchored to the tree (#71).

    `paths` is what may be offered. `widened` records every suggestion that named a
    file not in the tree and the directory glob it became — shown, because accepting
    `src/hooks/**` is a different decision from accepting `src/hooks/useTheme.ts`.
    `dropped` records what could be anchored to nothing, with the reason, so a drop is
    reported rather than swallowed.
    """

    paths: Tuple[str, ...] = ()
    widened: Tuple[Tuple[str, str], ...] = ()
    dropped: Tuple[Tuple[str, str], ...] = ()


class Advisor:
    name: str = NONE

    def propose_paths(self, ref: str, title: str, body: str,
                      files: Sequence[str]) -> Tuple[str, ...]:
        """Paths this ticket probably touches, or nothing. Never raises for a bad answer."""
        return ()


class NoAdvisor(Advisor):
    """The default. Asks nobody."""


def _subprocess_runner(root: Path) -> CommandRunner:
    def run(argv: Sequence[str]) -> CommandResult:
        res = subprocess.run(
            list(argv), cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
        )
        return CommandResult(res.returncode, res.stdout or "", res.stderr or "")
    return run


class ClaudeCodeAdvisor(Advisor):
    """Asks `claude -p` — Claude Code headless — on the user's own login."""

    name = CLAUDE_CODE

    def __init__(self, command: str, root: Path, runner: Optional[CommandRunner] = None):
        self.command = command
        self.root = Path(root)
        self._run = runner or _subprocess_runner(self.root)
        self.asked: List[str] = []
        #: The last answer in full, for a caller that wants to say what was widened.
        self.last_proposal: Optional[Proposal] = None

    def check_available(self) -> None:
        if shutil.which(self.command) is None:
            raise AdvisorError(
                f"The advisor is set to '{CLAUDE_CODE}' but the '{self.command}' command "
                f"is not on PATH. Install Claude Code, or set divide.advisor to 'none'.")

    def propose_paths(self, ref: str, title: str, body: str,
                      files: Sequence[str]) -> Tuple[str, ...]:
        return self.propose(ref, title, body, files).paths

    def propose(self, ref: str, title: str, body: str, files: Sequence[str]) -> Proposal:
        """The answer, anchored to the tree, with what was widened and what was dropped."""
        self.asked.append(ref)
        prompt = build_prompt(ref, title, body, files)
        try:
            res = self._run([self.command, "-p", prompt, "--output-format", "text"])
        except (OSError, subprocess.SubprocessError) as exc:
            raise AdvisorError(f"Could not run '{self.command}': {exc}") from exc
        if res.returncode != 0:
            raise AdvisorError(
                f"'{self.command} -p' exited {res.returncode}: {res.stderr.strip()[:200]}")
        self.last_proposal = anchor_paths(parse_paths(res.stdout), files)
        return self.last_proposal


def build_prompt(ref: str, title: str, body: str, files: Sequence[str]) -> str:
    sample = list(files)[:FILE_SAMPLE]
    more = len(files) - len(sample)
    listing = "\n".join(sample) + (f"\n... and {more} more" if more > 0 else "")
    return (
        "You are helping divide a backlog between coding agents. Each agent may only "
        "touch the files its ticket owns. This ticket does not say which files it "
        "touches. From the ticket and the file list, name the files or glob patterns "
        "it would most likely change or create. Prefer a few directory globs over many "
        f"single files. At most {MAX_PATHS} entries. Paths that appear in the list, or "
        "patterns that match them, are best; for new work you may name files that do "
        "not exist yet, and each will be widened to the nearest directory that does. "
        "Answer with a JSON object and nothing else: "
        '{"paths": ["path/or/glob", ...]}\n\n'
        f"Ticket #{ref}: {title}\n\n{body.strip()}\n\n"
        f"Files in the project:\n{listing}\n"
    )


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_paths(text: str) -> Tuple[str, ...]:
    """The `paths` list out of the model's answer, or nothing if it did not give one."""
    match = _JSON_OBJECT.search(text or "")
    if not match:
        return ()
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return ()
    raw = data.get("paths") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return ()
    out = []
    for item in raw:
        text_item = str(item).strip().replace("\\", "/").lstrip("./")
        if text_item and text_item not in out:
            out.append(text_item)
    return tuple(out[:MAX_PATHS])


def anchor_paths(paths: Sequence[str], files: Sequence[str]) -> Proposal:
    """Every suggestion, kept as it is or as the nearest existing directory (#71).

    A suggestion that matches a tracked file is kept verbatim. One that matches
    nothing is walked up: the first ancestor directory that holds a tracked file
    becomes `<dir>/**`. The walk stops short of a single top-level segment and of the
    root — `src/**` is the project, not a boundary — and a suggestion that reaches
    that point is dropped with the reason. Every glob written therefore matches
    something real, which is `keep_real_paths`' guarantee kept by another route.
    """
    listed = list(files)
    kept: List[str] = []
    widened: List[Tuple[str, str]] = []
    dropped: List[Tuple[str, str]] = []

    def _add(path: str) -> None:
        if path not in kept:
            kept.append(path)

    for path in paths:
        if any(LaneEngine.match_glob(f, path) for f in listed):
            _add(path)
            continue
        anchor = _existing_ancestor(path, listed)
        if anchor is None:
            top = path.split("/")[0]
            dropped.append((path, (
                f"nothing under '{top}/' exists in this project" if "/" in path
                and not _directory_exists(top, listed)
                else f"no directory it could belong to exists short of '{top}/', and "
                     f"'{top}/**' would be the whole project, not a boundary")))
            continue
        glob = f"{anchor}/**"
        widened.append((path, glob))
        _add(glob)
    return Proposal(paths=tuple(kept), widened=tuple(widened), dropped=tuple(dropped))


def _directory_exists(directory: str, files: Sequence[str]) -> bool:
    prefix = directory.rstrip("/") + "/"
    return any(f.startswith(prefix) for f in files)


def _existing_ancestor(path: str, files: Sequence[str]) -> Optional[str]:
    """The deepest ancestor directory of `path`, at least two segments deep, that
    holds a tracked file; None when there is none."""
    parts = [p for p in path.replace("\\", "/").split("/") if p and p not in ("*", "**")]
    for depth in range(len(parts) - 1, 1, -1):
        candidate = "/".join(parts[:depth])
        if _directory_exists(candidate, files):
            return candidate
    return None


def keep_real_paths(paths: Sequence[str], files: Sequence[str]) -> Tuple[str, ...]:
    """Drops every suggestion that names nothing in the project.

    This is the check that keeps the model honest. A path that exists, or a pattern
    that matches at least one tracked file, is kept; anything else is an invention.
    """
    listed = list(files)
    kept = []
    for path in paths:
        if any(LaneEngine.match_glob(f, path) for f in listed):
            kept.append(path)
    return tuple(kept)


def get_advisor(settings, root: Path, runner: Optional[CommandRunner] = None) -> Advisor:
    """The advisor `divide.advisor` names. Fails closed on a name it does not know."""
    name = (getattr(settings, "advisor", NONE) or NONE).strip().lower()
    if name == NONE:
        return NoAdvisor()
    if name == CLAUDE_CODE:
        advisor = ClaudeCodeAdvisor(settings.advisor_command, root, runner=runner)
        if runner is None:
            advisor.check_available()
        return advisor
    raise AdvisorError(f"Unknown advisor '{name}'. Known: {', '.join(KNOWN)}.")
