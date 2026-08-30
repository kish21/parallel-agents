"""Shared helper for tests that invoke the CLI as a real subprocess.

The subprocess runs with `cwd` set to a temporary repository, so any relative PYTHONPATH
inherited from the parent would resolve against the wrong directory. Always hand the child
an absolute path to `src/` so the tests pass from a plain checkout as well as from an
installed package.
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
    return env


def run_cli(args, cwd):
    """Runs `parallel-agents <args>` in `cwd` and returns the CompletedProcess."""
    return subprocess.run(
        [sys.executable, "-m", "parallel_agents.cli", *args],
        cwd=str(cwd), capture_output=True, text=True, env=cli_env(),
    )
