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
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
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

    def check_available(self) -> None:
        if shutil.which(self.command) is None:
            raise AdvisorError(
                f"The advisor is set to '{CLAUDE_CODE}' but the '{self.command}' command "
                f"is not on PATH. Install Claude Code, or set divide.advisor to 'none'.")

    def propose_paths(self, ref: str, title: str, body: str,
                      files: Sequence[str]) -> Tuple[str, ...]:
        self.asked.append(ref)
        prompt = build_prompt(ref, title, body, files)
        try:
            res = self._run([self.command, "-p", prompt, "--output-format", "text"])
        except (OSError, subprocess.SubprocessError) as exc:
            raise AdvisorError(f"Could not run '{self.command}': {exc}") from exc
        if res.returncode != 0:
            raise AdvisorError(
                f"'{self.command} -p' exited {res.returncode}: {res.stderr.strip()[:200]}")
        return keep_real_paths(parse_paths(res.stdout), files)


def build_prompt(ref: str, title: str, body: str, files: Sequence[str]) -> str:
    sample = list(files)[:FILE_SAMPLE]
    more = len(files) - len(sample)
    listing = "\n".join(sample) + (f"\n... and {more} more" if more > 0 else "")
    return (
        "You are helping divide a backlog between coding agents. Each agent may only "
        "touch the files its ticket owns. This ticket does not say which files it "
        "touches. From the ticket and the file list, name the files or glob patterns "
        "it would most likely change. Prefer a few directory globs over many single "
        f"files. At most {MAX_PATHS} entries. Only name paths that appear in the list "
        "or patterns that match them. Answer with a JSON object and nothing else: "
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
