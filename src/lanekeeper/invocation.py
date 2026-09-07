"""How lanekeeper was started, so it can tell people to run it the same way.

Every "run this next" line used to say `lanekeeper …`. On a Windows Store Python the
shim is not on PATH, so the person types `python -m lanekeeper.cli …` instead — and
then reads instructions naming a command they have just discovered does not work.
Worse, `lanekeeper open` puts them in a *second* window, one whose PATH is whatever
the editor was started with, where even a shim that worked over here may not resolve.

The tool knows exactly how it was invoked. Printing that form back is cheap,
deterministic, and correct for the whole class of installs where the shim was never
available. Nothing here touches PATH or the environment: editing a person's shell from
a spawn command is well outside what this tool should do. Issue #76.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Sequence

#: The console-script entry point `pip` installs.
SHIM = "lanekeeper"

#: The form that works wherever the package is importable. `python -m lanekeeper`
#: since 0.9.0 (`lanekeeper.cli` still works); the short spelling is the one a person
#: who has just hit a wall should be handed.
MODULE_FORM = "python -m lanekeeper"

#: Set this to the command you actually type, when the process cannot tell. The README
#: suggests a PowerShell function `lanekeeper` that runs the module form; inside it
#: `sys.argv[0]` is `cli.py`, so without this the tool would print the long form back
#: at somebody who never types it.
ENV_INVOCATION = "LANEKEEPER_INVOCATION"


def invocation(argv0: Optional[str] = None,
               orig_argv: Optional[Sequence[str]] = None,
               env: Optional[dict] = None) -> str:
    """The command the person typed to start this process: `lanekeeper`, or
    `python -m lanekeeper.cli` with the interpreter they actually used.

    `sys.argv[0]` is the shim's path when the shim ran, and the path to `cli.py` when
    `-m` ran it. `sys.orig_argv` (3.10+) carries the interpreter as typed — `python`,
    `python3`, `py` — which is the spelling to hand back; older interpreters get the
    documented `python`. Anything else — an embedding, a test runner — is neither, and
    gets the documented shim.
    """
    override = (os.environ if env is None else env).get(ENV_INVOCATION, "").strip()
    if override:
        return override
    first = sys.argv[0] if argv0 is None else argv0
    # Backslashes are separators here whatever the host thinks: a Windows argv is a
    # Windows path, and a test on Linux reading one must see the same name.
    name = Path(str(first or "").replace("\\", "/")).name.lower()
    if name.endswith(".exe"):
        name = name[:-4]
    # `python -m lanekeeper` runs `__main__.py`; `python -m lanekeeper.cli` runs
    # `cli.py`. Either way the person typed the module form, and gets it back short.
    if name not in ("cli.py", "__main__.py"):
        return SHIM
    original = list(sys.orig_argv if orig_argv is None else orig_argv) \
        if (orig_argv is not None or hasattr(sys, "orig_argv")) else []
    interpreter = "python"
    if original:
        head = Path(str(original[0]).replace("\\", "/")).name
        if head.lower().endswith(".exe"):
            head = head[:-4]
        # Only a name a person would type. A full path to an interpreter inside a
        # virtual environment is right but unreadable, and `python` still works there.
        if head and (head.lower().startswith("python") or head.lower() == "py") \
                and "/" not in head and "\\" not in head:
            interpreter = head
    return f"{interpreter} -m lanekeeper"


def fallback_line(inv: Optional[str] = None) -> str:
    """The one sentence to add where the instructions hand the person to another
    window. Empty when they are already using the module form, which is the fallback.
    """
    current = inv if inv is not None else invocation()
    if current != SHIM:
        return ""
    return (f"If '{SHIM}' is not found there, '{MODULE_FORM}' is the same program.")
