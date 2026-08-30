"""Regression tests: lane enforcement must fail CLOSED, never open.

Before these tests, a lane name that was not declared in the config (a typo, a renamed
lane, a hand-edited state file) caused the validator to substitute an empty allow/deny
policy. An empty allow list means "no path restriction", so every file passed and the CLI
printed "VALIDATION PASSED: PR is safe to submit and merge" for an agent that had written
to secrets/ and .github/workflows/. A single typo silently disabled the product's entire
safety guarantee. These tests pin the corrected behaviour.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from parallel_agents.config import Config, UnknownLaneError, save_config
from parallel_agents.state import AgentState, StateManager
from parallel_agents.validator import Validator
from parallel_agents.worktree import WorktreeManager

# Files a mis-laned agent must never be told are safe.
DANGEROUS_FILES = [
    "secrets/prod.pem",
    ".github/workflows/release.yml",
    "infra/terraform/main.tf",
]


# `unittest discover` imports these as top-level modules, so a package-relative import
# would not resolve. Put the tests directory on the path explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import run_cli  # noqa: E402


class TestConfigLaneLookupIsStrict(unittest.TestCase):
    def test_get_lane_raises_for_undeclared_lane(self):
        cfg = Config.default("proj")
        with self.assertRaises(UnknownLaneError) as ctx:
            cfg.get_lane("backedn")
        # The error must name the valid options so the typo is obvious.
        self.assertIn("backedn", str(ctx.exception))
        self.assertIn("backend", str(ctx.exception))

    def test_get_lane_returns_declared_lane(self):
        cfg = Config.default("proj")
        self.assertEqual(cfg.get_lane("backend").name, "backend")

    def test_has_lane(self):
        cfg = Config.default("proj")
        self.assertTrue(cfg.has_lane("frontend"))
        self.assertFalse(cfg.has_lane("frontedn"))

    def test_no_permissive_fallback_exists(self):
        """There must be no code path that yields an allow-everything lane by accident."""
        cfg = Config.default("proj")
        for bogus in ["", "NOPE", "backend ", "BACKEND", "../backend"]:
            with self.subTest(lane=bogus):
                self.assertFalse(cfg.has_lane(bogus))
                with self.assertRaises(UnknownLaneError):
                    cfg.get_lane(bogus)


class TestValidatorFailsClosed(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "."], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.c"], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.tmp, check=True)
        (self.tmp / "README.md").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.tmp, check=True)

        self.cfg = Config.default("proj")
        save_config(self.cfg, self.tmp)
        self.state = StateManager(self.tmp)

    def _agent_with_lane(self, lane):
        # A real git worktree, not a bare directory: `git status` reports paths relative
        # to the worktree root only when it genuinely is one.
        wt_mgr = WorktreeManager(self.tmp)
        wt = wt_mgr.create_worktree(Path("wt"), "parallel/agent-001/t")
        agent = AgentState(
            id="agent-001", name="w1", seat="JR1", lane=lane, task="t",
            branch="parallel/agent-001/t", worktree_path=str(wt),
        )
        self.state.save_agent(agent)
        for rel in DANGEROUS_FILES:
            f = wt / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("sensitive", encoding="utf-8")
        return agent

    def test_undeclared_lane_reports_invalid(self):
        self._agent_with_lane("backedn")
        validator = Validator(self.cfg, self.state, WorktreeManager(self.tmp))
        report = validator.validate_agent("agent-001")
        self.assertFalse(report.is_valid, "an undeclared lane must never validate as safe")
        self.assertFalse(report.lane_result.is_valid)
        self.assertTrue(any("backedn" in e for e in report.errors))

    def test_declared_lane_still_detects_real_violations(self):
        """Failing closed must not make the validator uselessly strict."""
        self._agent_with_lane("backend")
        validator = Validator(self.cfg, self.state, WorktreeManager(self.tmp))
        report = validator.validate_agent("agent-001")
        self.assertFalse(report.is_valid)
        flagged = {v.filepath for v in report.lane_result.violations}
        self.assertIn("secrets/prod.pem", flagged)
        self.assertIn(".github/workflows/release.yml", flagged)


class TestCliRejectsUndeclaredLane(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "."], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.c"], cwd=self.tmp, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.tmp, check=True)
        (self.tmp / "README.md").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.tmp, check=True)
        self.assertEqual(run_cli(["init", "--name", "proj"], self.tmp).returncode, 0)

    def test_spawn_rejects_unknown_lane_and_provisions_nothing(self):
        res = run_cli(["spawn", "--lane", "NOPE", "--name", "b1", "--task", "x"], self.tmp)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("Unknown lane", res.stderr)
        self.assertIn("backend", res.stderr)  # lists valid lanes

        # No worktree, no branch, no ledger entry may be left behind.
        agents = json.loads((self.tmp / ".parallel-agents/state/agents.json").read_text())
        self.assertEqual(agents, {})
        ports = json.loads((self.tmp / ".parallel-agents/state/ports.json").read_text())
        self.assertEqual(ports, {})
        branches = subprocess.run(
            ["git", "branch", "--list", "parallel/*"], cwd=self.tmp,
            capture_output=True, text=True,
        )
        self.assertEqual(branches.stdout.strip(), "")

    def test_spawn_accepts_declared_lane(self):
        res = run_cli(["spawn", "--lane", "backend", "--name", "b1", "--task", "x"], self.tmp)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_validate_refuses_agent_whose_lane_was_removed_from_config(self):
        """The state file can outlive a config edit; that must fail closed, not open."""
        self.assertEqual(
            run_cli(["spawn", "--lane", "backend", "--name", "b1", "--task", "x"], self.tmp).returncode, 0)

        # Operator renames the lane in config, leaving the agent orphaned.
        cfg = Config.default("proj")
        cfg.lanes.pop("backend")
        save_config(cfg, self.tmp)

        agents = json.loads((self.tmp / ".parallel-agents/state/agents.json").read_text())
        wt = Path(agents["agent-001"]["worktree_path"])
        for rel in DANGEROUS_FILES:
            f = wt / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("sensitive", encoding="utf-8")

        res = run_cli(["validate", "agent-001"], self.tmp)
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertNotIn("VALIDATION PASSED", res.stdout)
        self.assertIn("VALIDATION FAILED", res.stdout)

    def test_diff_refuses_agent_with_undeclared_lane(self):
        self.assertEqual(
            run_cli(["spawn", "--lane", "backend", "--name", "b1", "--task", "x"], self.tmp).returncode, 0)
        cfg = Config.default("proj")
        cfg.lanes.pop("backend")
        save_config(cfg, self.tmp)

        res = run_cli(["diff", "agent-001"], self.tmp)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertNotIn("LANE OK", res.stdout)


if __name__ == "__main__":
    unittest.main()
