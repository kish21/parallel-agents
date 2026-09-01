"""Regression tests for the ways the boundary check used to pass work it should not.

Every case here was reproduced against v0.6.0 before it was fixed. Each is a way an
agent's change left its lane and `validate` said nothing:

* a rename out of another lane reported only its destination;
* a base branch git could not diff against produced an empty change list, and an empty
  change list validates clean;
* the lane policy and the seat cards were exempt from the lane check, so a pull request
  could widen its own lane;
* a deny written as a directory (`secrets/`) matched nothing;
* a lane with no `allow` patterns allowed everything;
* an unreadable state ledger was read as an empty one;
* `cleanup` asked for confirmation and then ignored the answer.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from lanekeeper.config import Config, InvalidLaneError, LaneConfig, load_config, save_config
from lanekeeper.lanes import LaneEngine
from lanekeeper.state import AgentState, StateCorruptError, StateManager
from lanekeeper.validator import Validator
from lanekeeper.worktree import GitError, WorktreeManager

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import cli_env, output_of, run_cli  # noqa: E402


def _two_lane_config() -> Config:
    cfg = Config.default("proj")
    cfg.lanes = {
        "backend": LaneConfig(name="backend", allow=["src/backend/**"], deny=["secrets/"]),
        "frontend": LaneConfig(name="frontend", allow=["src/frontend/**"], deny=[]),
    }
    cfg.capability_gates = {}
    return cfg


class RepoTestCase(unittest.TestCase):
    """A real repository with a tracked lane policy and one agent worktree."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._git("init", "-q", "-b", "main", ".")
        self._git("config", "user.email", "t@t.c")
        self._git("config", "user.name", "t")
        for rel in ["src/backend/api.py", "src/frontend/App.tsx", "secrets/prod.pem",
                    ".gitignore"]:
            f = self.tmp / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("original\n", encoding="utf-8")
        self.cfg = _two_lane_config()
        save_config(self.cfg, self.tmp)
        cards = self.tmp / ".lanekeeper" / "capabilities"
        cards.mkdir(parents=True)
        (cards / "JR1.json").write_text('{"seat": "JR1"}', encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-qm", "init")

        self.state = StateManager(self.tmp)
        self.wt_mgr = WorktreeManager(self.tmp)
        self.wt = self.wt_mgr.create_worktree(Path("wt"), "parallel/agent-001/t")
        self.agent = AgentState(
            id="agent-001", name="w1", seat="JR1", lane="backend", task="t",
            branch="parallel/agent-001/t", worktree_path=str(self.wt),
        )
        self.state.save_agent(self.agent)

    def _git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.tmp, check=True,
                              capture_output=True)

    def _validate(self):
        return Validator(self.cfg, self.state, self.wt_mgr).validate_agent("agent-001")


class TestRenamesAreChangesToBothFiles(RepoTestCase):
    def test_uncommitted_move_out_of_another_lane_is_a_violation(self):
        self._git("mv", "src/frontend/App.tsx", "src/backend/App.tsx", cwd=self.wt)
        report = self._validate()
        self.assertFalse(report.is_valid, output_of_report(report))
        self.assertIn("src/frontend/App.tsx", {v.filepath for v in report.lane_result.violations})

    def test_committed_move_out_of_another_lane_is_a_violation(self):
        self._git("mv", "src/frontend/App.tsx", "src/backend/App.tsx", cwd=self.wt)
        self._git("commit", "-qm", "move", cwd=self.wt)
        report = self._validate()
        self.assertFalse(report.is_valid, output_of_report(report))
        self.assertIn("src/frontend/App.tsx", {v.filepath for v in report.lane_result.violations})

    def test_committed_move_of_a_denied_file_is_a_violation(self):
        self._git("mv", "secrets/prod.pem", "src/backend/prod.pem", cwd=self.wt)
        self._git("commit", "-qm", "move", cwd=self.wt)
        report = self._validate()
        self.assertFalse(report.is_valid)
        denied = [v for v in report.lane_result.violations if v.reason == "denied"]
        self.assertEqual([v.filepath for v in denied], ["secrets/prod.pem"])


class TestAnUnreadableDiffIsAFailedCheck(RepoTestCase):
    def test_missing_base_branch_raises(self):
        with self.assertRaises(GitError):
            self.wt_mgr.get_changed_files(self.wt, base_branch="no-such-branch")

    def test_validator_reports_invalid_rather_than_clean(self):
        # Commit a denied change, then take away the branch the diff is computed against.
        (self.wt / "secrets" / "prod.pem").write_text("exfil\n", encoding="utf-8")
        self._git("commit", "-qam", "bad", cwd=self.wt)
        self._git("branch", "-m", "main", "trunk")
        report = self._validate()
        self.assertFalse(report.is_valid)
        self.assertTrue(any("nothing was checked" in e for e in report.errors), report.errors)
        self.assertEqual(report.lane_result.allowed_files, [],
                         "no file may be reported as allowed when none was examined")


class TestThePolicyIsNotSubjectToThePolicy(RepoTestCase):
    def test_widening_the_lane_policy_is_a_violation(self):
        cfg_file = self.wt / ".lanekeeper" / "config.yaml"
        cfg_file.write_text(cfg_file.read_text(encoding="utf-8") + "\n# widened\n",
                            encoding="utf-8")
        report = self._validate()
        self.assertFalse(report.is_valid)
        policy = [v for v in report.lane_result.violations if v.reason == "policy"]
        self.assertEqual([v.filepath for v in policy], [".lanekeeper/config.yaml"])
        self.assertTrue(any("Lane policy modified" in e for e in report.errors), report.errors)

    def test_editing_a_seat_card_is_a_violation(self):
        (self.wt / ".lanekeeper" / "capabilities" / "JR1.json").write_text(
            '{"seat": "JR1", "capabilities": {"security_review": "native"}}', encoding="utf-8")
        report = self._validate()
        self.assertFalse(report.is_valid)
        self.assertIn(".lanekeeper/capabilities/JR1.json",
                      {v.filepath for v in report.lane_result.violations if v.reason == "policy"})

    def test_even_a_lane_that_allows_everything_cannot_touch_it(self):
        wide = LaneConfig(name="wide", allow=["**"], deny=[])
        result = LaneEngine.validate_files([".lanekeeper/config.yaml", "src/x.py"], wide)
        self.assertFalse(result.is_valid)
        self.assertEqual([v.reason for v in result.violations], ["policy"])

    def test_gitignore_is_ordinary_work(self):
        """It used to be exempt. It is the file that keeps peer worktrees out of a commit."""
        result = LaneEngine.validate_files([".gitignore"], self.cfg.get_lane("backend"))
        self.assertFalse(result.is_valid)

    def test_runtime_state_is_still_ignored(self):
        result = LaneEngine.validate_files(
            [".lanekeeper/state/agents.json", ".lanekeeper/logs/agent-001.log", ".env", ".lane"],
            self.cfg.get_lane("backend"))
        self.assertTrue(result.is_valid)
        self.assertEqual(result.allowed_files, [])


class TestDirectoryPatterns(unittest.TestCase):
    def test_a_trailing_slash_means_everything_under_it(self):
        self.assertTrue(LaneEngine.match_glob("secrets/prod.pem", "secrets/"))
        self.assertTrue(LaneEngine.match_glob("secrets/deep/er/key", "secrets/"))
        self.assertFalse(LaneEngine.match_glob("secretsx/key", "secrets/"))

    def test_deny_written_as_a_directory_is_enforced(self):
        lane = LaneConfig(name="l", allow=["**"], deny=["secrets/"])
        violation = LaneEngine.check_file("secrets/prod.pem", lane)
        self.assertIsNotNone(violation)
        self.assertEqual(violation.reason, "denied")


class TestALaneMustAllowSomething(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, lanes):
        cfg_dir = self.tmp / ".lanekeeper"
        cfg_dir.mkdir()
        (cfg_dir / "config.yaml").write_text(
            yaml.safe_dump({"project": {"name": "p"}, "lanes": lanes}), encoding="utf-8")

    def test_empty_allow_is_refused(self):
        self._write({"wide": {"allow": [], "deny": ["x/**"]}})
        with self.assertRaises(InvalidLaneError) as ctx:
            load_config(self.tmp)
        self.assertIn("wide", str(ctx.exception))

    def test_missing_allow_is_refused(self):
        self._write({"wide": {"deny": ["x/**"]}})
        with self.assertRaises(InvalidLaneError):
            load_config(self.tmp)

    def test_null_allow_is_refused(self):
        self._write({"wide": {"allow": None}})
        with self.assertRaises(InvalidLaneError):
            load_config(self.tmp)

    def test_a_single_string_is_refused_rather_than_split_into_letters(self):
        self._write({"one": {"allow": "src/**"}})
        with self.assertRaises(InvalidLaneError):
            load_config(self.tmp)

    def test_a_real_lane_loads(self):
        self._write({"api": {"allow": ["src/api/**"], "deny": None}})
        cfg = load_config(self.tmp)
        self.assertEqual(cfg.lanes["api"].allow, ["src/api/**"])
        self.assertEqual(cfg.lanes["api"].deny, [])


class TestADamagedLedgerStopsEverything(RepoTestCase):
    def test_corrupt_ports_file_raises_and_is_left_alone(self):
        self.state.allocate_port(8001, "agent-001")
        self.state.ports_file.write_text('{"8001": "agent-001", "8002": ', encoding="utf-8")
        before = self.state.ports_file.read_text(encoding="utf-8")
        with self.assertRaises(StateCorruptError):
            self.state.get_allocated_ports()
        with self.assertRaises(StateCorruptError):
            self.state.allocate_port(8003, "agent-002")
        self.assertEqual(self.state.ports_file.read_text(encoding="utf-8"), before,
                         "a write must never replace a ledger that could not be read")

    def test_corrupt_agents_file_does_not_become_a_one_agent_file(self):
        self.state.agents_file.write_text("not json", encoding="utf-8")
        with self.assertRaises(StateCorruptError):
            self.state.save_agent(self.agent)
        self.assertEqual(self.state.agents_file.read_text(encoding="utf-8"), "not json")

    def test_the_cli_says_so_without_a_traceback(self):
        self.state.agents_file.write_text("[]", encoding="utf-8")
        res = run_cli(["status"], cwd=self.tmp)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertNotIn("Traceback", res.stderr)
        self.assertIn("agents.json", res.stderr)


class TestCleanupHonoursTheAnswer(RepoTestCase):
    def test_answering_y_removes_the_worktree(self):
        (self.wt / "src" / "backend" / "api.py").write_text("uncommitted\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "lanekeeper.cli", "cleanup", "agent-001"],
            cwd=str(self.tmp), input="y\n", capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=cli_env(),
        )
        self.assertEqual(proc.returncode, 0, output_of(proc))
        self.assertFalse(self.wt.exists())
        agents = json.loads(self.state.agents_file.read_text(encoding="utf-8"))
        self.assertNotIn("agent-001", agents)

    def test_answering_n_keeps_everything(self):
        (self.wt / "src" / "backend" / "api.py").write_text("uncommitted\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "lanekeeper.cli", "cleanup", "agent-001"],
            cwd=str(self.tmp), input="n\n", capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=cli_env(),
        )
        self.assertEqual(proc.returncode, 1, output_of(proc))
        self.assertTrue(self.wt.exists())


def output_of_report(report) -> str:
    return "\n".join(report.errors) + "\n" + "\n".join(
        f"{v.reason}: {v.filepath}" for v in report.lane_result.violations)


if __name__ == "__main__":
    unittest.main()
