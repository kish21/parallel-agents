"""Regression tests: values written into .env/.lane must never escape their line.

Task descriptions are free-form operator input. Before these tests, a task containing a
quote, a newline, or a shell metacharacter corrupted the generated .env — and a newline
allowed arbitrary lines (including commands) to be injected into a file that operators
and start-up scripts routinely `source`.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from parallel_agents.config import Config
from parallel_agents.environment import EnvironmentManager, sanitize_env_key, shell_quote
from parallel_agents.state import AgentState

HOSTILE_TASKS = [
    'add "quoted" support',
    "it's an apostrophe",
    "expand $HOME and ${PATH}",
    "run `id` and $(whoami)",
    "line one\nrm -rf /\nline three",
    "tabs\tand\r\ncarriage returns",
    "semicolon; echo pwned",
    "backslash \\ and pipe | and amp &",
]


class TestShellQuote(unittest.TestCase):
    def test_quotes_are_balanced_and_single_line(self):
        for raw in HOSTILE_TASKS:
            with self.subTest(raw=raw):
                quoted = shell_quote(raw)
                self.assertTrue(quoted.startswith("'") and quoted.endswith("'"))
                self.assertNotIn("\n", quoted)
                self.assertNotIn("\r", quoted)

    def test_roundtrips_through_a_real_shell(self):
        """The definitive check: /bin/sh must read back exactly what we meant to store."""
        for raw in HOSTILE_TASKS:
            with self.subTest(raw=raw):
                expected = " ".join(raw.split())
                res = subprocess.run(
                    ["sh", "-c", f"V={shell_quote(raw)}; printf '%s' \"$V\""],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(res.returncode, 0)
                self.assertEqual(res.stdout, expected)

    def test_sanitize_env_key(self):
        self.assertEqual(sanitize_env_key("backend"), "BACKEND")
        self.assertEqual(sanitize_env_key("my-port"), "MY_PORT")
        self.assertEqual(sanitize_env_key("web.api"), "WEB_API")
        self.assertEqual(sanitize_env_key("2fast"), "_2FAST")


class TestEnvFileIsInjectionProof(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.env_mgr = EnvironmentManager(Config.default("proj"))

    def _write(self, task):
        agent = AgentState(
            id="agent-001", name="w1", seat="JR1", lane="backend", task=task,
            branch="parallel/agent-001/x", worktree_path=str(self.tmp),
            ports={"backend": 8001},
        )
        self.env_mgr.write_agent_environment(self.tmp, agent)
        return (self.tmp / ".env").read_text(encoding="utf-8")

    def test_hostile_task_cannot_add_lines(self):
        baseline = len([l for l in self._write("plain task").splitlines() if l])
        for raw in HOSTILE_TASKS:
            with self.subTest(raw=raw):
                lines = [l for l in self._write(raw).splitlines() if l]
                self.assertEqual(
                    len(lines), baseline,
                    f"task {raw!r} changed the .env line count — injection is possible",
                )

    def test_sourcing_env_yields_the_literal_task(self):
        """A hostile task must be inert data after `source`, not executed or expanded."""
        for raw in HOSTILE_TASKS:
            with self.subTest(raw=raw):
                self._write(raw)
                res = subprocess.run(
                    ["sh", "-c", f". '{self.tmp}/.env' && printf '%s' \"$AGENT_TASK\""],
                    capture_output=True, text=True,
                )
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertEqual(res.stdout, " ".join(raw.split()))

    def test_command_substitution_is_not_executed(self):
        self._write("run `id` and $(whoami)")
        res = subprocess.run(
            ["sh", "-c", f". '{self.tmp}/.env' && printf '%s' \"$AGENT_TASK\""],
            capture_output=True, text=True,
        )
        self.assertIn("`id`", res.stdout)
        self.assertIn("$(whoami)", res.stdout)
        self.assertNotIn("uid=", res.stdout)

    def test_lane_file_is_quoted_too(self):
        agent = AgentState(
            id="agent-001", name="w1", seat="SR1'; echo pwned", lane="backend",
            task="t", branch="b", worktree_path=str(self.tmp),
        )
        self.env_mgr.write_agent_environment(self.tmp, agent)
        res = subprocess.run(
            ["sh", "-c", f". '{self.tmp}/.lane' && printf '%s' \"$SEAT\""],
            capture_output=True, text=True,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout, "SR1'; echo pwned")


if __name__ == "__main__":
    unittest.main()
