"""Shared helper for tests that invoke the CLI as a real subprocess.

Two portability rules are encoded here, both learned from Windows CI:

1. The subprocess runs with `cwd` set to a temporary repository, so any relative
   PYTHONPATH inherited from the parent would resolve against the wrong directory.
   Always hand the child an absolute path to `src/`.

2. Captured streams are normalised to strings, and decoding is pinned to UTF-8. The CLI
   prints emoji, which the Windows default locale encoding cannot represent; and a
   captured stream that comes back as None turns an innocuous assertion message like
   `res.stdout + res.stderr` into a TypeError that masks the real result.
"""

import os
import subprocess
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


def cli_env():
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing if existing else "")
    # Force UTF-8 in the child so its emoji output survives on Windows consoles.
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_cli(args, cwd):
    """Runs `lanekeeper <args>` in `cwd`.

    Returns the CompletedProcess with `stdout` and `stderr` guaranteed to be strings,
    never None, so callers can safely build assertion messages from them.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "lanekeeper.cli", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=cli_env(),
    )
    proc.stdout = proc.stdout or ""
    proc.stderr = proc.stderr or ""
    return proc


def output_of(proc):
    """Combined stdout+stderr, for use as an assertion message."""
    return f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
